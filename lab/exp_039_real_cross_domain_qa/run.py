"""EXP-039: cross-domain QA rerun with the real DeBERTa-v3 SQuAD2 checkpoint.

Re-measures EXP-014's per-domain extractive accuracy (software, recipes,
sports, finance, medical, legal -- 4 items each) with
lab.common.real_encoders.real_qa in place of lab.common.qa.answer_question.
The reasoning-skills probes (comparison, counting, ordering, sum,
conditional) are deterministic code (lab/common/calc.py and a regex) and
are unaffected by which QA model is loaded; they are not rerun here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.real_encoders import QA_MODEL_NAME, real_qa
from lab.common.textutil import normalize

FILES = [
    "lab/exp_039_real_cross_domain_qa/run.py",
    "lab/common/real_encoders.py",
    "lab/common/harness.py",
    "data/exp_014_reasoning/results.json",
    "data/exp_039_real_cross_domain_qa/items.json",
    "data/exp_039_real_cross_domain_qa/results.json",
]

DOMAINS = {
    "software": [
        ("What is the retry count?", "The service retries 3 times.", "3"),
        ("What is the timeout?", "The timeout is 15 seconds.", "15 seconds"),
        ("Which port is documented?", "The service listens on port 8080.", "8080"),
        ("What does the flag do?", "The flag dry-run skips writes.", "skips writes"),
    ],
    "recipes": [
        ("How much salt is used?", "The recipe uses 7 grams of salt.", "7 grams"),
        ("How long is the bake?", "Bake the loaf for 35 minutes.", "35 minutes"),
        ("What temperature is stated?", "Heat the oven to 180 C.", "180 C"),
        ("How many eggs are required?", "The batter uses 2 eggs.", "2"),
    ],
    "sports": [
        ("What is the match length?", "The match length is 40 minutes.", "40 minutes"),
        ("How many players are on the field?", "Each side fields 11 players.", "11"),
        ("What is the overtime length?", "Overtime lasts 5 minutes.", "5 minutes"),
        ("How many substitutions are allowed?", "A team may make 3 substitutions.", "3"),
    ],
    "finance": [
        ("What is the interest rate?", "The note pays 7 percent.", "7 percent"),
        ("What is the fee?", "The transfer fee is USD 12.", "USD 12"),
        ("When is the coupon paid?", "The coupon is paid on 1 June 2024.", "1 June 2024"),
        ("What is the face value?", "The face value is INR 1000.", "INR 1000"),
    ],
    "medical": [
        ("What dose is printed?", "The leaflet says the dose is 40 mg.", "40 mg"),
        ("How often is the dose taken?", "Take the dose once daily.", "once daily"),
        ("What is the storage temperature?", "Store below 25 C.", "25 C"),
        ("How many tablets are in the pack?", "The pack contains 14 tablets.", "14"),
    ],
    "legal": [
        ("What is the notice period?", "The notice period is 30 days.", "30 days"),
        ("What is the deposit?", "The security deposit is INR 50000.", "INR 50000"),
        ("Who is the Lessee?", "Ravi Sharma (the Lessee) signed.", "Ravi Sharma"),
        ("What is the cure period?", "The cure period is 10 days.", "10 days"),
    ],
}


def main():
    run = Run("EXP-039", "exp_039_real_cross_domain_qa")
    domain_scores = {}
    saved = []
    for domain, pairs in DOMAINS.items():
        hits = []
        for question, passage, gold in pairs:
            qa = real_qa(question, passage)
            hit = bool(qa["answer"] and normalize(gold) in normalize(qa["answer"]))
            hits.append(hit)
            saved.append({"domain": domain, "question": question, "gold": gold, "span": qa["answer"], "hit": hit})
        domain_scores[domain] = round(sum(hits) / len(hits), 4)
    run.write_json("items.json", saved)

    values = list(domain_scores.values())
    gap = round(max(values) - min(values), 4) if values else None

    metrics = {
        "model": QA_MODEL_NAME,
        "per_domain_accuracy": domain_scores,
        "domain_gap": gap,
        "items_per_domain": 4,
    }

    exp014_path = ROOT / "data" / "exp_014_reasoning" / "results.json"
    exp014 = json.loads(exp014_path.read_text())["metrics"] if exp014_path.exists() else None
    if exp014:
        metrics["vs_exp_014_lexical_qa"] = {
            "exp_014_per_domain_accuracy": exp014["per_domain_accuracy"],
            "exp_039_per_domain_accuracy": domain_scores,
            "exp_014_domain_gap": exp014["domain_gap"],
            "exp_039_domain_gap": gap,
        }

    prose = (
        f"With {QA_MODEL_NAME}, per-domain accuracy on 4 items each: {domain_scores}. "
        f"The gap between the highest and lowest domain is {gap}. "
        + (f"EXP-014's lexical extractor scored: {exp014['per_domain_accuracy']} (gap {exp014['domain_gap']})." if exp014 else "")
    )

    run.finish(
        title="Cross-domain QA rerun with the real DeBERTa-v3 SQuAD2 checkpoint",
        goal="Re-measure EXP-014's per-domain extractive accuracy with deepset/deberta-v3-base-squad2 in place of the lexical extractor, on the identical 24 items across 6 domains.",
        method=(
            "Identical domains, questions, and passages as EXP-014. lab.common.real_encoders.real_qa "
            "replaces lab.common.qa.answer_question for the 24 single-passage items. The reasoning-skills "
            "probes (comparison, counting, ordering, sum, conditional) are deterministic code, unaffected by "
            "the QA model, and are not rerun here -- EXP-014's own numbers for those stand."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=(
            f"The real {QA_MODEL_NAME} checkpoint is loaded and measured on EXP-014's own items, not "
            "assumed. "
            + (
                "If the domain gap shrinks relative to EXP-014's lexical-extractor gap, that is evidence the "
                "real checkpoint's accuracy is less sensitive to a domain's wording than the hand-written "
                "lexical rules were; if it does not shrink, the remaining gap is a property of the questions "
                "themselves, not the extractor."
            )
        ),
        scale_down="Same 4 items in each of 6 domains EXP-014 used.",
        referenced_files=FILES,
        models_used=(
            f"{QA_MODEL_NAME}, a local checkpoint loaded with transformers (not an API call)."
        ),
    )


if __name__ == "__main__":
    main()
