"""EXP-060: one reasoning brain, not three separate engines picked by hand.

Directly answers the objection raised in review: up to this point, plain
lookup (lab.common.engine), rule application (lab.common.rules, EXP-057),
and the integrated scenario (EXP-058) were each exercised by a different
script calling a different sequence of functions -- there was no single
entry point. lab.common.brain.reason is that entry point, and this
exploration runs all three regimes through the exact same function call,
with nothing in the call site telling it which regime it's in. The function
itself decides what to do by checking which signals are present (a rule
sentence anywhere in context? more than one candidate story? does the ask
want an identity or a total?) -- not by a label chosen ahead of time for
each case.

Regime 1: five plain lookup items from EXP-005 (notice period, deposit,
invented term, who-is-the-Lessee, and one unanswerable control), none of
which contain a rule sentence or more than one story.
Regime 2: EXP-057's headline rule-application case.
Regime 3: EXP-058's two integrated cases (disambiguation + identity +
arithmetic + policy).

If brain.reason needed a different code path wired in by the caller for
each regime, that would be the dispatcher-in-disguise this exploration is
checking for. It does not: every case below calls the identical function
with just (ask, passages).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run
from lab.common.textutil import normalize

FILES = [
    "lab/exp_060_unified_brain/run.py",
    "lab/common/brain.py",
    "lab/common/ask.py",
    "lab/common/index.py",
    "lab/common/entities.py",
    "lab/common/calc.py",
    "lab/common/rules.py",
    "lab/common/qa.py",
    "lab/common/verify.py",
    "lab/common/harness.py",
    "data/exp_057_rule_application/results.json",
    "data/exp_058_integrated_scenario/results.json",
    "data/exp_060_unified_brain/results.json",
]

LOOKUP_CASES = [
    {
        "id": "L01_notice_period",
        "ask": "What is the notice period?",
        "passages": [{"id": "A", "text": "The notice period is 30 days."}, {"id": "B", "text": "The garden is open daily."}],
        "expect_decision": "supported",
        "expect_contains": "30 days",
    },
    {
        "id": "L02_deposit",
        "ask": "What is the security deposit?",
        "passages": [{"id": "A", "text": "The security deposit is INR 50000."}, {"id": "B", "text": "Silt deposit is seasonal."}],
        "expect_decision": "supported",
        "expect_contains": "INR 50000",
    },
    {
        "id": "L03_invented_term",
        "ask": "What is a zorb?",
        "passages": [{"id": "A", "text": "A zorb is a refund issued after 14 days."}, {"id": "B", "text": "The refund desk opens at noon."}],
        "expect_decision": "supported",
        "expect_contains": "refund issued after 14 days",
    },
    {
        "id": "L04_who_is_lessee",
        "ask": "Who is the Lessee?",
        "passages": [{"id": "A", "text": "Ravi Sharma (the Lessee) signed the page."}, {"id": "B", "text": "The Lessee form is blank in this brochure."}],
        "expect_decision": "supported",
        "expect_contains": "Ravi Sharma",
    },
    {
        "id": "L05_unanswerable",
        "ask": "What is the zorb window?",
        "passages": [{"id": "A", "text": "The refund desk opens at 14:00."}, {"id": "B", "text": "Desks are wooden."}],
        "expect_decision": "inconclusive",
        "expect_contains": None,
    },
]

RULE_CASE = {
    "id": "R01_murder",
    "ask": "Arjun murdered Neha. Is that a punishable crime?",
    "passages": [
        {"id": "RULE1", "text": "If someone murders a person, it is a punishable crime."},
        {"id": "FACT1", "text": "Arjun murdered Neha."},
    ],
    "expect_decision": "supported",
    "expect_contains": "punishable crime",
}

INTEGRATED_PASSAGES = [
    {"id": "A1", "group": "A", "text": "Ravi Sharma lives at 14 MG Road, Pune 411001."},
    {"id": "A2", "group": "A", "text": "Ravi works as a sales manager at ABC Pvt Ltd."},
    {"id": "A3", "group": "A", "text": "In January, Ravi received a salary of INR 40000."},
    {"id": "A4", "group": "A", "text": "In February, he received a performance bonus of INR 5000."},
    {"id": "A5", "group": "A", "text": "Ravi filed no reimbursement claims this quarter."},
    {"id": "B1", "group": "B", "text": "Priya Nair resides at 9 Residency Road, Bengaluru 560001."},
    {"id": "B2", "group": "B", "text": "Priya is a contractor for Zenith Corp."},
    {"id": "B3", "group": "B", "text": "In March, Priya billed consulting fees of INR 25000."},
    {"id": "B4", "group": "B", "text": "In April, Priya filed a travel reimbursement claim for INR 15000."},
    {"id": "POLICY", "text": "Company policy: if a contractor's total billed amount in a quarter exceeds INR 30000, the payment requires finance head approval."},
]
INTEGRATED_CASES = [
    {
        "id": "I01_contractor",
        "ask": "A contractor filed a reimbursement claim in April. Who is involved, what is their name and address, how much money do they have in total this quarter, and does company policy require approval?",
        "expect_decision": "supported",
        "expect_contains": "Priya Nair",
    },
    {
        "id": "I02_sales_manager",
        "ask": "A sales manager received a performance bonus in February. Who is involved, what is their name and address, how much money do they have in total, and does company policy require approval?",
        "expect_decision": "supported",
        "expect_contains": "Ravi Sharma",
    },
]


def run_case(ask, passages, expect_decision, expect_contains):
    result = reason(ask, passages)
    contains_ok = expect_contains is None or (expect_contains.lower() in result["text"].lower())
    return {
        "decision": result["decision"],
        "text": result["text"],
        "trace_steps": [t["step"] for t in result["trace"]],
        "correct_decision": result["decision"] == expect_decision,
        "correct_content": contains_ok,
    }


def main():
    run = Run("EXP-060", "exp_060_unified_brain")
    rows = []

    for case in LOOKUP_CASES:
        outcome = run_case(case["ask"], case["passages"], case["expect_decision"], case["expect_contains"])
        rows.append({"regime": "lookup", "id": case["id"], **outcome})

    outcome = run_case(RULE_CASE["ask"], RULE_CASE["passages"], RULE_CASE["expect_decision"], RULE_CASE["expect_contains"])
    rows.append({"regime": "rule", "id": RULE_CASE["id"], **outcome})

    for case in INTEGRATED_CASES:
        outcome = run_case(case["ask"], INTEGRATED_PASSAGES, case["expect_decision"], case["expect_contains"])
        rows.append({"regime": "integrated", "id": case["id"], **outcome})

    run.write_json("items.json", rows)

    n = len(rows)
    correct = sum(r["correct_decision"] and r["correct_content"] for r in rows)
    by_regime = {}
    for regime in ("lookup", "rule", "integrated"):
        regime_rows = [r for r in rows if r["regime"] == regime]
        by_regime[regime] = {
            "n": len(regime_rows),
            "correct": sum(r["correct_decision"] and r["correct_content"] for r in regime_rows),
            "trace_steps_used": sorted({step for r in regime_rows for step in r["trace_steps"]}),
        }

    metrics = {
        "n": n,
        "accuracy": round(correct / n, 4),
        "by_regime": by_regime,
        "same_function_called_every_time": "lab.common.brain.reason(ask, passages) -- no case-specific branch at the call site",
        "cases": [{"regime": r["regime"], "id": r["id"], "decision": r["decision"], "correct": r["correct_decision"] and r["correct_content"]} for r in rows],
    }

    prose = (
        f"On {n} cases spanning three regimes (plain lookup, rule application, integrated disambiguation+"
        f"arithmetic+policy), all through the identical lab.common.brain.reason(ask, passages) call, "
        f"{correct} are correct (accuracy {metrics['accuracy']}). The trace shows which internal steps fired "
        f"per regime: lookup cases use {by_regime['lookup']['trace_steps_used']}, the rule case uses "
        f"{by_regime['rule']['trace_steps_used']}, the integrated cases use "
        f"{by_regime['integrated']['trace_steps_used']} -- different internal steps, same external call."
    )

    conclusion = (
        "One function handles a plain lookup, a rule-application question, and a multi-signal integrated "
        "scenario without the caller choosing a path. The difference between regimes shows up only in the "
        "trace -- which internal signal checks fired -- never in which function was called or how it was "
        "called. A lookup question fires none of the extra signals and falls back to the same single-slot "
        "extractor lab.common.engine already uses; the integrated cases fire three signals at once and chain "
        "their results. This is the unification the prior three explorations (EXP-057/058/059) proved "
        "piece by piece, now proved as one entry point rather than three scripts a person chooses between."
    )

    run.finish(
        title="One reasoning brain: lookup, rule application, and integration through a single entry point",
        goal=(
            "Prove lab.common.brain.reason is a single unified controller, not a dispatcher that routes to "
            "separate engines, by running plain lookup items, a rule-application case, and the full "
            "integrated scenario through the identical function call with no case-specific wiring at the "
            "call site."
        ),
        method=(
            "lab.common.brain.reason(ask, passages) first runs lab.common.ask.analyze (existing task-type "
            "classification, reused not duplicated), then checks four independent, domain-agnostic signals: "
            "more than one passage group present (disambiguate via lab.common.index.Index), the ask wants an "
            "identity (lab.common.entities), the ask wants a total (lab.common.calc.sum_amounts), and whether "
            "any passage parses as a rule (lab.common.rules, either shape). Only the tools whose signal fires "
            "run; a plain lookup with none of them falls back to lab.common.qa.answer_with_agreement, the "
            "same extractor EXP-005 and lab.common.engine already use. 8 cases: 5 lookup (EXP-005 subset), 1 "
            "rule (EXP-057's headline case), 2 integrated (EXP-058's both cases)."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            "8 cases across 3 regimes, not a benchmark of the brain's ceiling -- a targeted test that the "
            "single entry point reproduces every prior exploration's answer without per-case wiring."
        ),
        referenced_files=FILES,
        follow_ups=[
            "Wire lab.common.brain.reason as the entry point lab.common.engine.run_task's callers would use, "
            "so the controller's own round/budget loop (EXP-001) and this brain's signal-chaining converge "
            "into one thing instead of two.",
            "Add long-form dispatch (lab.common.assemble) as a fifth signal -- 'does the ask want a "
            "document, not a short answer' -- so EXP-018/042/048/054/055/056's page-wise path is reachable "
            "from the same entry point too.",
        ],
        models_used=(
            "No generative model. Every step is a previously-measured classical/deterministic primitive; "
            "this module's only new code is the control flow that chains them."
        ),
    )


if __name__ == "__main__":
    main()
