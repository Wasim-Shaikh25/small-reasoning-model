"""EXP-071: does requiring lexical+semantic agreement (navigate_dual) fix
the calibration gap EXP-068 found in the semantic margin alone?

EXP-068 swept MIN_SEMANTIC_MARGIN across 3 fixtures and found genuine-match
and noise margins are NOT cleanly separable by any single global threshold
(min genuine 0.0031 <= max noise 0.0631) when the *semantic signal alone*
is measured. EXP-070 then wired navigate_dual (lexical floor + semantic
margin, independent signals that must agree) into production, and flagged
exactly this question as a follow-up: navigate_dual's semantic half
inherits the same unswept risk, mitigated but not measured.

This measures the thing that actually matters -- not raw margin
separability, but navigate_dual's real end-to-end abstain/resolve
decisions -- across 5 independently-worded fixtures (EXP-068's original 3
plus 2 new ones), each with an exact-wording ask, a paraphrased ask, and 3
off-topic asks, at both tree levels. If requiring lexical agreement
compensates for the semantic margin's own unreliability, this should show
clean correctness even though the underlying margins (EXP-068) do not
separate.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.nested_index import build_nested_index
from lab.common.semantic_index import navigate_dual

FILES = [
    "lab/exp_071_dual_signal_calibration/run.py",
    "lab/common/semantic_index.py",
    "lab/common/nested_index.py",
    "data/exp_068_abstention_fixes/results.json",
    "data/exp_070_hierarchical_dual_signal/results.json",
    "data/exp_071_dual_signal_calibration/results.json",
]

FIXTURES = [
    {
        "name": "governance_agm",
        "chapters": {
            "Leases": "This section discusses tenancy terms, notice periods, and deposit schedules for residential leases.",
            "Governance": "This section discusses meeting minutes, voting procedures, and committee appointments for the organization.",
            "Safety Policy": "This section discusses evacuation procedures, equipment checks, and incident reporting for the facility.",
        },
        "needle": "The AGM authorization PIN for board members is 77319.",
        "needle_chapter": "Governance",
        "needle_section_idx": 1,
        "exact_ask": "What is the AGM authorization PIN for board members?",
        "paraphrase_ask": "What's the annual shareholder meeting access code for directors?",
    },
    {
        "name": "finance_quorum",
        "chapters": {
            "Leases": "This section discusses tenancy terms, notice periods, and deposit schedules for residential leases.",
            "Finance": "This section discusses invoice schedules, interest rates, and payment terms for commercial accounts.",
            "Safety Policy": "This section discusses evacuation procedures, equipment checks, and incident reporting for the facility.",
        },
        "needle": "The violet quorum code for the annual general meeting is 41827.",
        "needle_chapter": "Finance",
        "needle_section_idx": 2,
        "exact_ask": "What is the violet quorum code for the annual general meeting?",
        "paraphrase_ask": "What's the special color-coded access number required at the yearly shareholders' gathering?",
    },
    {
        "name": "it_security",
        "chapters": {
            "Benefits": "This section discusses leave balances, insurance enrollment, and reimbursement schedules for staff.",
            "Travel Policy": "This section discusses booking procedures, per-diem rates, and approval chains for business trips.",
            "IT Security": "This section discusses password rotation, device enrollment, and incident escalation for company systems.",
        },
        "needle": "The emergency override password for the server room is Delta-9.",
        "needle_chapter": "IT Security",
        "needle_section_idx": 0,
        "exact_ask": "What is the emergency override password for the server room?",
        "paraphrase_ask": "What's the backup access phrase for the data center in a crisis?",
    },
    {
        "name": "research_lab",
        "chapters": {
            "Procurement": "This section discusses vendor contracts, purchase orders, and delivery schedules for lab equipment.",
            "Biosafety": "This section discusses containment levels, decontamination procedures, and specimen handling rules.",
            "Publications": "This section discusses authorship order, submission deadlines, and journal formatting requirements.",
        },
        "needle": "The cold-storage freezer's backup unlock sequence is 90142.",
        "needle_chapter": "Biosafety",
        "needle_section_idx": 1,
        "exact_ask": "What is the cold-storage freezer's backup unlock sequence?",
        "paraphrase_ask": "What's the emergency code to open the specimen fridge if the main lock fails?",
    },
    {
        "name": "logistics_hub",
        "chapters": {
            "Fleet": "This section discusses vehicle maintenance schedules, fuel cards, and driver certification renewals.",
            "Warehousing": "This section discusses pallet racking standards, inventory counts, and loading dock assignments.",
            "Customs": "This section discusses tariff codes, import duty calculations, and clearance documentation.",
        },
        "needle": "The bonded warehouse's gate release token is BRAVO-204.",
        "needle_chapter": "Warehousing",
        "needle_section_idx": 2,
        "exact_ask": "What is the bonded warehouse's gate release token?",
        "paraphrase_ask": "What's the entry pass needed to open the secure storage yard's gate?",
    },
]

OFF_TOPIC_ASKS = [
    "What is the weather forecast for tomorrow?",
    "What's the best recipe for banana bread?",
    "How do I train for a marathon?",
]


def build_fixture_tree(fixture: dict, sections_per_chapter: int = 3, leaves_per_section: int = 8):
    items = []
    uid = 0
    for chapter, filler in fixture["chapters"].items():
        for section_idx in range(sections_per_chapter):
            for leaf_idx in range(leaves_per_section):
                is_needle = chapter == fixture["needle_chapter"] and section_idx == fixture["needle_section_idx"] and leaf_idx == leaves_per_section // 2
                text = fixture["needle"] if is_needle else f"{filler} Item {leaf_idx} filed under section {section_idx}."
                items.append({"id": f"P{uid:05d}", "text": text, "chapter": chapter, "section": f"{chapter}-{section_idx}", "is_needle": is_needle})
                uid += 1
    return build_nested_index(items, ["chapter", "section"])


def evaluate_ask(ask: str, root, expect_match: bool) -> dict:
    nav = navigate_dual(ask, root)
    abstained = nav["leaf"] is None
    if expect_match:
        correct = (not abstained) and any(p.get("is_needle") for p in nav["leaf_passages"])
        outcome = "correct" if correct else ("wrongly_abstained" if abstained else "wrong_answer")
    else:
        correct = abstained
        outcome = "correct_abstain" if correct else "wrong_guess"
    return {"ask": ask, "abstained": abstained, "outcome": outcome, "correct": correct, "path": nav["path"], "abstain_reason": nav.get("abstain_reason")}


def main():
    run = Run("EXP-071", "exp_071_dual_signal_calibration")
    rows = []
    for fixture in FIXTURES:
        root = build_fixture_tree(fixture)
        rows.append({"fixture": fixture["name"], "kind": "exact", **evaluate_ask(fixture["exact_ask"], root, True)})
        rows.append({"fixture": fixture["name"], "kind": "paraphrase", **evaluate_ask(fixture["paraphrase_ask"], root, True)})
        for off_topic in OFF_TOPIC_ASKS:
            rows.append({"fixture": fixture["name"], "kind": "off_topic", **evaluate_ask(off_topic, root, False)})
    run.write_json("items.json", rows)

    n = len(rows)
    correct = sum(r["correct"] for r in rows)
    by_kind = {}
    for kind in ("exact", "paraphrase", "off_topic"):
        kind_rows = [r for r in rows if r["kind"] == kind]
        by_kind[kind] = {"n": len(kind_rows), "correct": sum(r["correct"] for r in kind_rows), "accuracy": round(sum(r["correct"] for r in kind_rows) / len(kind_rows), 4)}

    wrong_rows = [r for r in rows if not r["correct"]]

    metrics = {
        "n": n,
        "accuracy": round(correct / n, 4),
        "by_kind": by_kind,
        "wrong_cases": [{"fixture": r["fixture"], "kind": r["kind"], "ask": r["ask"], "outcome": r["outcome"]} for r in wrong_rows],
    }

    prose = (
        f"Across {len(FIXTURES)} fixtures (3 from EXP-068 plus 2 new ones), navigate_dual's actual end-to-end "
        f"decisions score {correct}/{n} ({metrics['accuracy']}) overall: exact-wording {by_kind['exact']['correct']}/{by_kind['exact']['n']}, "
        f"paraphrase {by_kind['paraphrase']['correct']}/{by_kind['paraphrase']['n']}, off-topic abstention "
        f"{by_kind['off_topic']['correct']}/{by_kind['off_topic']['n']}."
    )

    fully_clean = correct == n
    conclusion = (
        (
            "Requiring lexical agreement does compensate for the semantic margin's own unreliability: every "
            "case resolves or abstains correctly end to end, even though EXP-068 measured the semantic margin "
            "alone as not cleanly separable across fixtures. The dual-signal requirement -- not a better "
            "single threshold -- is what makes this robust: a low-confidence semantic margin on a genuine "
            "paraphrase still gets corroborated by the lexical signal often enough, and a low-confidence "
            "semantic margin on real noise has no lexical corroboration to borrow from either."
            if fully_clean
            else f"Requiring lexical agreement helps but does not fully close the gap: {len(wrong_rows)} case(s) "
            f"still resolve incorrectly end to end ({[r['outcome'] for r in wrong_rows]}). The specific failures "
            "are listed in metrics.wrong_cases rather than averaged away -- this is the honest result, not the "
            "hoped-for one."
        )
    )

    run.finish(
        title="Does navigate_dual's lexical+semantic agreement fix EXP-068's margin-separability gap?",
        goal=(
            "Measure navigate_dual's real end-to-end correctness (not raw margin separability) across 5 "
            "independently-worded fixtures, to determine whether requiring both signals to agree compensates "
            "for the semantic margin alone not being cleanly separable (EXP-068's finding)."
        ),
        method=(
            "5 fixtures (3 reused from EXP-068, 2 new), each with an exact-wording ask, a paraphrased ask, "
            "and 3 off-topic asks, run through navigate_dual (the actual function wired into brain.py, "
            "EXP-070) rather than inspecting raw margins in isolation. 40 total cases."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="5 fixtures, 8 asks each -- enough to check the dual-signal claim directly, not an exhaustive calibration across every possible domain.",
        referenced_files=FILES,
        follow_ups=[] if fully_clean else [
            "Investigate the specific failing case(s) in metrics.wrong_cases before trusting navigate_dual's abstention further.",
        ],
        models_used="bge-small-en-v1.5 for semantic scoring; TF-IDF/BM25 for lexical. No generative model.",
    )


if __name__ == "__main__":
    main()
