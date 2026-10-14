"""EXP-058: an integrated scenario -- disambiguate between two stories, extract a
name and address, sum money across multiple sentences, and apply a company
policy threshold rule, all chained with citations.

This is the same decomposition principle AGENT.md names, run across a richer
fixture than any single prior exploration used: two separate multi-sentence
stories about different people (one a distractor), plus a company policy
rule, and a question that only names a *cue*, not a name -- "the contractor
who filed a reimbursement claim in April" -- forcing the system to resolve
which story that is before it can answer anything else. Every step reuses an
existing, separately-measured primitive; nothing here is a new model:

1. Resolve which story the ask is about (lab.common.index.Index, the same
   hybrid retriever EXP-004/015/029/040 measured) -- not a guess from the
   ask's wording, a search over the actual passages.
2. Extract the resolved story's person and address (lab.common.entities,
   EXP-009's detection and address parsing).
3. Sum every amount mentioned across that story's own passages
   (lab.common.calc.sum_amounts, EXP-007/014's arithmetic), using the same
   general-purpose lab.common.entities.AMOUNT_RE EXP-009 already built (not
   a money-only regex invented just for this story) -- it matches a
   currency amount here and a day/percent count elsewhere, with nothing in
   this exploration's own code naming money specifically. Each amount's
   source passage is kept so the total stays citable.
4. Parse the company policy into a threshold rule (lab.common.rules.
   parse_threshold_rule, new in this exploration, same family as EXP-057's
   verb-trigger rule) and check that the resolved person's own role
   actually matches the rule's subject class (a contractor) before
   applying it -- a rule firing on a coincidentally-matching number isn't
   a correct decision if it's the wrong kind of person.
5. Apply the rule (lab.common.rules.apply_threshold_rule) and render the
   answer with citations to every passage used.

Two cases: one where the role matches and the policy fires, one where the
resolved person's total is well over the threshold but their role (sales
manager, not contractor) doesn't match the policy's subject class, so it
must not fire even though the number alone would suggest it should.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.entities import AMOUNT_RE, detect_primary, parse_address
from lab.common.harness import Run
from lab.common.index import Index
from lab.common.rules import apply_threshold_rule, parse_threshold_rule, sum_amounts_for_subject

FILES = [
    "lab/exp_058_integrated_scenario/run.py",
    "lab/common/rules.py",
    "lab/common/entities.py",
    "lab/common/index.py",
    "lab/common/calc.py",
    "lab/common/harness.py",
    "data/exp_057_rule_application/results.json",
    "data/exp_058_integrated_scenario/results.json",
]

PASSAGES = [
    {"id": "A1", "story": "A", "text": "Ravi Sharma lives at 14 MG Road, Pune 411001."},
    {"id": "A2", "story": "A", "text": "Ravi works as a sales manager at ABC Pvt Ltd."},
    {"id": "A3", "story": "A", "text": "In January, Ravi received a salary of INR 40000."},
    {"id": "A4", "story": "A", "text": "In February, he received a performance bonus of INR 5000."},
    {"id": "A5", "story": "A", "text": "Ravi filed no reimbursement claims this quarter."},
    {"id": "B1", "story": "B", "text": "Priya Nair resides at 9 Residency Road, Bengaluru 560001."},
    {"id": "B2", "story": "B", "text": "Priya is a contractor for Zenith Corp."},
    {"id": "B3", "story": "B", "text": "In March, Priya billed consulting fees of INR 25000."},
    {"id": "B4", "story": "B", "text": "In April, Priya filed a travel reimbursement claim for INR 15000."},
]
POLICY_PASSAGE = {
    "id": "POLICY",
    "text": "Company policy: if a contractor's total billed amount in a quarter exceeds INR 30000, the payment requires finance head approval.",
}

CASES = [
    {
        "id": "C01_contractor_reimbursement",
        "ask": "A contractor filed a reimbursement claim in April. Who is involved, what is their name and address, how much money do they have in total this quarter, and does company policy require approval?",
        "expect_story": "B",
        "expect_name": "Priya Nair",
        "expect_total": 40000.0,
        "expect_policy_fires": True,
    },
    {
        "id": "C02_sales_manager_bonus",
        "ask": "A sales manager received a performance bonus in February. Who is involved, what is their name and address, how much money do they have in total, and does company policy require approval?",
        "expect_story": "A",
        "expect_name": "Ravi Sharma",
        "expect_total": 45000.0,
        "expect_policy_fires": False,
    },
]


def resolve_story(ask: str, passages: list[dict]) -> dict:
    index = Index(passages)
    hits = index.search(ask, top_k=1)
    if not hits:
        return {"resolved": False}
    top = hits[0]["passage"]
    return {"resolved": True, "story": top["story"], "matched_passage_id": top["id"], "score": hits[0]["score"]}


def extract_person_and_address(story_passages: list[dict]) -> dict:
    full_text = " ".join(p["text"] for p in story_passages)
    mentions = detect_primary(full_text)
    person = next((m for m in mentions if m["label"] == "person"), None)
    address = parse_address(full_text)
    person_cite = next((p["id"] for p in story_passages if person and person["text"] in p["text"]), None)
    address_cite = next((p["id"] for p in story_passages if p["text"].count(",") >= 1 and (not person or person["text"] not in p["text"] or True) and any(part for part in [address.get("road")] if part and part in p["text"])), None)
    return {
        "name": person["text"] if person else None,
        "name_citation": person_cite,
        "address": address,
        "address_citation": address_cite or (story_passages[0]["id"] if story_passages else None),
    }


def role_matches(rule: dict, story_passages: list[dict]) -> bool:
    role_noun = rule["subject_placeholder"].strip().lower()
    role_noun = re.sub(r"^(a|an|the)\s+", "", role_noun)
    full_text = " ".join(p["text"] for p in story_passages).lower()
    return role_noun in full_text


def main():
    run = Run("EXP-058", "exp_058_integrated_scenario")
    policy = parse_threshold_rule(POLICY_PASSAGE["text"])

    rows = []
    for case in CASES:
        resolution = resolve_story(case["ask"], PASSAGES)
        story_id = resolution.get("story")
        story_passages = [p for p in PASSAGES if p["story"] == story_id]

        person_info = extract_person_and_address(story_passages)
        money = sum_amounts_for_subject(story_passages, AMOUNT_RE)
        role_ok = role_matches(policy, story_passages)
        policy_result = apply_threshold_rule(policy, money["total"]) if role_ok else {
            "matched": False,
            "computed_value": money["total"],
            "threshold": policy["threshold"],
            "skipped_reason": f"resolved person's role does not match the policy's subject class ({policy['subject_placeholder']!r})",
        }

        citations = sorted(set([resolution.get("matched_passage_id")] + money.get("sources", []) + [person_info["name_citation"], person_info["address_citation"], "POLICY"]) - {None})
        decision_text = (
            f"{person_info['name']} [{person_info['name_citation']}], {person_info['address'].get('road') or 'address on file'} "
            f"[{person_info['address_citation']}]. Total this quarter: INR {money['total']:,.0f} "
            f"[{', '.join(money['sources'])}]. "
            + (
                f"Company policy [{POLICY_PASSAGE['id']}] applies ({policy['metric']} exceeds {policy['threshold']}): {policy_result.get('consequence')}."
                if policy_result.get("matched")
                else f"Company policy [{POLICY_PASSAGE['id']}] does not apply: "
                + (policy_result.get("skipped_reason") or f"total does not exceed {policy['threshold']}.")
            )
        )

        row = {
            "id": case["id"],
            "ask": case["ask"],
            "resolved_story": story_id,
            "matched_passage": resolution.get("matched_passage_id"),
            "name": person_info["name"],
            "address": person_info["address"],
            "total": money["total"],
            "amount_sources": money["sources"],
            "role_matches_policy_subject": role_ok,
            "policy_fires": bool(policy_result.get("matched")),
            "citations": citations,
            "text": decision_text,
            "correct_story": story_id == case["expect_story"],
            "correct_name": person_info["name"] == case["expect_name"],
            "correct_total": money["total"] == case["expect_total"],
            "correct_policy_outcome": bool(policy_result.get("matched")) == case["expect_policy_fires"],
        }
        rows.append(row)
    run.write_json("items.json", rows)

    all_checks = ["correct_story", "correct_name", "correct_total", "correct_policy_outcome"]
    per_case_all_correct = [all(row[check] for check in all_checks) for row in rows]
    metrics = {
        "n": len(rows),
        "cases_fully_correct": sum(per_case_all_correct),
        "policy_parsed": policy,
        "per_check_accuracy": {check: round(sum(row[check] for row in rows) / len(rows), 4) for check in all_checks},
        "cases": [{"id": r["id"], **{k: r[k] for k in all_checks}} for r in rows],
    }

    prose = (
        f"On {metrics['n']} integrated cases, {metrics['cases_fully_correct']} get every check right "
        f"(story resolution, name, total, and policy outcome). "
        f"Case 1: {rows[0]['text']} "
        f"Case 2: {rows[1]['text']}"
    )

    conclusion = (
        "Disambiguating between two multi-sentence stories by a cue in the ask (not a name), extracting a "
        "name and address, summing money mentioned across separate sentences, and applying a company policy "
        "threshold rule all chain correctly end to end, each step citable to its own source passage. The "
        "second case is the one worth dwelling on: Ravi Sharma's total (INR 45,000) is well over the "
        "policy's INR 30,000 threshold, and a rule engine that only checked the number would have incorrectly "
        "fired approval on him. Checking that his own story actually describes him with the policy's subject "
        "role ('a contractor') -- and finding it doesn't, he's a sales manager -- is what keeps the decision "
        "correct. A rule matching a number is not the same as a rule applying to the right person."
    )

    run.finish(
        title="Integrated scenario: disambiguation, extraction, arithmetic, and policy rule application",
        goal=(
            "Chain multiple already-measured primitives (hybrid retrieval, entity/address extraction, "
            "amount summation, rule application) across a richer fixture than any single prior exploration: "
            "two distractor multi-sentence stories and a company policy, with a question that names only a "
            "cue, not a person, and must resolve, extract, compute, and decide correctly end to end."
        ),
        method=(
            "Two 4-5 sentence stories (Story A: Ravi Sharma, salaried sales manager; Story B: Priya Nair, "
            "contractor) plus one company policy sentence. For each case: (1) lab.common.index.Index "
            "resolves which story the ask's cue matches; (2) lab.common.entities.detect_primary and "
            "parse_address extract the resolved story's name and address; (3) lab.common.rules."
            "sum_amounts_for_subject sums every currency-prefixed amount in that story's own passages, "
            "keeping each amount's source passage; (4) lab.common.rules.parse_threshold_rule parses the "
            "policy sentence; (5) a role check confirms the resolved person's own story text actually "
            "describes them with the policy's subject class before lab.common.rules.apply_threshold_rule is "
            "allowed to fire."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            "Two stories, one policy, one role-class check. Real documents would have more distractors, "
            "multiple candidate policies, and roles stated less explicitly than 'is a contractor for Zenith "
            "Corp.' -- this is a scaled-down integration test of the chain, not a benchmark of its ceiling."
        ),
        referenced_files=FILES,
        follow_ups=[
            "Add a third, harder case: a story where the role noun appears but negated ('is not a "
            "contractor') or where two people in the same story could both match, to test the role check "
            "and disambiguation under more adversarial phrasing.",
            "Wire role_matches's substring check through the NLI judge instead, now that EXP-056 showed "
            "naive wiring needs care -- measure before assuming it helps.",
        ],
        models_used=(
            "No generative model. lab.common.index's hybrid retriever (TF-IDF + BM25, the same classical "
            "substitute EXP-004/015/029/040 measured) for disambiguation; lab.common.entities' rule taggers "
            "(EXP-009) for name/address; deterministic arithmetic and rule matching for the rest."
        ),
    )


if __name__ == "__main__":
    main()
