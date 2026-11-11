"""EXP-099: lab.common.store.Store, wired into lab.common.brain.reason as a
RAG backend for the first time.

Store (auto-create-on-ingest, load-on-reuse on-disk index: lexical Index +
optional dense RealBgeIndex + optional entity graph, fused by Reciprocal
Rank Fusion) had zero real callers anywhere outside its own module before
this -- confirmed by grep, not assumed: the only other "Store"/"store" in
this repo is lab.common.entities.ExampleStore, an unrelated entity-
resolution feedback cache. The project owner's own description of the gap
("our system fetch data from these places... this data should also be
vectorised rag right, so system brain can work on it properly") named
exactly this: a persisted, vectorized index Store already builds, that
brain.reason never actually drew on.

The fix needed turned out to be zero new production code, not a new
integration: lab.common.brain.reason already has a generic, duck-typed
`connector` extension point (lab.common.connectors.fetch_context_passages)
built for QdrantConnector/GraphConnector, and its own docstring already
says "a future [connector] with the same `search(query, top_k) -> rows`
shape ... needs no change here." Store.search(query, top_k) already
returns exactly that shape (`[{"passage": {...}, "score": ...}, ...]`,
checked directly against lab.common.index.Index.search's row shape
before relying on it) -- so `reason(ask, passages, connector=a_store)`
already worked, untested and unnoticed, before this exploration. This is
that first test, not a new code path.
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
    "lab/exp_099_store_rag_wiring/run.py",
    "lab/common/store.py",
    "lab/common/brain.py",
    "lab/common/connectors.py",
    "data/exp_099_store_rag_wiring/results.json",
]

# A deliberately mixed small corpus -- two unrelated people, a policy
# fact, and a second Ravi fact -- so retrieval precision (does the right
# passage surface, not just any passage) is a real thing to measure, not
# a one-passage store where any retrieval trivially "works".
STORE_PASSAGES = [
    {"id": "S0", "text": "Ravi Sharma lives at 14 MG Road, Pune 411001."},
    {"id": "S1", "text": "Ravi Sharma works at ABC Pvt Ltd."},
    {"id": "S2", "text": "Meera Iyer lives at 22 Lake View Road, Chennai 600028."},
    {"id": "S3", "text": "The notice period for all employees is 30 days."},
]


def main() -> None:
    run = Run("EXP-099", "exp_099_store_rag_wiring")
    store_dir = run.out_dir / "stores"
    shutil.rmtree(store_dir, ignore_errors=True)

    # Build once (use_bge=True: the dense leg is the actual "vectorised"
    # part of the project owner's ask, fused with the lexical leg by RRF,
    # not a lexical-only store dressed up as RAG), then load it back as a
    # brand-new Store instance -- proving this is real on-disk
    # persistence a later process can reuse, not just an in-process
    # convenience object handed straight to reason().
    Store("notice_policy", base_dir=store_dir).build(STORE_PASSAGES, use_bge=True)
    store = Store("notice_policy", base_dir=store_dir).load()

    case1 = reason("What is the notice period?", [], connector=store, connector_top_k=2)
    case2 = reason("Where does Ravi Sharma live?", [], connector=store, connector_top_k=2)
    # Off-topic: the store has nothing relevant, so Store.search still
    # returns its (irrelevant) top-k -- this checks that brain.reason's
    # own grounding/abstention logic, not the connector, is what decides
    # whether an answer is supported, so a connector can never manufacture
    # false confidence just by always returning *something*.
    case3 = reason("What is the capital of France?", [], connector=store, connector_top_k=2)
    # Same ask as case1, but with no connector at all -- isolates that the
    # Store is what made case1 answerable, not some baseline capability
    # reason() already had with zero passages and zero connector.
    baseline_no_connector = reason("What is the notice period?", [], connector=None)

    def _fetched_ids(result: dict) -> list[str]:
        steps = [t for t in result["trace"] if t["step"] == "connector_fetch"]
        return steps[0]["added_passage_ids"] if steps else []

    case1_correct = case1["decision"] == "supported" and "30 days" in case1["text"] and "S3" in _fetched_ids(case1)
    case2_correct = case2["decision"] == "supported" and "14 MG Road" in case2["text"] and "S0" in _fetched_ids(case2)
    case3_correct = case3["decision"] in ("inconclusive", "ungrounded") and "Paris" not in case3["text"]
    baseline_correct = baseline_no_connector["decision"] != "supported"

    metrics = {
        "case1_notice_period": {"decision": case1["decision"], "text": case1["text"], "fetched_ids": _fetched_ids(case1), "correct": case1_correct},
        "case2_ravi_address": {"decision": case2["decision"], "text": case2["text"], "fetched_ids": _fetched_ids(case2), "correct": case2_correct},
        "case3_off_topic": {"decision": case3["decision"], "text": case3["text"], "fetched_ids": _fetched_ids(case3), "correct": case3_correct},
        "baseline_same_ask_no_connector": {"decision": baseline_no_connector["decision"], "text": baseline_no_connector["text"], "correct": baseline_correct},
    }
    run.write_json("items.json", metrics)

    all_correct = case1_correct and case2_correct and case3_correct and baseline_correct

    prose = (
        f"With a Store connector (dense+lexical, RRF-fused, reloaded fresh from disk): 'What is the notice "
        f"period?' -> decision={case1['decision']!r}, text={case1['text']!r} (fetched {metrics['case1_notice_period']['fetched_ids']}). "
        f"'Where does Ravi Sharma live?' -> decision={case2['decision']!r}, text={case2['text']!r} "
        f"(fetched {metrics['case2_ravi_address']['fetched_ids']}). Off-topic 'What is the capital of France?' "
        f"-> decision={case3['decision']!r} (fetched {metrics['case3_off_topic']['fetched_ids']}, none relevant, "
        f"correctly not used as grounding). Same notice-period ask with no connector at all -> "
        f"decision={baseline_no_connector['decision']!r} -- confirms the Store, not some pre-existing capability, "
        f"is what answered case1."
    )

    conclusion = (
        "lab.common.store.Store works as a lab.common.brain.reason RAG backend end to end, through the "
        "existing connector= extension point, with zero new production code: build once, reload from disk in a "
        "new Store instance, hand it to reason() as connector=, and the right passage is retrieved and cited "
        "correctly for two different asks, while an off-topic ask that retrieves only irrelevant passages is "
        "correctly NOT answered as supported -- the connector supplies candidates, reason()'s own grounding "
        "logic still decides what counts as evidence. The same ask with no connector at all does not answer, "
        "isolating the Store's real contribution rather than crediting it for something reason() could already "
        "do. This closes the one concrete, confirmed gap in the project owner's own architecture description: "
        "'our system fetch data from these places... this data should also be vectorised rag'."
        if all_correct
        else "At least one case did not behave as expected -- see metrics for exactly which, reported as "
        "measured, not assumed to work."
    )

    run.finish(
        title="lab.common.store.Store wired into brain.reason as a RAG connector, via the existing duck-typed connector= extension point",
        goal=(
            "Give lab.common.store.Store -- a confirmed-dormant, zero-real-caller module -- its first real "
            "regression test as brain.reason's actual RAG backend, closing the gap the project owner's own "
            "architecture description named: data fetched from an external source should be vectorized and "
            "retrievable by the brain, not re-supplied as direct passages on every call."
        ),
        method=(
            "Four small, mixed-topic passages built into a Store (lexical + dense bge leg, RRF-fused) and "
            "persisted to disk; a second, brand-new Store instance loads that same collection back (real "
            "persistence, not reuse of the in-process object) and is passed as reason()'s connector= argument "
            "with passages=[] -- forcing every answer to come from the connector, not from direct passages. "
            "Two on-topic asks (each needing a different one of two Ravi-related passages to be the one that "
            "actually surfaces), one off-topic ask (checking the connector's irrelevant top-k doesn't get "
            "treated as grounding), and one same-ask-no-connector baseline (isolating the Store's real effect)."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="Four passages, one collection, two real asks plus one off-topic and one baseline -- a proof the wiring works end to end, not a retrieval-quality benchmark at corpus scale (lab.common.store's own module docstring already covers the RRF-fusion design rationale separately).",
        referenced_files=FILES,
        follow_ups=[
            "Not yet exercised with Store's use_graph=True leg (entity-graph expansion) or Store.upsert's incremental-ingest path through reason() -- this exploration only proves the base build+load+search path.",
            "connector_top_k=2 was chosen to keep the fixture's retrieval precision meaningful (so the right passage has to actually outrank the other Ravi passage, not just be included among four); untested at the larger top_k a real multi-hundred-passage collection would use.",
            "No caller in this repo builds a Store from real documents yet (lab.common.ingest.chunk_document + Store.build/ingest_and_store exist and are callable, but nothing in lab/ does this outside this exploration's own fixture) -- the next real step is a caller that ingests an actual document into a Store collection before any ask arrives, rather than building fixture passages inline.",
        ],
        models_used="bge-small-en-v1.5 (lab.common.real_encoders, Store's dense leg) -- non-generative similarity scoring only; brain.reason's own classical lookup path answers from the retrieved passages, same as every other direct-passages caller.",
    )

    print("case1:", case1["decision"], case1_correct)
    print("case2:", case2["decision"], case2_correct)
    print("case3:", case3["decision"], case3_correct)
    print("baseline:", baseline_no_connector["decision"], baseline_correct)
    print("ALL CORRECT:", all_correct)


if __name__ == "__main__":
    main()
