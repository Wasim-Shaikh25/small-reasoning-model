"""EXP-038: provenance and context-faithfulness rerun with the real DeBERTa-v3 SQuAD2 checkpoint.

Re-measures EXP-013's H1 (context faithfulness: does the answer follow the
supplied passage, not a background prior?) and H2 (invented terms answered
only while their definition is in context) with
lab.common.real_encoders.real_qa in place of lab.common.qa.answer_question.
Provenance tagging itself (lab.common.provenance.tag_statement,
answer_from_context_or_abstain) is unchanged deterministic code; only the
span that feeds it now comes from the real checkpoint.

RETIRED (2026-11-11): lab.common.provenance was deleted -- see EXP-013's
own RETIRED note (lab/exp_013_provenance/run.py) for the full reasoning;
the same applies here unchanged, since this experiment only reruns
EXP-013's fixture with a different QA checkpoint, not different
provenance logic. Kept as the historical record (results.json
unaffected); running this script again will now ImportError.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.provenance import BACKGROUND_FACTS, answer_from_context_or_abstain
from lab.common.real_encoders import QA_MODEL_NAME, real_qa
from lab.common.textutil import normalize

FILES = [
    "lab/exp_038_real_provenance_qa/run.py",
    "lab/common/real_encoders.py",
    "lab/common/provenance.py",
    "lab/common/harness.py",
    "data/exp_013_provenance/results.json",
    "data/exp_038_real_provenance_qa/items.json",
    "data/exp_038_real_provenance_qa/results.json",
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
    run = Run("EXP-038", "exp_038_real_provenance_qa")
    h1_rows = []
    for item in H1:
        qa = real_qa(item["question"], item["passage"])
        decided = answer_from_context_or_abstain(item["key"], qa["answer"], item["passage"])
        matched_context = bool(decided["answer"] and normalize(item["context"]) in normalize(decided["answer"]))
        matched_background = bool(decided["answer"] and normalize(BACKGROUND_FACTS[item["key"]]) in normalize(decided["answer"]))
        h1_rows.append({"matched_context": matched_context, "matched_background": matched_background, "abstained": decided["abstained"], "span": qa["answer"], "answer": decided["answer"]})

    h2_with = []
    h2_without = []
    for item in H2:
        with_def = real_qa(item["question"], item["definition"])
        without = real_qa(item["question"], "The desk opens at noon and lists no definitions.")
        h2_with.append(bool(with_def["answer"] and normalize(item["gold"]) in normalize(with_def["answer"])))
        h2_without.append(not bool(without["answer"]))

    run.write_json("items.json", {"h1": h1_rows, "h2_with": h2_with, "h2_without": h2_without})

    metrics = {
        "model": QA_MODEL_NAME,
        "h1_n": len(h1_rows),
        "context_faithfulness": round(sum(r["matched_context"] for r in h1_rows) / len(h1_rows), 4),
        "answered_with_background_fact": sum(r["matched_background"] for r in h1_rows),
        "h1_abstain": sum(r["abstained"] for r in h1_rows),
        "h2_n": len(H2),
        "correct_with_definition": round(sum(h2_with) / len(h2_with), 4),
        "unresolved_without_definition": round(sum(h2_without) / len(h2_without), 4),
    }

    exp013_path = ROOT / "data" / "exp_013_provenance" / "results.json"
    exp013 = json.loads(exp013_path.read_text())["metrics"] if exp013_path.exists() else None
    if exp013:
        metrics["vs_exp_013_lexical_qa"] = {
            "exp_013_context_faithfulness": exp013["context_faithfulness"],
            "exp_038_context_faithfulness": metrics["context_faithfulness"],
            "exp_013_correct_with_definition": exp013["correct_with_definition"],
            "exp_038_correct_with_definition": metrics["correct_with_definition"],
            "exp_013_unresolved_without_definition": exp013["unresolved_without_definition"],
            "exp_038_unresolved_without_definition": metrics["unresolved_without_definition"],
        }

    prose = (
        f"With {QA_MODEL_NAME}, H1 context-faithfulness is {metrics['context_faithfulness']} on "
        f"{metrics['h1_n']} altered-fact items (answers matching the background prior instead of the "
        f"passage: {metrics['answered_with_background_fact']}, abstentions: {metrics['h1_abstain']}). "
        f"H2 correct with the definition present: {metrics['correct_with_definition']}; unresolved when "
        f"the definition is removed: {metrics['unresolved_without_definition']}. "
        + (f"EXP-013's lexical extractor scored context-faithfulness {exp013['context_faithfulness']} on the same items." if exp013 else "")
    )

    run.finish(
        title="Provenance and context faithfulness rerun with the real DeBERTa-v3 SQuAD2 checkpoint",
        goal="Re-measure EXP-013's context-faithfulness (H1) and invented-term (H2) probes with deepset/deberta-v3-base-squad2 in place of the lexical extractor.",
        method=(
            "Identical items and passages as EXP-013. lab.common.real_encoders.real_qa replaces "
            "lab.common.qa.answer_question for both H1 (does the span follow the passage, not a background "
            "prior table) and H2 (is an invented term's definition only usable while present in context). "
            "Provenance tagging (lab.common.provenance.answer_from_context_or_abstain) is unchanged "
            "deterministic code: it still accepts or drops a span based on whether it occurs in the "
            "evidence text, verbatim-quote rule, regardless of which model proposed the span."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=(
            f"The real {QA_MODEL_NAME} checkpoint is loaded and measured on EXP-013's own items, not "
            "assumed. The quote-in-passage gate (lab.common.provenance) still runs underneath the real "
            "checkpoint exactly as it did under the lexical extractor, so a real model's span is no more "
            "able to leak a background fact than the lexical one was -- the gate's guarantee does not "
            "depend on which extractor proposed the span."
        ),
        scale_down="Same 8 H1 items and 6 H2 items EXP-013 used.",
        referenced_files=FILES,
        models_used=(
            f"{QA_MODEL_NAME}, a local checkpoint loaded with transformers (not an API call). The provenance "
            "gate downstream of it is unchanged deterministic code."
        ),
    )


if __name__ == "__main__":
    main()
