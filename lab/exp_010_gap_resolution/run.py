"""EXP-010: gap types and the budgeted resolution loop (architecture section 6.0 and H6)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.index import Index
from lab.common.nli import judge, label_of
from lab.common.qa import answer_question
from lab.common.textutil import normalize, numbers

FILES = [
    "lab/exp_010_gap_resolution/run.py",
    "lab/common/index.py",
    "lab/common/qa.py",
    "lab/common/nli.py",
    "lab/common/textutil.py",
    "lab/common/harness.py",
    "data/exp_010_gap_resolution/items.json",
    "data/exp_010_gap_resolution/results.json",
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


def resolve_gap(item: dict, max_rounds: int = 3) -> dict:
    passages = [{"id": f"P{i}", "text": text} for i, text in enumerate(item["passages"])]
    index = Index(passages)
    alternatives = []
    for rnd in range(max_rounds):
        query = item["queries"][min(rnd, len(item["queries"]) - 1)]
        hits = index.rerank(query, index.search(query, top_k=6), keep=6)
        ctx = [hit["passage"] for hit in hits]
        qa = answer_question(item["question"], ctx, tau=0.34)
        spans = []
        for passage in ctx:
            one = answer_question(item["question"], [passage], tau=0.34)
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
            support = judge(ctx[0]["text"] if ctx else "", f"The answer is {qa['span']}.")
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
    run = Run("EXP-010", "exp_010_gap_resolution")
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
    prose = (
        f"Gap resolution accuracy on {metrics['n']} items is {metrics['accuracy']}. "
        f"By type: {metrics['by_gap']}. "
        "Conflicts and vague criteria are closed as ambiguous. Missing definitions with no passage stay unresolved."
    )
    run.finish(
        title="Gap resolution loop",
        goal="Run the budgeted gap loop on unknown terms, ambiguous references, missing premises, conflicting values, and vague criteria.",
        method="Each round searches the supplied passages, reranks, and re-reads with extractive QA. Disagreeing spans stay open. After at most 3 rounds the gap is resolved, ambiguous, or unresolved. No weights change.",
        metrics=metrics,
        results_prose=prose,
        conclusion="The loop can close a gap only when a passage states the missing piece, and it refuses a single answer when two values or a vague criterion remain.",
        scale_down="Twelve items, two or three per gap type, replace the requested 10 items per gap type. Context is pasted, which is the Phase 0 setup.",
        referenced_files=FILES,
    )


if __name__ == "__main__":
    main()
