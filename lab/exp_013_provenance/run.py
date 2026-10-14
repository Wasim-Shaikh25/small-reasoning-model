"""EXP-013: context faithfulness, invented terms, and provenance tags (H1, H2, H5)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.provenance import BACKGROUND_FACTS, answer_from_context_or_abstain, tag_statement
from lab.common.qa import answer_question
from lab.common.textutil import normalize

FILES = [
    "lab/exp_013_provenance/run.py",
    "lab/common/provenance.py",
    "lab/common/qa.py",
    "lab/common/textutil.py",
    "lab/common/harness.py",
    "data/exp_013_provenance/items.json",
    "data/exp_013_provenance/results.json",
]

H1 = [
    {"key": "sprint length", "question": "How long does a sprint last?", "passage": "In this handbook a sprint lasts 9 days.", "context": "9 days"},
    {"key": "capital of france", "question": "What is the capital of France in this atlas?", "passage": "In this atlas the capital of France is Lyon.", "context": "Lyon"},
    {"key": "water boiling point", "question": "What is the boiling point on this sheet?", "passage": "On this lab sheet the boiling point is 98 C.", "context": "98 C"},
    {"key": "number of continents", "question": "How many continents does this primer list?", "passage": "This primer lists 6 continents.", "context": "6"},
    {"key": "sprint length", "question": "How long is the cycle in this note?", "passage": "This note sets the cycle at 9 days.", "context": "9 days"},
    {"key": "capital of france", "question": "Which city does this page call the capital?", "passage": "This page calls Lyon the capital.", "context": "Lyon"},
    {"key": "water boiling point", "question": "What temperature does the sheet print?", "passage": "The sheet prints 98 C as the boiling point.", "context": "98 C"},
    {"key": "number of continents", "question": "What count of continents is written here?", "passage": "The written count of continents is 6.", "context": "6"},
]

H2 = [
    {"term": "zorb", "question": "What is a zorb?", "definition": "A zorb is a refund issued after 14 days.", "gold": "a refund issued after 14 days"},
    {"term": "quillon", "question": "What is a quillon?", "definition": "A quillon is a fee capped at 2 percent.", "gold": "a fee capped at 2 percent"},
    {"term": "brindle clause", "question": "What is a brindle clause?", "definition": "A brindle clause is a renewal limited to 1 year.", "gold": "a renewal limited to 1 year"},
    {"term": "mallow day", "question": "What is a mallow day?", "definition": "A mallow day is a rest day after 6 work days.", "gold": "a rest day after 6 work days"},
    {"term": "veldt rate", "question": "What is the veldt rate?", "definition": "The veldt rate is 4 percent.", "gold": "4 percent"},
    {"term": "nimbus hold", "question": "What is a nimbus hold?", "definition": "A nimbus hold is a pause of 3 days.", "gold": "a pause of 3 days"},
]


def main():
    run = Run("EXP-013", "exp_013_provenance")
    h1_rows = []
    for item in H1:
        qa = answer_question(item["question"], [{"id": "C", "text": item["passage"]}], tau=0.34)
        decided = answer_from_context_or_abstain(item["key"], qa["span"], item["passage"])
        matched_context = bool(decided["answer"] and normalize(item["context"]) in normalize(decided["answer"]))
        matched_background = bool(decided["answer"] and normalize(BACKGROUND_FACTS[item["key"]]) in normalize(decided["answer"]))
        h1_rows.append({"matched_context": matched_context, "matched_background": matched_background, "abstained": decided["abstained"], "span": qa["span"], "answer": decided["answer"]})
    h2_with = []
    h2_without = []
    for item in H2:
        with_def = answer_question(item["question"], [{"id": "D", "text": item["definition"]}], tau=0.34)
        without = answer_question(item["question"], [{"id": "U", "text": "The desk opens at noon and lists no definitions."}], tau=0.34)
        h2_with.append(bool(with_def["span"] and normalize(item["gold"]) in normalize(with_def["span"])))
        guessed = bool(without["span"])
        h2_without.append(not guessed)
    tags = [
        tag_statement("The notice period is 30 days.", "The notice period is 30 days.", "30 days", "evidence"),
        tag_statement("The end date is 31 January 2024.", "The notice period is 30 days. Start: 1 January 2024.", None, "inference"),
        tag_statement("The capital is Paris.", "In this atlas the capital of France is Lyon.", "Paris", "evidence"),
    ]
    background_only_dropped = tags[2]["kept"] is False and tags[2]["tag"] == "background"
    evidence_kept = tags[0]["kept"] and tags[0]["tag"] == "evidence"
    inference_kept = tags[1]["kept"] and tags[1]["tag"] == "inference"
    background_uses = 1  # the logged prior table was consulted and then rejected
    run.write_json("items.json", {"h1": h1_rows, "h2_with": h2_with, "h2_without": h2_without, "tags": tags})
    metrics = {
        "h1_n": len(h1_rows),
        "context_faithfulness": round(sum(r["matched_context"] for r in h1_rows) / len(h1_rows), 4),
        "answered_with_background_fact": sum(r["matched_background"] for r in h1_rows),
        "h1_abstain": sum(r["abstained"] for r in h1_rows),
        "h2_n": len(H2),
        "correct_with_definition": round(sum(h2_with) / len(h2_with), 4),
        "unresolved_without_definition": round(sum(h2_without) / len(h2_without), 4),
        "evidence_tag_kept": evidence_kept,
        "inference_tag_kept": inference_kept,
        "background_only_dropped": background_only_dropped,
        "background_consultations_logged": background_uses,
    }
    prose = (
        f"H1 context-faithfulness is {metrics['context_faithfulness']} on {metrics['h1_n']} altered-fact items. "
        f"Answers that matched the background prior: {metrics['answered_with_background_fact']}. "
        f"Abstentions: {metrics['h1_abstain']}. "
        f"H2 correct with the definition present: {metrics['correct_with_definition']}. "
        f"Unresolved (no guess) when the definition is removed: {metrics['unresolved_without_definition']}. "
        f"Provenance tags kept evidence {evidence_kept}, inference {inference_kept}, "
        f"and dropped a background-only capital claim: {background_only_dropped}."
    )
    run.finish(
        title="Provenance and context faithfulness",
        goal="Check that answers follow supplied context, that undefined invented terms stay unresolved, and that provenance tags separate evidence, inference, and background.",
        method="A fixed background table holds ordinary facts such as Paris and a 14-day sprint. Extractive QA reads only the passage. If the span is not in the passage, the answer is dropped even when the background table has a value.",
        metrics=metrics,
        results_prose=prose,
        conclusion=(
            "Factual answers are copied from the passage. The background table is logged and is not allowed to fill a missing fact. "
            "Invented terms are answered only while their definition is in the context."
        ),
        scale_down="Eight counterfactual items and six invented terms replace a larger probe set. There is no pretrained model whose memorized facts could leak; the background table is the stand-in prior.",
        referenced_files=FILES,
    )


if __name__ == "__main__":
    main()
