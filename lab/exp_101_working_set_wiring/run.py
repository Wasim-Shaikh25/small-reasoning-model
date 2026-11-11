"""EXP-101: lab.common.paged.WorkingSet, wired into lab.common.brain.reason
as a bounded-RAM cap on connector-fetched passages.

paged.py (EXP-015) had zero real callers anywhere outside its own module
before this -- confirmed by grep, not assumed. Its WorkingSet class
(admit-with-relevance, evict-least-relevant-beyond-budget, pin) is
exactly the mechanism the project owner's own architecture question
named: "brain memory... which makes it not bounded with any context
length". The concrete, previously-unaddressed gap it closes: once
lab.common.store.Store or any other connector is wired in (EXP-099),
`reason()`'s own passage list grows by however many hits the connector
returns -- `connector_top_k` can be set arbitrarily large, and
GraphConnector is queried once per ask entity with no shared cap at all
-- with nothing bounding how large that list gets in a single call.

This wiring deliberately stays narrow: only passages a `connector` adds
are ever subject to eviction. Every passage the caller supplies directly
is kept exactly as before (today's unbounded behavior, when
working_set_budget is omitted) -- this closes the one place passages can
grow large from a single external fetch, without touching the deeper
`scoped`/`graph_expand` machinery further into `_reason_once`, which
already commits to its own bounded subset by construction and was not
audited for this change.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run
from lab.common.store import Store

FILES = [
    "lab/exp_101_working_set_wiring/run.py",
    "lab/common/brain.py",
    "lab/common/paged.py",
    "lab/common/relevance.py",
    "data/exp_101_working_set_wiring/results.json",
]

ASK = "What is the notice period for employees?"

# Six passages a connector could plausibly return for this ask -- only
# one (S3) is actually what answers it; the rest range from loosely
# related (S4, employee-adjacent) to irrelevant (S0-S2, S5).
PASSAGES = [
    {"id": "S0", "text": "Ravi Sharma lives at 14 MG Road, Pune 411001."},
    {"id": "S1", "text": "Ravi Sharma works at ABC Pvt Ltd."},
    {"id": "S2", "text": "Meera Iyer lives at 22 Lake View Road, Chennai 600028."},
    {"id": "S3", "text": "The notice period for all employees is 30 days."},
    {"id": "S4", "text": "Employees must submit timesheets every Friday."},
    {"id": "S5", "text": "The office cafeteria serves lunch from 12 to 2pm."},
]


def _fetch_step(result: dict) -> dict | None:
    steps = [t for t in result["trace"] if t["step"] == "connector_fetch"]
    return steps[0] if steps else None


def _evict_step(result: dict) -> dict | None:
    steps = [t for t in result["trace"] if t["step"] == "working_set_evict"]
    return steps[0] if steps else None


def main() -> None:
    run = Run("EXP-101", "exp_101_working_set_wiring")
    store_dir = run.out_dir / "stores"
    shutil.rmtree(store_dir, ignore_errors=True)

    Store("employees", base_dir=store_dir).build(PASSAGES, use_bge=False)
    store = Store("employees", base_dir=store_dir).load()

    no_budget = reason(ASK, [], connector=store, connector_top_k=6)
    capped = reason(ASK, [], connector=store, connector_top_k=6, working_set_budget=2)
    # Same budget, but the caller also directly supplies one passage --
    # must survive untouched, since only connector-fetched passages are
    # ever subject to eviction.
    with_direct_passage = reason(ASK, [PASSAGES[5]], connector=store, connector_top_k=6, working_set_budget=2)

    no_budget_fetch = _fetch_step(no_budget)
    capped_fetch = _fetch_step(capped)
    capped_evict = _evict_step(capped)
    direct_fetch = _fetch_step(with_direct_passage)
    direct_evict = _evict_step(with_direct_passage)

    no_budget_correct = no_budget_fetch is not None and len(no_budget_fetch["added_passage_ids"]) == 6 and no_budget["decision"] == "supported"
    capped_correct = (
        capped_fetch is not None
        and len(capped_fetch["added_passage_ids"]) <= 2
        and "S3" in capped_fetch["added_passage_ids"]
        and capped_evict is not None
        and len(capped_evict["dropped_passage_ids"]) == 4
        and capped["decision"] == "supported"
        and "30 days" in capped["text"]
    )
    # S5 was supplied directly, so it must never appear in either the
    # connector's own fetch list or the eviction list -- it was never a
    # candidate for eviction in the first place.
    direct_passage_untouched = (
        direct_fetch is not None
        and "S5" not in direct_fetch["added_passage_ids"]
        and (direct_evict is None or "S5" not in direct_evict["dropped_passage_ids"])
        and with_direct_passage["decision"] == "supported"
    )

    metrics = {
        "no_budget": {"decision": no_budget["decision"], "fetched_count": len(no_budget_fetch["added_passage_ids"]) if no_budget_fetch else 0, "correct": no_budget_correct},
        "capped_budget_2": {
            "decision": capped["decision"],
            "text": capped["text"],
            "fetched": capped_fetch["added_passage_ids"] if capped_fetch else None,
            "evicted": capped_evict["dropped_passage_ids"] if capped_evict else None,
            "correct": capped_correct,
        },
        "direct_passage_survives_eviction": {
            "decision": with_direct_passage["decision"],
            "fetched": direct_fetch["added_passage_ids"] if direct_fetch else None,
            "evicted": direct_evict["dropped_passage_ids"] if direct_evict else None,
            "correct": direct_passage_untouched,
        },
    }
    run.write_json("items.json", metrics)

    all_correct = no_budget_correct and capped_correct and direct_passage_untouched

    prose = (
        f"No budget (today's default, unchanged): connector fetches all {metrics['no_budget']['fetched_count']} "
        f"of 6 candidate passages, decision={no_budget['decision']!r}. working_set_budget=2: only "
        f"{len(metrics['capped_budget_2']['fetched'] or [])} survive ({metrics['capped_budget_2']['fetched']}), "
        f"{len(metrics['capped_budget_2']['evicted'] or [])} evicted ({metrics['capped_budget_2']['evicted']}) -- "
        f"the actually-relevant passage (S3) survives, the answer is still correct: "
        f"{metrics['capped_budget_2']['text']!r}. Same budget, with one passage (S5) supplied directly by the "
        f"caller instead of through the connector: S5 appears in neither the fetch nor the eviction list "
        f"({metrics['direct_passage_survives_eviction']['correct']}) -- confirming only connector-fetched "
        f"passages are ever subject to eviction, never what the caller directly supplied."
    )

    conclusion = (
        "lab.common.paged.WorkingSet is now wired into lab.common.brain.reason (working_set_budget=, default "
        "None, zero regression for every existing caller) as a real cap on how many passages a connector can "
        "add to a single reasoning pass: without it, a connector's fetch grows passages unboundedly; with it, "
        "only the budget's worth of most ask-relevant hits survive, least-relevant-first eviction, and the "
        "answer is still correctly produced from the surviving relevant passage. Passages the caller supplies "
        "directly are never subject to this eviction at all, by construction (only new_passages from the "
        "connector fetch are ever passed through WorkingSet), not just by coincidence on this fixture."
        if all_correct
        else "At least one case did not behave as expected -- see metrics for exactly which, reported as "
        "measured, not assumed to work."
    )

    run.finish(
        title="lab.common.paged.WorkingSet wired into brain.reason as working_set_budget, capping connector-fetched passages only",
        goal=(
            "Give lab.common.paged.WorkingSet -- a confirmed-dormant module matching the project owner's own "
            "'brain RAM, not bounded by context length' architecture question -- its first real wiring into "
            "the live reasoning path, closing the concrete gap a connector (EXP-099) exposes: nothing today "
            "bounds how many passages a single connector fetch can add to a reasoning pass."
        ),
        method=(
            "A six-passage Store collection where only one passage actually answers the ask, the rest ranging "
            "from loosely related to irrelevant. Three reason() calls: no budget (today's default, all six "
            "fetched); working_set_budget=2 (checking eviction fires, the relevant passage survives, and the "
            "answer is still correct); and the same budget with one passage supplied directly by the caller "
            "alongside the connector (checking that directly-supplied passages are never eviction candidates)."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="Six passages, one collection, budget=2 -- a proof the wiring works end to end and correctly scopes eviction to connector-fetched passages only, not a capacity benchmark at corpus scale.",
        referenced_files=FILES,
        follow_ups=[
            "Only wired at the one connector-fetch point in _reason_once -- the deeper scoped/graph_expand passage accumulation further into the function is not capped by this parameter at all, and was deliberately left untouched (see this module's own docstring for why); a document with a very large entity-graph expansion could still grow scoped without a budget.",
            "lab.common.paged.Notebook (sub-question row tracking, the other half of EXP-015) is still unwired -- this exploration only wires WorkingSet; Notebook's own purpose (tracking per-subquestion coverage) could parallel plan_stages' existing subquestions field, untested here.",
            "Relevance is ask_relevance's lexical coverage score, the same scale-down every other lexical-overlap gate in this repo already carries (a true paraphrase with no shared word stems scores low) -- untested against a connector with strong dense-only hits that a lexical score would undervalue.",
        ],
        models_used="None -- WorkingSet's eviction is deterministic; ask_relevance (lexical coverage) drives the relevance score, no model of any kind.",
    )

    print("no_budget_correct:", no_budget_correct, "capped_correct:", capped_correct, "direct_passage_untouched:", direct_passage_untouched)
    print("ALL CORRECT:", all_correct)


if __name__ == "__main__":
    main()
