"""EXP-066: the unified brain navigates a hierarchical document too, through
the identical entry point EXP-060 already proved for flat documents.

EXP-060 proved lab.common.brain.reason handles plain lookups, rule
application, and flat multi-story disambiguation through one function call.
EXP-065 proved hierarchical (chapter/section) navigation works standalone.
This wires the two together and proves it end to end: the same
brain.reason(ask, passages) call, given passages tagged with a "hierarchy"
dict instead of a flat "group" string, navigates the structure
(lab.common.nested_index), resolves to the right section, then runs the
identical identity/arithmetic/rule-application signals EXP-058 already
measured on a flat document -- nothing at the call site tells it the
document is structured differently.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run

FILES = [
    "lab/exp_066_brain_nested_navigation/run.py",
    "lab/common/brain.py",
    "lab/common/nested_index.py",
    "lab/common/index.py",
    "lab/common/harness.py",
    "data/exp_058_integrated_scenario/results.json",
    "data/exp_060_unified_brain/results.json",
    "data/exp_065_nested_navigation/results.json",
    "data/exp_066_brain_nested_navigation/results.json",
]

PASSAGES = [
    {"id": "A1", "hierarchy": {"chapter": "Employees", "section": "Ravi"}, "text": "Ravi Sharma lives at 14 MG Road, Pune 411001."},
    {"id": "A2", "hierarchy": {"chapter": "Employees", "section": "Ravi"}, "text": "Ravi works as a sales manager at ABC Pvt Ltd."},
    {"id": "A3", "hierarchy": {"chapter": "Employees", "section": "Ravi"}, "text": "In January, Ravi received a salary of INR 40000."},
    {"id": "A4", "hierarchy": {"chapter": "Employees", "section": "Ravi"}, "text": "In February, he received a performance bonus of INR 5000."},
    {"id": "B1", "hierarchy": {"chapter": "Contractors", "section": "Priya"}, "text": "Priya Nair resides at 9 Residency Road, Bengaluru 560001."},
    {"id": "B2", "hierarchy": {"chapter": "Contractors", "section": "Priya"}, "text": "Priya is a contractor for Zenith Corp."},
    {"id": "B3", "hierarchy": {"chapter": "Contractors", "section": "Priya"}, "text": "In March, Priya billed consulting fees of INR 25000."},
    {"id": "B4", "hierarchy": {"chapter": "Contractors", "section": "Priya"}, "text": "In April, Priya filed a travel reimbursement claim for INR 15000."},
    {"id": "POLICY", "text": "Company policy: if a contractor's total billed amount in a quarter exceeds INR 30000, the payment requires finance head approval."},
]

CASES = [
    {
        "id": "H01_contractor",
        "ask": "A contractor filed a reimbursement claim in April. Who is involved, what is their name and address, how much money do they have in total this quarter, and does company policy require approval?",
        "expect_decision": "supported",
        "expect_contains": "Priya Nair",
        "expect_section": "Priya",
    },
    {
        "id": "H02_off_topic",
        "ask": "What is the weather forecast for tomorrow?",
        "expect_decision": "inconclusive",
        "expect_contains": None,
        "expect_section": None,
    },
]


def main():
    run = Run("EXP-066", "exp_066_brain_nested_navigation")
    rows = []
    for case in CASES:
        result = reason(case["ask"], PASSAGES)
        nav_step = next((t for t in result["trace"] if t["step"] == "nested_navigate"), None)
        resolved_section = None
        if nav_step and nav_step["path"]:
            section_hop = next((h for h in nav_step["path"] if h["level"] == "section"), None)
            resolved_section = section_hop["chosen"] if section_hop else None
        contains_ok = case["expect_contains"] is None or (case["expect_contains"].lower() in result["text"].lower())
        rows.append(
            {
                "id": case["id"],
                "ask": case["ask"],
                "decision": result["decision"],
                "text": result["text"],
                "resolved_section": resolved_section,
                "trace_steps": [t["step"] for t in result["trace"]],
                "correct_decision": result["decision"] == case["expect_decision"],
                "correct_content": contains_ok,
                "correct_section": resolved_section == case["expect_section"],
            }
        )
    run.write_json("items.json", rows)

    n = len(rows)
    correct = sum(r["correct_decision"] and r["correct_content"] and r["correct_section"] for r in rows)

    metrics = {
        "n": n,
        "accuracy": round(correct / n, 4),
        "cases": [{"id": r["id"], "decision": r["decision"], "resolved_section": r["resolved_section"], "correct": r["correct_decision"] and r["correct_content"] and r["correct_section"]} for r in rows],
    }

    headline = rows[0]
    prose = (
        f"On {n} cases through the identical brain.reason(ask, passages) call EXP-060 used for flat "
        f"documents, {correct} are fully correct. The contractor case resolves to section "
        f"{headline['resolved_section']!r} via nested navigation, then runs identity extraction, arithmetic, "
        f"and policy rule application exactly as EXP-058 measured on a flat-tagged version of the same "
        f"scenario: {headline['text']!r}. The off-topic case correctly abstains rather than guessing a "
        f"section: decision {rows[1]['decision']!r}."
    )

    conclusion = (
        "The unification EXP-060 proved for flat documents carries over to hierarchical ones without any "
        "change at the call site: the same function, given passages tagged with a 'hierarchy' dict instead "
        "of a flat 'group' string, navigates the structure (lab.common.nested_index, EXP-065's near-zero "
        "abstention floor included) and then runs the identical downstream signals (identity, arithmetic, "
        "rule application) EXP-058 already measured. A caller never needs to know or declare whether the "
        "document it's handing brain.reason is flat or structured -- the passages' own tags decide, the "
        "same 'input decides how much of the machinery runs' principle EXP-060 established for the simpler "
        "signals now extends to document structure itself."
    )

    run.finish(
        title="The unified brain navigates a hierarchical document",
        goal=(
            "Prove lab.common.brain.reason handles a hierarchically-structured document (chapter/section "
            "tags) through the same entry point and call shape EXP-060 proved for flat documents, chaining "
            "nested navigation (EXP-065) into the identity/arithmetic/rule-application signals EXP-058 "
            "already measured."
        ),
        method=(
            "Two cases through brain.reason(ask, passages), passages tagged with a 'hierarchy' dict "
            "({'chapter':..., 'section':...}) instead of EXP-058/060's flat 'group' string. Case 1 "
            "restates EXP-058's contractor scenario with 2-level hierarchy tags instead of flat ones. "
            "Case 2 is an off-topic ask with no real match in the document, testing that EXP-065's "
            "near-zero abstention floor correctly propagates through brain.reason rather than producing a "
            "confident wrong answer."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="2 cases, 2-level hierarchy, 9 passages -- a wiring proof, not a scale test (EXP-065 already measured scale up to 450 leaves for the navigation mechanism alone).",
        referenced_files=FILES,
        follow_ups=[
            "Extend lab.common.brain's flat ('group') disambiguation branch with the same near-zero "
            "abstention floor nested navigation now has, so a flat off-topic ask also abstains instead of "
            "guessing (EXP-065's follow-up, not yet carried to the flat path).",
            "Test a 3-level hierarchy (chapter/section/paragraph) through brain.reason, not just the "
            "2-level case here.",
        ],
        models_used="No generative model. Every step is a previously-measured classical/deterministic primitive; this exploration only chains them through the existing single entry point.",
    )


if __name__ == "__main__":
    main()
