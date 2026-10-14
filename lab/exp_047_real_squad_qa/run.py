"""EXP-047: extractive QA and answerability on the real SQuAD2 dev set.

ARCHITECTURE.md's Experiment B (section 10) specifies the data as "SQuAD2 dev
subset plus 40 custom items." EXP-005 ran only the 40 custom items. This
exploration runs the identical method (lab/common/qa.answer_with_agreement,
the same two lexical extractors, the same tau, the same harness.score_qa) on
300 real, unmodified SQuAD2 dev questions instead, and reports the same
metrics side by side with EXP-005's closed numbers.

No model is loaded here, classical or neural -- this is a real-data rerun, not
a real-model rerun. It is independent of the huggingface.co block that limits
EXP-029/032/033.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run, score_qa
from lab.common.qa import answer_with_agreement
from lab.common.real_squad import N_ITEMS, build_subset, save_subset
from lab.common.textutil import normalize

FILES = [
    "lab/exp_047_real_squad_qa/run.py",
    "lab/common/real_squad.py",
    "lab/common/qa.py",
    "lab/common/harness.py",
    "lab/common/textutil.py",
    "data/exp_005_extractive_qa/results.json",
    "data/exp_047_real_squad_qa/squad_subset.json",
    "data/exp_047_real_squad_qa/items.json",
    "data/exp_047_real_squad_qa/results.json",
]

TAU = 0.34


def main():
    run = Run("EXP-047", "exp_047_real_squad_qa")
    items = build_subset(N_ITEMS)
    subset_path = save_subset(items)

    serializable = []
    scores = []
    for item in items:
        passages = [{"id": pid, "text": text} for pid, text in item["passages"].items()]
        qa = answer_with_agreement(item["question"], passages, tau=TAU)
        packed = {
            "answerable": item["answerable"],
            "gold": item["gold"],
            "tau_no_answer": TAU,
            "passages": item["passages"],
        }
        scored = score_qa(packed, {"span": qa["span"], "score": qa["score"], "no_answer": qa["no_answer"], "passage_id": qa["passage_id"]})
        any_ref_match = bool(
            qa["span"]
            and item["answerable"]
            and any(normalize(alt) == normalize(qa["span"]) for alt in item["gold_alternatives"])
        )
        contained = bool(
            qa["span"]
            and item["answerable"]
            and any(normalize(alt) in normalize(qa["span"]) or normalize(qa["span"]) in normalize(alt) for alt in item["gold_alternatives"])
        )
        scores.append(
            {
                **scored,
                "any_reference_match": any_ref_match,
                "contained": contained,
                "id": item["id"],
                "span": qa["span"],
                "passage_id": qa["passage_id"],
                "agrees": qa["second_model_agrees"],
                "answerable": item["answerable"],
            }
        )
        serializable.append(
            {
                "id": item["id"],
                "title": item["title"],
                "question": item["question"],
                "gold_alternatives": item["gold_alternatives"],
                "answerable": item["answerable"],
                "pred_span": qa["span"],
                "passage_id": qa["passage_id"],
                **scored,
                "any_reference_match": any_ref_match,
            }
        )
    run.write_json("items.json", serializable)

    answerable = [s for s in scores if s["answerable"]]
    unanswerable = [s for s in scores if not s["answerable"]]
    abstained = [s for s in scores if s["correct_abstain"] or s["missed_answer"]]
    answered = [s for s in scores if not (s["correct_abstain"] or s["missed_answer"])]
    span_valid = [s for s in answered if s["span_valid"]]

    metrics = {
        "data_source": "real SQuAD2 dev-v2.0.json (rajpurkar/SQuAD-explorer), unmodified Wikipedia-paragraph questions",
        "n": len(scores),
        "n_answerable": len(answerable),
        "n_unanswerable": len(unanswerable),
        "tau": TAU,
        "exact_match_on_answerable": round(sum(s["exact_match"] for s in answerable) / max(1, len(answerable)), 4),
        "any_reference_match_on_answerable": round(sum(s["any_reference_match"] for s in answerable) / max(1, len(answerable)), 4),
        "contained_match_on_answerable": round(sum(s["contained"] for s in answerable) / max(1, len(answerable)), 4),
        "unanswerable_recall": round(sum(s["correct_abstain"] for s in unanswerable) / max(1, len(unanswerable)), 4),
        "false_answer_rate_on_unanswerable": round(sum(s["false_answer"] for s in unanswerable) / max(1, len(unanswerable)), 4),
        "missed_answer_rate": round(sum(s["missed_answer"] for s in answerable) / max(1, len(answerable)), 4),
        "span_valid_rate_when_answered": round(len(span_valid) / max(1, len(answered)), 4),
        "second_extractor_agreement_when_answered": round(sum(1 for s in answered if s["agrees"]) / max(1, len(answered)), 4),
        "answered": len(answered),
        "abstained": len(abstained),
    }

    exp005_path = ROOT / "data" / "exp_005_extractive_qa" / "results.json"
    exp005 = None
    if exp005_path.exists():
        import json

        exp005 = json.loads(exp005_path.read_text())["metrics"]
        metrics["vs_exp_005_custom_items"] = {
            "exp_005_exact_match_on_answerable": exp005["exact_match_on_answerable"],
            "exp_047_exact_match_on_answerable": metrics["exact_match_on_answerable"],
            "exp_005_unanswerable_recall": exp005["unanswerable_recall"],
            "exp_047_unanswerable_recall": metrics["unanswerable_recall"],
            "exp_005_span_valid_rate_when_answered": exp005["span_valid_rate_when_answered"],
            "exp_047_span_valid_rate_when_answered": metrics["span_valid_rate_when_answered"],
        }

    prose = (
        f"On {metrics['n']} real SQuAD2 dev questions ({metrics['n_answerable']} answerable, "
        f"{metrics['n_unanswerable']} unanswerable), exact match on answerable items is "
        f"{metrics['exact_match_on_answerable']} (any-reference-answer match {metrics['any_reference_match_on_answerable']}, "
        f"contained-span match {metrics['contained_match_on_answerable']}). Unanswerable recall is "
        f"{metrics['unanswerable_recall']} (false-answer rate {metrics['false_answer_rate_on_unanswerable']}). "
        f"Span validity when answered is {metrics['span_valid_rate_when_answered']}. "
        + (
            f"For comparison, EXP-005's 40 hand-written items scored exact match "
            f"{exp005['exact_match_on_answerable']} and unanswerable recall {exp005['unanswerable_recall']}."
            if exp005
            else ""
        )
    )
    target_met = metrics["unanswerable_recall"] >= 0.9

    conclusion = (
        "The same lexical extractor and the same 0.34 threshold that scored well on EXP-005's clean, hand-written "
        "items "
        + (
            "also meets the Phase 0 unanswerable-recall target on real, adversarially written SQuAD2 questions."
            if target_met
            else "falls short of the Phase 0 unanswerable-recall target on real, adversarially written SQuAD2 "
            "questions, unlike on EXP-005's custom set. SQuAD2's unanswerable questions are deliberately phrased to "
            "closely resemble an answerable one over the same passage (for example, a question that swaps 'gave "
            "their name to Normandy' for a subtly different, unsupported claim); the lexical coverage scorer has no "
            "way to tell a close paraphrase of a supported claim from an unsupported one, so it answers when it "
            "should abstain."
        )
        + " This closes the SQuAD2 data gap that EXP-005's scale-down note flagged: the architecture's own "
        "Experiment B data spec is now exercised, with the lexical extractor as the measured method -- not a "
        "DeBERTa/RoBERTa SQuAD2 checkpoint, which EXP-030 (still todo) would require and which huggingface.co "
        "being blocked in this sandbox prevents loading."
    )

    run.finish(
        title="Extractive QA and answerability on the real SQuAD2 dev set",
        goal="Run the architecture's Experiment B on its actual specified data (SQuAD2 dev subset) instead of only the 40 custom items EXP-005 used, with the same lexical method so the two are directly comparable.",
        method=(
            f"Took the first {N_ITEMS} questions from the real, unmodified SQuAD2 dev-v2.0.json, in file order "
            "(deterministic, not sampled). Each question keeps its real context paragraph as passage A; passage B "
            "is a real distractor -- the first paragraph of a different, deterministically chosen article in the "
            "same dataset, giving every item the same two-passage shape as EXP-005's items without inventing any "
            "text. Ran the identical lab/common/qa.answer_with_agreement (unigram + bigram lexical extractors, "
            "tau=0.34) and harness.score_qa used by EXP-005. Exact match uses the dataset's first reference answer; "
            "any_reference_match additionally credits a prediction matching any of SQuAD2's multiple human "
            "reference answers for that question."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            f"{N_ITEMS} of the dev set's roughly 12,000 questions, not the full set. One real distractor passage "
            "per question, not the 3-10 passages Experiment B specifies. No pretrained QA checkpoint is loaded "
            "(deepset/deberta-v3-base-squad2 is EXP-030, still todo, blocked on huggingface.co access)."
        ),
        referenced_files=FILES,
        follow_ups=[
            "Run the full dev set (not just the first 300) for a stable estimate.",
            "If huggingface.co access is ever granted, rerun this exact subset with deepset/deberta-v3-base-squad2 (EXP-030) for a true model-vs-model comparison on identical real data.",
            "Add the 3-10 passage distractor count Experiment B specifies, once more real passages per question are sourced.",
        ],
        models_used=(
            "No model, classical or neural, is loaded by this exploration beyond lab/common/qa.py's existing "
            "lexical extractors (unchanged from EXP-005). This is a real-data rerun: the SQuAD2 dev set is real "
            "and unmodified; the method is EXP-005's own. deepset/deberta-v3-base-squad2, the blueprint's named "
            "checkpoint for this role, remains unloaded because huggingface.co is blocked in this sandbox."
        ),
    )
    print(f"wrote {subset_path}")


if __name__ == "__main__":
    main()
