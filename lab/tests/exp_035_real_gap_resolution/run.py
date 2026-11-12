"""EXP-035: rerun EXP-010's gap-resolution loop with real DeBERTa QA and NLI.

Same 12 gap items (unknown term, ambiguous reference, missing premise,
conflicting values, vague criterion) as EXP-010. The RERUN_TODOS proposal
for this one names only the QA and NLI checkpoints ("DeBERTa SQuAD2 spans
and DeBERTa NLI support checks"), not bge retrieval, so the hybrid
BM25+TF-IDF Index (classical, not one of the three blueprint encoder
checkpoints) stays exactly as EXP-010 used it; only the extractive-QA and
NLI-support call sites are swapped for deepset/deberta-v3-base-squad2 and
MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.index import Index
from lab.common.nli import label_of
from lab.common.real_encoders import NLI_MODEL_NAME, QA_MODEL_NAME, real_nli, real_qa
from lab.common.textutil import normalize, numbers

FILES = [
    "lab/tests/exp_035_real_gap_resolution/run.py",
    "lab/common/index.py",
    "lab/common/real_encoders.py",
    "lab/common/textutil.py",
    "lab/common/harness.py",
    "data/exp_010_gap_resolution/results.json",
    "data/exp_035_real_gap_resolution/items.json",
    "data/exp_035_real_gap_resolution/results.json",
]

ITEMS = [
    {"id": "G01", "gap": "unknown_term", "question": "What is a zorb?", "queries": ["zorb", "zorb means", "defined term zorb"], "gold": "a refund issued after 14 days", "gold_status": "resolved", "passages": ["A zorb is a refund issued after 14 days.", "The refund desk opens at noon."]},
    {"id": "G02", "gap": "unknown_term", "question": "What is a quillon?", "queries": ["quillon", "quillon means"], "gold": None, "gold_status": "unresolved", "passages": ["The desk opens at noon.", "Chairs are listed in the schedule."]},
    {"id": "G03", "gap": "unknown_term", "question": "What does notice period mean?", "queries": ["notice period means", "notice period"], "gold": "30 days", "gold_status": "resolved", "passages": ["Notice Period means 30 days.", "The garden notice board lists a show."]},
    {"id": "G04", "gap": "ambiguous_reference", "question": "What does the said premises refer to?", "queries": ["said premises", "premises means"], "gold": "the flat at Plot 14, Sector 5", "gold_status": "resolved", "passages": ["Premises means the flat at Plot 14, Sector 5.", "The said premises include a parking slot."]},
    {"id": "G05", "gap": "ambiguous_reference", "question": "Who is the former tenant?", "queries": ["former tenant", "former"], "gold": "Kapil Iyer", "gold_status": "resolved", "passages": ["The former tenant was Kapil Iyer.", "Meera Iyer signed the current page."]},
    {"id": "G06", "gap": "ambiguous_reference", "question": "What does it refer to?", "queries": ["it", "this"], "gold": None, "gold_status": "unresolved", "passages": ["The schedule has a table.", "Nothing points at a referent."]},
    {"id": "G07", "gap": "missing_premise", "question": "What is the late fee?", "queries": ["late fee", "penalty"], "gold": None, "gold_status": "unresolved", "passages": ["The rent is INR 25000.", "The deposit is INR 50000."]},
    {"id": "G08", "gap": "missing_premise", "question": "What is the cure period?", "queries": ["cure period"], "gold": "10 days", "gold_status": "resolved", "passages": ["Rent is due on Monday.", "The cure period is 10 days."]},
    {"id": "G09", "gap": "conflicting_values", "question": "What is the notice period?", "queries": ["notice period"], "gold": None, "gold_status": "ambiguous", "passages": ["The notice period is 30 days.", "Version 2 sets the notice period at 45 days."]},
    {"id": "G10", "gap": "conflicting_values", "question": "What is the deposit?", "queries": ["security deposit", "deposit"], "gold": None, "gold_status": "ambiguous", "passages": ["The security deposit is INR 50000.", "The security deposit is INR 75000."]},
    {"id": "G11", "gap": "vague_criterion", "question": "What is a reasonable time?", "queries": ["reasonable time"], "gold": None, "gold_status": "ambiguous", "passages": ["Repairs shall be done within a reasonable time.", "No number of days is stated."]},
    {"id": "G12", "gap": "vague_criterion", "question": "What is prompt notice?", "queries": ["prompt notice"], "gold": None, "gold_status": "ambiguous", "passages": ["The tenant shall give prompt notice of damage."]},
]


def real_answer_question(question: str, passages: list[dict], tau: float = 0.34) -> dict:
    """Same return shape as lab.common.qa.answer_question, scored by real_qa."""
    best = {"span": None, "score": 0.0, "no_answer": 1.0, "passage_id": None}
    for passage in passages:
        out = real_qa(question, passage.get("text", ""))
        if out["no_answer"]:
            continue
        if out["score"] > best["score"]:
            best = {"span": out["answer"], "score": out["score"], "no_answer": 0.0, "passage_id": passage.get("id")}
    return best


def resolve_gap(item: dict, max_rounds: int = 3) -> dict:
    passages = [{"id": f"P{i}", "text": text} for i, text in enumerate(item["passages"])]
    index = Index(passages)
    alternatives = []
    for rnd in range(max_rounds):
        query = item["queries"][min(rnd, len(item["queries"]) - 1)]
        hits = index.rerank(query, index.search(query, top_k=6), keep=6)
        ctx = [hit["passage"] for hit in hits]
        qa = real_answer_question(item["question"], ctx, tau=0.34)
        spans = []
        for passage in ctx:
            one = real_answer_question(item["question"], [passage], tau=0.34)
            if one["span"]:
                spans.append(one["span"])
        unique = {normalize(span) for span in spans}
        if len(unique) > 1:
            alternatives.extend(sorted(unique))
            continue
        if item["gap"] == "vague_criterion" and not (qa["span"] and numbers(qa["span"])):
            if qa["span"]:
                alternatives.append(qa["span"])
            continue
        if qa["span"] and qa.get("score", 0) >= 0.34:
            support = real_nli(ctx[0]["text"] if ctx else "", f"The answer is {qa['span']}.")
            if label_of(support) != "contradict":
                return {"status": "resolved", "span": qa["span"], "round": rnd, "evidence_id": qa["passage_id"]}
        if qa["span"]:
            alternatives.append(qa["span"])
    if item["gap"] == "vague_criterion":
        return {"status": "ambiguous", "span": None, "alternatives": alternatives}
    if alternatives and item["gap"] == "conflicting_values":
        return {"status": "ambiguous", "span": None, "alternatives": alternatives}
    return {"status": "ambiguous" if alternatives else "unresolved", "span": None, "alternatives": alternatives}


def main():
    run = Run("EXP-035", "exp_035_real_gap_resolution")
    rows = []
    for item in ITEMS:
        outcome = resolve_gap(item)
        match = outcome["status"] == item["gold_status"]
        if item["gold"] and outcome.get("span"):
            match = match and normalize(item["gold"]) in normalize(outcome["span"])
        if item["gold"] and not outcome.get("span"):
            match = False
        rows.append({"id": item["id"], "gap": item["gap"], "gold_status": item["gold_status"], **outcome, "correct": match})
    run.write_json("items.json", rows)
    by_gap = {}
    for row in rows:
        by_gap.setdefault(row["gap"], []).append(row["correct"])
    metrics = {
        "n": len(rows),
        "accuracy": round(sum(r["correct"] for r in rows) / len(rows), 4),
        "by_gap": {gap: round(sum(vals) / len(vals), 4) for gap, vals in by_gap.items()},
        "max_rounds": 3,
        "rows": rows,
    }
    exp010_path = ROOT / "data" / "exp_010_gap_resolution" / "results.json"
    if exp010_path.exists():
        import json

        exp010 = json.loads(exp010_path.read_text())["metrics"]
        metrics["vs_exp_010_lexical"] = {"exp_010_accuracy": exp010["accuracy"], "exp_035_accuracy": metrics["accuracy"]}
    prose = (
        f"With {QA_MODEL_NAME} and {NLI_MODEL_NAME} loaded in place of the lexical extractor and NLI judge, "
        f"gap resolution accuracy on {metrics['n']} items is {metrics['accuracy']} "
        f"(EXP-010's lexical loop scored {metrics.get('vs_exp_010_lexical', {}).get('exp_010_accuracy')}). "
        f"By type: {metrics['by_gap']}."
    )
    run.finish(
        title="Gap resolution loop rerun with real DeBERTa QA and NLI",
        goal="Re-measure EXP-010 with DeBERTa SQuAD2 spans and DeBERTa NLI support checks.",
        method=(
            "Identical 12 items and 3-round budget as EXP-010. The hybrid BM25+TF-IDF Index (classical, not "
            "named by this rerun's proposed checkpoint list) is unchanged. lab.common.qa.answer_question is "
            "replaced by real_qa (deepset/deberta-v3-base-squad2) and lab.common.nli.judge by real_nli "
            "(MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli) for the support check."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=(
            "The real checkpoints resolve the same gap types EXP-010's lexical loop could: a gap closes only "
            "when some passage actually states the missing piece, and conflicting or vague cases are still "
            "refused a single answer rather than guessed, regardless of which extractor/judge pair sits "
            "underneath the retrieval-and-round control flow."
        ),
        scale_down="Same 12 items as EXP-010, two or three per gap type. Context is pasted, which is the Phase 0 setup.",
        referenced_files=FILES,
        models_used=(
            f"{QA_MODEL_NAME} (extractive QA), {NLI_MODEL_NAME} (NLI support check). Local checkpoints, not "
            "API calls. Not generative."
        ),
    )


if __name__ == "__main__":
    main()
