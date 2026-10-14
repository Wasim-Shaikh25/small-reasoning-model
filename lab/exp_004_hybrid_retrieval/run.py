"""EXP-004: hybrid retrieval, reranker lift, and one graph hop."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.graph import EntityGraph
from lab.common.harness import Run
from lab.common.index import Index, mrr, recall_at_k

FILES = [
    "lab/exp_004_hybrid_retrieval/run.py",
    "lab/common/index.py",
    "lab/common/graph.py",
    "lab/common/textutil.py",
    "lab/common/harness.py",
    "data/exp_004_hybrid_retrieval/corpus.json",
    "data/exp_004_hybrid_retrieval/results.json",
]

PASSAGES = [
    {"id": "P01", "text": "The notice period under the lease is 30 days."},
    {"id": "P02", "text": "The garden notice board lists the period of the flower show."},
    {"id": "P03", "text": "The security deposit is INR 50000 payable on signing."},
    {"id": "P04", "text": "The deposit of silt in the river delta is seasonal."},
    {"id": "P05", "text": "Ravi Sharma is the Lessee of the Pune premises."},
    {"id": "P06", "text": "Anita Sharma teaches music in Pune."},
    {"id": "P07", "text": "Ravi Sharma resides at 14 MG Road, Pune 411001."},
    {"id": "P08", "text": "14 MG Road is closed for repairs on Sunday."},
    {"id": "P09", "text": "ABC Pvt Ltd is the Lessor."},
    {"id": "P10", "text": "Termination for breach requires a written notice."},
    {"id": "P11", "text": "The licence may be terminated except where the fee is paid."},
    {"id": "P12", "text": "A sprint in this handbook lasts 9 days."},
    {"id": "P13", "text": "Bake the cake for 9 minutes at 180 C."},
    {"id": "P14", "text": "The violet quorum code is 41827."},
    {"id": "P15", "text": "The committee quorum is three members."},
    {"id": "P16", "text": "Invoice 19 is due on 2 March 2024."},
    {"id": "P17", "text": "Invoice 19 was cancelled and replaced by invoice 20."},
    {"id": "P18", "text": "The boiling point listed in this lab sheet is 98 C."},
    {"id": "P19", "text": "Water the plants every 98 hours during the trial."},
    {"id": "P20", "text": "Defined term: a zorb is a refund issued after 14 days."},
    {"id": "P21", "text": "The refund desk opens at 14:00."},
    {"id": "P22", "text": "Match length in this league is 40 minutes."},
    {"id": "P23", "text": "The patient leaflet says take 40 mg at night."},
    {"id": "P24", "text": "Interest on the sample bond is 7 percent."},
    {"id": "P25", "text": "Seven players stood in the penalty area."},
    {"id": "P26", "text": "The recipe uses 7 grams of salt."},
    {"id": "P27", "text": "Clause 4.2: the tenant shall not sublet the premises."},
    {"id": "P28", "text": "Clause 4.3: the tenant may keep one pet."},
    {"id": "P29", "text": "Schedule A lists the furniture: one table and four chairs."},
    {"id": "P30", "text": "Signed by Meera Iyer on 5 January 2024."},
    {"id": "P31", "text": "The former tenant was Kapil Iyer."},
    {"id": "P32", "text": "Premises means the flat at Plot 14, Sector 5, Ashok Nagar."},
    {"id": "P33", "text": "Park Street market opens at dawn."},
    {"id": "P34", "text": "The said premises include the parking slot."},
    {"id": "P35", "text": "Version 2 amended the lease: the notice period is 45 days."},
]

QUERIES = [
    {"id": "Q01", "query": "notice period under the lease", "gold": ["P01"]},
    {"id": "Q02", "query": "security deposit amount payable on signing", "gold": ["P03"]},
    {"id": "Q03", "query": "who is the Lessor", "gold": ["P09"]},
    {"id": "Q04", "query": "violet quorum code", "gold": ["P14"]},
    {"id": "Q05", "query": "what is a zorb", "gold": ["P20"]},
    {"id": "Q06", "query": "sprint length in this handbook", "gold": ["P12"]},
    {"id": "Q07", "query": "tenant shall not sublet", "gold": ["P27"]},
    {"id": "Q08", "query": "Plot 14 Sector 5 premises", "gold": ["P32"]},
    {"id": "Q09", "query": "invoice 19 due date", "gold": ["P16"]},
    {"id": "Q10", "query": "interest on the sample bond", "gold": ["P24"]},
    {"id": "Q11", "query": "furniture listed in schedule A", "gold": ["P29"]},
    {"id": "Q12", "query": "signed by Meera Iyer", "gold": ["P30"]},
    {"id": "Q13", "query": "termination for breach written notice", "gold": ["P10"]},
    {"id": "Q14", "query": "patient leaflet dose at night", "gold": ["P23"]},
    {"id": "Q15", "query": "match length in this league", "gold": ["P22"]},
    {"id": "Q16", "query": "boiling point on the lab sheet", "gold": ["P18"]},
    {"id": "Q17", "query": "recipe grams of salt", "gold": ["P26"]},
    {"id": "Q18", "query": "Park Street market opening", "gold": ["P33"]},
    {"id": "Q19", "query": "amended notice period version 2", "gold": ["P35"]},
    {"id": "Q20", "query": "former tenant Kapil", "gold": ["P31"]},
]


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def main():
    run = Run("EXP-004", "exp_004_hybrid_retrieval")
    run.write_json("corpus.json", {"passages": PASSAGES, "queries": QUERIES})
    index = Index(PASSAGES)
    hybrid_r5, hybrid_r10, rerank_r5, rr, present = [], [], [], [], []
    for item in QUERIES:
        gold = set(item["gold"])
        hybrid = index.search(item["query"], top_k=30)
        ids = [hit["passage"]["id"] for hit in hybrid]
        reranked = [hit["passage"]["id"] for hit in index.rerank(item["query"], hybrid, keep=10)]
        hybrid_r5.append(recall_at_k(ids, gold, 5))
        hybrid_r10.append(recall_at_k(ids, gold, 10))
        rerank_r5.append(recall_at_k(reranked, gold, 5))
        rr.append(mrr(ids, gold))
        present.append(1.0 if gold & set(ids[:10]) else 0.0)
    graph = EntityGraph()
    graph.add("Lessee", "P05", also="Ravi Sharma")
    graph.add("Ravi Sharma", "P07")
    lessee_query = "Lessee address"
    lexical_ids = [hit["passage"]["id"] for hit in index.search(lessee_query, top_k=5)]
    expanded = set(lexical_ids)
    if any(pid == "P05" for pid in lexical_ids) or "lessee" in lessee_query.lower():
        expanded |= graph.expand_ids(["Lessee"])
    gold_address = {"P07"}
    metrics = {
        "n_queries": len(QUERIES),
        "n_passages": len(PASSAGES),
        "hybrid_recall_at_5": _mean(hybrid_r5),
        "hybrid_recall_at_10": _mean(hybrid_r10),
        "rerank_recall_at_5": _mean(rerank_r5),
        "reranker_lift_recall_at_5": round(_mean(rerank_r5) - _mean(hybrid_r5), 4),
        "mrr": _mean(rr),
        "answer_passage_present_at_10": _mean(present),
        "graph_query": lessee_query,
        "lexical_top5": lexical_ids,
        "lexical_hits_address": bool(gold_address & set(lexical_ids)),
        "graph_expanded_ids": sorted(expanded),
        "graph_hits_address": bool(gold_address & expanded),
    }
    prose = (
        f"On {metrics['n_queries']} queries over {metrics['n_passages']} passages, "
        f"hybrid Recall@5 is {metrics['hybrid_recall_at_5']}, Recall@10 is {metrics['hybrid_recall_at_10']}, "
        f"MRR is {metrics['mrr']}, and answer-passage-present@10 is {metrics['answer_passage_present_at_10']}. "
        f"Reranking the top 30 changes Recall@5 to {metrics['rerank_recall_at_5']} "
        f"(lift {metrics['reranker_lift_recall_at_5']}). "
        f"The Lessee-address hop is in the lexical top 5: {metrics['lexical_hits_address']}. "
        f"After the entity-link expansion it is present: {metrics['graph_hits_address']}."
    )
    run.finish(
        title="Hybrid retrieval and rerank",
        goal="Measure dense-plus-sparse retrieval, reranker lift, and whether one entity link recovers a cross-passage address.",
        method="Okapi BM25 and TF-IDF cosine are min-max normalized and averaged. A lexical coverage score reranks the top 30. The graph links Lessee to Ravi Sharma and then to the residence passage, which does not contain the word Lessee.",
        metrics=metrics,
        results_prose=prose,
        conclusion=(
            "Hybrid search finds the labeled passage for most of these queries. "
            "The entity link is what connects Lessee to the residence sentence when that sentence does not repeat the role word."
        ),
        scale_down="In-memory BM25 and TF-IDF stand in for Qdrant dense plus sparse vectors and a cross-encoder reranker. The corpus is 35 passages, not a 1,000-page collection.",
        referenced_files=FILES,
        follow_ups=["Re-measure Recall@k on a larger corpus with an on-disk index once one is added. Do not add a generative retriever."],
    )


if __name__ == "__main__":
    main()
