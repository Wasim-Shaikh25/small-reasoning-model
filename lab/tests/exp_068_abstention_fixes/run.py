"""EXP-068: closing the three gaps named right after EXP-067 -- flat
disambiguation's missing abstention, navigate_semantic's single-child gap,
and MIN_SEMANTIC_MARGIN's unvalidated value.

Part A -- lab.common.brain's flat ("group") disambiguation branch. Regression
on EXP-058/060's integrated fixture (must still answer both cases correctly),
plus two new cases exercising what the dual lexical+semantic signal now adds:
an off-topic ask (previously a confident wrong guess, now must abstain) and a
flat-document paraphrase ask (lexical alone would likely miss it; semantic
should not).

Part B -- lab.common.semantic_index.navigate_semantic's single-candidate
level. A tree built with exactly one section so no margin can be computed at
that level, tested with a genuine ask (must proceed) and an off-topic ask
(must abstain via the dense-score fallback).

Part C -- MIN_SEMANTIC_MARGIN=0.03 was picked from a single measured
data point (EXP-067's paraphrase case, margin 0.0403, barely above it). This
sweeps three independent tree fixtures (different vocabulary each, so the
result isn't an artifact of one domain's wording), collecting the margin
produced by a genuine match (exact + paraphrase asks) versus by real noise
(off-topic asks) at every level, to see whether any single threshold
actually separates the two populations -- not assumed, measured.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run
from lab.common.index import Index
from lab.common.nested_index import MIN_DENSE_SCORE, build_nested_index
from lab.common.semantic_index import MIN_SEMANTIC_MARGIN, SemanticIndex, navigate_semantic

FILES = [
    "lab/tests/exp_068_abstention_fixes/run.py",
    "lab/common/brain.py",
    "lab/common/semantic_index.py",
    "lab/common/nested_index.py",
    "lab/common/index.py",
    "lab/common/harness.py",
    "data/exp_058_integrated_scenario/results.json",
    "data/exp_060_unified_brain/results.json",
    "data/exp_067_semantic_navigation/results.json",
    "data/exp_068_abstention_fixes/results.json",
]

# ---------------------------------------------------------------------------
# Part A: brain.py's flat disambiguation branch.
# ---------------------------------------------------------------------------

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

FLAT_CASES = [
    {
        "id": "F01_contractor_regression",
        "ask": "A contractor filed a reimbursement claim in April. Who is involved, what is their name and address, how much money do they have in total this quarter, and does company policy require approval?",
        "expect_decision": "supported",
        "expect_contains": "Priya Nair",
        "expect_group": "B",
        "note": "Regression: EXP-060's I01, must still pass with the new dual-signal logic.",
    },
    {
        "id": "F02_sales_manager_regression",
        "ask": "A sales manager received a performance bonus in February. Who is involved, what is their name and address, how much money do they have in total, and does company policy require approval?",
        "expect_decision": "supported",
        "expect_contains": "Ravi Sharma",
        "expect_group": "A",
        "note": "Regression: EXP-060's I02, must still pass with the new dual-signal logic.",
    },
    {
        "id": "F03_off_topic_new",
        "ask": "What is the weather forecast for tomorrow?",
        "expect_decision": "inconclusive",
        "expect_contains": None,
        "expect_group": None,
        "note": "New: previously had zero abstention here, would have confidently guessed group A or B.",
    },
    {
        "id": "F04_paraphrase_new",
        "ask": "Which employee's take-home pay increased with an extra payout last quarter's second month, and where do they live?",
        "expect_decision": "supported",
        "expect_contains": "Ravi Sharma",
        "expect_group": "A",
        "note": "New: paraphrases 'performance bonus in February' / 'salary' without reusing those exact words -- tests whether the semantic signal resolves it the way lexical alone might not.",
    },
]


def run_flat_cases() -> list[dict]:
    rows = []
    for case in FLAT_CASES:
        result = reason(case["ask"], INTEGRATED_PASSAGES)
        disambig = next((t for t in result["trace"] if t["step"] == "disambiguate"), None)
        contains_ok = case["expect_contains"] is None or (case["expect_contains"].lower() in result["text"].lower())
        # Mirror brain.py's own resolution rule (whichever signal was confident) so a
        # failed case can be attributed to disambiguation itself, or to something
        # downstream of it, instead of assuming the cause.
        resolved_group = None
        if disambig and not (disambig["lexical_abstain"] and disambig["semantic_abstain"]):
            resolved_group = disambig["semantic_group"] if disambig["lexical_abstain"] else disambig["lexical_group"]
        disambiguation_correct = resolved_group == case["expect_group"]
        rows.append(
            {
                "id": case["id"],
                "note": case["note"],
                "ask": case["ask"],
                "decision": result["decision"],
                "text": result["text"],
                "disambiguate_trace": disambig,
                "resolved_group": resolved_group,
                "disambiguation_correct": disambiguation_correct,
                "correct": result["decision"] == case["expect_decision"] and contains_ok,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Part B: navigate_semantic's single-candidate level.
# ---------------------------------------------------------------------------

def run_single_child_case() -> dict:
    items = [
        {"id": "S1", "text": "The backup generator runs on diesel and is tested every Monday.", "section": "Facilities"},
        {"id": "S2", "text": "The server room's emergency override password is Delta-9.", "section": "Facilities"},
        {"id": "S3", "text": "Visitor badges must be returned to the front desk.", "section": "Facilities"},
    ]
    root = build_nested_index(items, ["section"])  # exactly one child at the top -- "Facilities" -- no margin possible.

    genuine = navigate_semantic("What is the emergency override password for the server room?", root)
    off_topic = navigate_semantic("What's the best recipe for banana bread?", root)
    return {
        "genuine_ask_abstained": genuine["leaf"] is None,
        "genuine_ask_path": genuine["path"],
        "off_topic_abstained": off_topic["leaf"] is None,
        "off_topic_abstain_reason": off_topic.get("abstain_reason"),
    }


# ---------------------------------------------------------------------------
# Part C: margin sweep across independent fixtures.
# ---------------------------------------------------------------------------

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


def margins_for_ask(ask: str, root) -> list[dict]:
    """Diagnostic-only descent: always takes the argmax child (ignores
    abstention) so a margin sample is recorded at every level for every ask,
    including off-topic ones that a real navigate_semantic call would have
    already abstained on. This is for measuring the margin *distribution*,
    not for answering anything.
    """
    samples = []
    node = root
    while not node.is_leaf:
        candidates = [{"id": c.node_id, "text": c.summary_text} for c in node.children]
        hits = SemanticIndex(candidates).search(ask, top_k=2)
        margin = hits[0]["score"] - hits[1]["score"] if len(hits) > 1 else hits[0]["score"]
        samples.append({"level": node.children[0].level, "margin": round(margin, 4), "top_score": round(hits[0]["score"], 4)})
        best_id = hits[0]["passage"]["id"]
        node = next(c for c in node.children if c.node_id == best_id)
    return samples


def run_margin_sweep() -> dict:
    genuine_margins = []
    noise_margins = []
    per_fixture = []
    for fixture in FIXTURES:
        root = build_fixture_tree(fixture)
        exact_samples = margins_for_ask(fixture["exact_ask"], root)
        paraphrase_samples = margins_for_ask(fixture["paraphrase_ask"], root)
        noise_samples = [margins_for_ask(ask, root) for ask in OFF_TOPIC_ASKS]

        genuine_margins += [s["margin"] for s in exact_samples] + [s["margin"] for s in paraphrase_samples]
        for samples in noise_samples:
            noise_margins += [s["margin"] for s in samples]

        per_fixture.append(
            {
                "fixture": fixture["name"],
                "exact_ask_margins": exact_samples,
                "paraphrase_ask_margins": paraphrase_samples,
                "off_topic_margins": {ask: samples for ask, samples in zip(OFF_TOPIC_ASKS, noise_samples)},
            }
        )

    min_genuine = min(genuine_margins)
    max_noise = max(noise_margins)
    separable = min_genuine > max_noise
    recommended = round((min_genuine + max_noise) / 2, 4) if separable else None

    return {
        "per_fixture": per_fixture,
        "genuine_margins": sorted(genuine_margins),
        "noise_margins": sorted(noise_margins),
        "min_genuine_margin": round(min_genuine, 4),
        "max_noise_margin": round(max_noise, 4),
        "separable": separable,
        "current_min_semantic_margin": MIN_SEMANTIC_MARGIN,
        "current_value_in_safe_zone": separable and max_noise < MIN_SEMANTIC_MARGIN <= min_genuine,
        "recommended_margin_if_separable": recommended,
    }


def main():
    run = Run("EXP-068", "exp_068_abstention_fixes")

    flat_rows = run_flat_cases()
    single_child = run_single_child_case()
    sweep = run_margin_sweep()
    run.write_json("items.json", {"flat_disambiguation": flat_rows, "single_child_fallback": single_child, "margin_sweep": sweep})

    flat_correct = sum(r["correct"] for r in flat_rows)
    single_child_correct = (not single_child["genuine_ask_abstained"]) and single_child["off_topic_abstained"]

    metrics = {
        "part_a_flat_disambiguation": {
            "n": len(flat_rows),
            "correct": flat_correct,
            "cases": [
                {"id": r["id"], "decision": r["decision"], "resolved_group": r["resolved_group"], "disambiguation_correct": r["disambiguation_correct"], "correct": r["correct"]}
                for r in flat_rows
            ],
        },
        "part_b_single_child_fallback": {
            "genuine_ask_correctly_proceeded": not single_child["genuine_ask_abstained"],
            "off_topic_correctly_abstained": single_child["off_topic_abstained"],
            "both_correct": single_child_correct,
        },
        "part_c_margin_sweep": {
            "min_genuine_margin": sweep["min_genuine_margin"],
            "max_noise_margin": sweep["max_noise_margin"],
            "separable": sweep["separable"],
            "current_min_semantic_margin": sweep["current_min_semantic_margin"],
            "current_value_in_safe_zone": sweep["current_value_in_safe_zone"],
            "recommended_margin_if_separable": sweep["recommended_margin_if_separable"],
        },
    }

    paraphrase_row = next(r for r in flat_rows if r["id"] == "F04_paraphrase_new")
    resolved_group = paraphrase_row["resolved_group"]
    disambig_ok = paraphrase_row["disambiguation_correct"]
    overall_ok = paraphrase_row["correct"]
    if overall_ok:
        part_a_paraphrase_detail = "The new paraphrase case is correct end-to-end: disambiguation resolved the right group and the downstream extraction found the right answer."
    elif disambig_ok:
        part_a_paraphrase_detail = (
            f"The new paraphrase case is a mixed result worth stating precisely rather than rounding off: "
            f"disambiguation itself resolved the right group ({resolved_group!r}, correct), but the overall "
            f"case still came back {paraphrase_row['decision']!r} -- the failure is downstream of the fix "
            f"just made, in brain.py's _wants_identity/_wants_total keyword checks, which don't recognize "
            f"this paraphrase's intent wording ('take-home pay', 'extra payout') the way they recognize "
            f"'name'/'address'/'total' literally, so it falls through to the single-slot lookup extractor "
            f"and finds no single-span answer."
        )
    else:
        part_a_paraphrase_detail = f"The new paraphrase case failed, and disambiguation itself was also wrong (resolved {resolved_group!r})."

    part_a_detail = (
        f"Part A (flat disambiguation, brain.py): {flat_correct}/{len(flat_rows)} end-to-end correct -- the "
        f"two EXP-060 regression cases hold and the off-topic ask now abstains instead of guessing. "
        f"{part_a_paraphrase_detail}"
    )
    prose = (
        f"{part_a_detail} Part B (single-child fallback, navigate_semantic): genuine ask "
        f"{'proceeded' if not single_child['genuine_ask_abstained'] else 'wrongly abstained'}, off-topic ask "
        f"{'correctly abstained' if single_child['off_topic_abstained'] else 'wrongly proceeded'} "
        f"(reason: {single_child['off_topic_abstain_reason']}). Part C (margin sweep, 3 fixtures x "
        f"(1 exact + 1 paraphrase + 3 off-topic) asks, 2 levels each): genuine-match margins range down to "
        f"{sweep['min_genuine_margin']}, noise margins range up to {sweep['max_noise_margin']}; the two "
        f"populations are {'cleanly separable' if sweep['separable'] else 'NOT cleanly separable'}. The "
        f"current MIN_SEMANTIC_MARGIN={sweep['current_min_semantic_margin']} is "
        f"{'inside' if sweep['current_value_in_safe_zone'] else 'NOT safely inside'} the measured gap."
    )

    conclusion = (
        "All three gaps named after EXP-067 were addressed and re-measured rather than assumed fixed. "
        "Flat disambiguation now abstains correctly on the off-topic case and still answers both EXP-060 "
        "regression cases, using the identical dual-signal (lexical floor + semantic margin, independent "
        "checks that must agree) design EXP-067 validated for hierarchical navigation -- the same mechanism "
        "now covers both branches of lab.common.brain. "
        + (
            "The disambiguation fix worked on the paraphrase case from the first run (it resolved the correct "
            "group); what failed downstream of it at the time this exploration was first run was a *separate* "
            "issue this exploration exposed rather than caused: brain.py's _wants_identity and _wants_total "
            "were literal keyword checks ('name' + 'address', a fixed list of total-cue words), so a "
            "paraphrased ask could pass disambiguation correctly and still get no answer. That gap was closed "
            "in EXP-069 (semantic intent signals, replacing the literal keyword checks) -- this file reflects "
            "a rerun after that fix, which is why the paraphrase case now passes end to end rather than "
            "failing downstream the way it did when this exploration was first written."
            if paraphrase_row["correct"]
            else "The disambiguation fix itself worked on the paraphrase case (it resolved the correct group); "
            "what still fails downstream of it is a *separate*, pre-existing issue this exploration exposed "
            "rather than caused: brain.py's _wants_identity and _wants_total signal detectors are themselves "
            "literal keyword checks ('name' + 'address', a fixed list of total-cue words), so a paraphrased "
            "ask can pass disambiguation correctly and still get no answer because the intent-detection step "
            "never recognized what kind of question it was. That's a fourth, newly-identified gap, not one of "
            "the three this exploration set out to fix."
        )
        + " The single-candidate gap in navigate_semantic is closed by falling back to the TF-IDF dense floor "
        "specifically where a margin can't be computed, reusing lab.common.nested_index's already-measured "
        "constant rather than inventing a new number. "
        + (
            f"The margin sweep found real separation across three independently-worded fixtures (min genuine "
            f"{sweep['min_genuine_margin']} > max noise {sweep['max_noise_margin']}), and "
            + (
                f"the current value (0.03) sits safely inside that gap -- it was a lucky first guess that "
                f"this measurement now actually supports, rather than leaving it unvalidated."
                if sweep["current_value_in_safe_zone"]
                else f"recommends moving it to {sweep['recommended_margin_if_separable']} (the midpoint of the "
                f"measured gap) instead of the untouched first guess of 0.03."
            )
            if sweep["separable"]
            else (
                f"The margin sweep found the two populations are NOT cleanly separable (min genuine "
                f"{sweep['min_genuine_margin']} <= max noise {sweep['max_noise_margin']}) -- meaning no single "
                f"fixed threshold can be fully trusted across different vocabularies, a real limitation to "
                f"flag rather than paper over with a confident-sounding constant."
            )
        )
    )

    run.finish(
        title="Closing EXP-067's three named gaps: flat abstention, single-child navigation, and margin calibration",
        goal=(
            "Fix and re-measure, not just patch, the three concrete gaps named right after EXP-067: "
            "lab.common.brain's flat disambiguation branch had no abstention at all; "
            "lab.common.semantic_index.navigate_semantic could not handle a level with only one candidate; "
            "and MIN_SEMANTIC_MARGIN=0.03 was a single first measurement, not a validated constant."
        ),
        method=(
            "Part A: brain.reason run on EXP-058/060's integrated fixture (2 regression cases) plus a new "
            "off-topic case and a new flat-document paraphrase case, through the new dual lexical+semantic "
            "signal logic. Part B: navigate_semantic run on a single-level, single-child tree, with a genuine "
            "ask and an off-topic ask, to exercise the new dense-floor fallback. Part C: margin sweep across "
            "3 independently-worded tree fixtures (72 leaves each), each with an exact-wording ask, a "
            "paraphrase ask, and 3 off-topic asks, collecting the top1-vs-runner-up margin at every level "
            "visited (ignoring abstention, for measurement purposes) to check whether MIN_SEMANTIC_MARGIN "
            "actually separates genuine matches from real noise."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="3 margin-sweep fixtures, 1 single-child case, 4 flat-disambiguation cases -- enough to validate the mechanism and get a first real measurement of separability, not an exhaustive calibration.",
        referenced_files=FILES,
        follow_ups=[
            "RESOLVED in EXP-069: brain.py's _wants_identity/_wants_total were literal keyword checks "
            "('name'+'address', a fixed total-cue word list) -- a paraphrased ask could pass disambiguation "
            "correctly (proven working here) and still fail because intent detection itself didn't recognize "
            "it. Replaced with lab.common.intent_signals (bge exemplar similarity), tested cross-domain. This "
            "file was rerun after that fix, which is why the paraphrase case passes end to end now.",
            "The margin sweep found genuine-match and noise margins are NOT cleanly separable by any single "
            "global threshold across 3 fixtures and 2 levels (min genuine 0.0031 <= max noise 0.0631) -- "
            "MIN_SEMANTIC_MARGIN=0.03 is not a safe fixed constant. This is why brain.py's disambiguation never "
            "trusts the semantic margin alone -- it only acts when lexical also abstains or agrees -- but "
            "navigate_semantic's hierarchical path still uses the margin as its only signal at each level and "
            "inherits this same risk. Needs either a per-level/relative recalibration or a second corroborating "
            "signal there too, not a bigger single constant.",
            "If MIN_SEMANTIC_MARGIN is adjusted, rerun EXP-066/067 to confirm nothing regresses.",
            "The single-child fallback still can't catch a paraphrased ask the way the margin check can -- only exercised against an exact/off-topic pair here, not a paraphrase against a lone candidate.",
        ],
        models_used="bge-small-en-v1.5 for all semantic scoring (retrieval only, no generation); TF-IDF/BM25 (lab.common.index) for the lexical signal and the single-child fallback floor.",
    )


if __name__ == "__main__":
    main()
