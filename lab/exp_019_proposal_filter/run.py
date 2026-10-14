"""EXP-019: grounding filter and template queries (architecture Experiment P, no proposer model)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.ask import analyze
from lab.common.harness import Run
from lab.common.index import Index, recall_at_k
from lab.common.proposals import dedupe, grounding_filter

FILES = [
    "lab/exp_019_proposal_filter/run.py",
    "lab/common/proposals.py",
    "lab/common/ask.py",
    "lab/common/index.py",
    "lab/common/textutil.py",
    "lab/common/harness.py",
    "data/exp_019_proposal_filter/proposals.json",
    "data/exp_019_proposal_filter/results.json",
]

ASK = "What is the notice period under the lease?"
CONTEXT = "The notice period under the lease is 30 days."
PASSAGES = [
    {"id": "P01", "text": CONTEXT},
    {"id": "P02", "text": "The garden notice board lists the period of the flower show."},
    {"id": "P35", "text": "Version 2 amended the lease: the notice period is 45 days."},
    {"id": "P03", "text": "The security deposit is INR 50000."},
]

GOOD = [
    "notice period",
    "notice period under the lease",
    "what is the notice period",
    "lease notice period",
    "the notice period",
]
HALLUCINATED = [
    "notice period is 90 days",
    "Ravi Sharma notice period",
    "notice period on 1 January 2024",
    "the cure period is 10 days",
    "Kapil Menon lease",
]
MALFORMED = ["", "   ", "notice\n\nperiod with a second paragraph that should not parse as a list item " * 4]
DUPLICATES = ["notice period", "Notice   period", "notice period"]


def main():
    run = Run("EXP-019", "exp_019_proposal_filter")
    rows = []
    for text in GOOD:
        rows.append({"text": text, "kind": "good", **grounding_filter(text, ASK, CONTEXT)})
    for text in HALLUCINATED:
        rows.append({"text": text, "kind": "hallucinated", **grounding_filter(text, ASK, CONTEXT)})
    for text in MALFORMED:
        rows.append({"text": text, "kind": "malformed", **grounding_filter(text, ASK, CONTEXT)})
    deduped = dedupe(DUPLICATES)
    kept_good = [r for r in rows if r["kind"] == "good" and r["keep"]]
    caught_hall = [r for r in rows if r["kind"] == "hallucinated" and not r["keep"]]
    caught_bad = [r for r in rows if r["kind"] == "malformed" and not r["keep"]]
    index = Index(PASSAGES)
    gold = {"P01"}
    raw_ids = [h["passage"]["id"] for h in index.search(ASK, top_k=5)]
    plan = analyze(ASK)
    template_ids = []
    for query in plan["queries"]:
        template_ids.extend(h["passage"]["id"] for h in index.search(query, top_k=5))
    # Unique order-preserving.
    ordered = []
    for pid in template_ids:
        if pid not in ordered:
            ordered.append(pid)
    raw_recall = recall_at_k(raw_ids, gold, 5)
    template_recall = recall_at_k(ordered, gold, 5)
    harm = template_recall < raw_recall
    run.write_json("proposals.json", rows)
    metrics = {
        "good_kept": len(kept_good),
        "good_total": len(GOOD),
        "hallucination_catch_rate": round(len(caught_hall) / len(HALLUCINATED), 4),
        "malformed_catch_rate": round(len(caught_bad) / len(MALFORMED), 4),
        "deduped_count": len(deduped),
        "format_valid_rate_on_good": round(len(kept_good) / len(GOOD), 4),
        "raw_ask_recall_at_5": raw_recall,
        "template_query_recall_at_5": template_recall,
        "retrieval_lift": round(template_recall - raw_recall, 4),
        "harm_template_lowered_recall": harm,
        "proposer_model_called": False,
        "raw_ask_in_template_queries": ASK in plan["queries"],
    }
    prose = (
        f"The grounding filter kept {metrics['good_kept']} of {metrics['good_total']} source-bound queries "
        f"and caught {metrics['hallucination_catch_rate']} of the queries that introduced a new name, number, or date. "
        f"Malformed items caught: {metrics['malformed_catch_rate']}. "
        f"Duplicates collapsed to {metrics['deduped_count']}. "
        f"Raw-ask Recall@5 is {metrics['raw_ask_recall_at_5']}; template queries reach {metrics['template_query_recall_at_5']} "
        f"(lift {metrics['retrieval_lift']}, harm {metrics['harm_template_lowered_recall']}). "
        "No proposer model was called."
    )
    run.finish(
        title="Proposal grounding filter",
        goal="Measure the grounding filter and the retrieval lift of template queries over the raw ask, without calling a generative proposer.",
        method="Candidate strings are kept only when they are well formed and their names, numbers, dates, and content terms already occur in the ask or the pasted context. Template queries come from the ask analyzer. Recall of the gold lease passage is compared with the raw ask.",
        metrics=metrics,
        results_prose=prose,
        conclusion=(
            "The filter drops proposals that introduce new names, numbers, or dates. "
            "Template queries are allowed only as additional searches; the raw ask remains in the list, so a bad extra query cannot remove the baseline. "
            "Experiment P's model ladder was not run."
        ),
        scale_down="Hand-written good and bad proposals stand in for FLAN-T5 samples. Input-size, hop, and sampling ladders that require a generative model are out of scope.",
        referenced_files=FILES,
    )


if __name__ == "__main__":
    main()
