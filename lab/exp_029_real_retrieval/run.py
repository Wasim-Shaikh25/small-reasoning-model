"""EXP-029: rerun hybrid retrieval with a real pretrained dense model.

The blueprint names bge-small-en-v1.5 for the dense leg, Qdrant for storage, and
bge-reranker-v2-m3 for reranking. huggingface.co is blocked by this sandbox's
egress policy (see lab/common/real_models.py), so bge itself cannot be loaded
here. This rerun loads the closest real, reachable, non-generative substitute --
spaCy's en_core_web_md pretrained static vectors -- for the dense leg, keeps the
same in-process Okapi BM25 sparse leg as EXP-004, and measures retrieval over
the real multi-document collection attached in EXP-025 instead of the 35
synthetic lease passages EXP-004 used.

This is not a bge measurement. It is a measured comparison of the classical
TF-IDF dense leg (EXP-004's substitute) against a real pretrained dense leg, on
real documents.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import json

from lab.common.harness import Run
from lab.common.index import Index, mrr, recall_at_k
from lab.common.real_corpus import DOCS_PATH
from lab.common.real_index import RealIndex
from lab.common.real_models import model_card

FILES = [
    "lab/exp_029_real_retrieval/run.py",
    "lab/common/real_index.py",
    "lab/common/real_models.py",
    "lab/common/index.py",
    "lab/common/real_corpus.py",
    "lab/common/harness.py",
    "data/exp_025_real_documents/chunks.json",
    "data/exp_029_real_retrieval/queries.json",
    "data/exp_029_real_retrieval/results.json",
]


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def load_chunks() -> list[dict]:
    path = ROOT / "data" / "exp_025_real_documents" / "chunks.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing. Run lab/exp_025_real_documents/run.py first.")
    return json.loads(path.read_text())


def build_summary_queries(chunks: list[dict]) -> list[dict]:
    """One query per chunk, using the chunk's own extractive summary. Gold is that chunk's id.

    The query text is a literal substring of the gold passage, so both a lexical and a
    dense scorer can win on exact term overlap alone. This is a sanity check, not a hard test.
    """
    queries = []
    for chunk in chunks:
        summary = (chunk.get("summary") or "").strip()
        if not summary or not chunk.get("summary_sentences_are_substrings"):
            continue
        queries.append({"id": f"RQ-{chunk['chunk_id']}", "query": summary, "gold": [chunk["chunk_id"]]})
    return queries


def build_headline_queries(documents: list[dict], chunks: list[dict]) -> list[dict]:
    """One query per real document, using its real headline. Gold is every chunk of that document's body.

    The headline is real text from the same article but is not copied into any chunk body
    verbatim, so a hit requires relating the headline's wording to the body's wording --
    a harder, more realistic test than the substring-summary queries above.
    """
    queries = []
    for doc in documents:
        gold = [c["chunk_id"] for c in chunks if c["doc_id"] == doc["doc_id"]]
        if gold:
            queries.append({"id": f"HQ-{doc['doc_id']}", "query": doc["title"], "gold": gold})
    return queries


def _score(index, passages: list[dict], queries: list[dict]) -> dict:
    r5, r10, rr = [], [], []
    for item in queries:
        gold = set(item["gold"])
        hits = index.search(item["query"], top_k=10)
        ids = [hit["passage"]["chunk_id"] for hit in hits]
        r5.append(recall_at_k(ids, gold, 5))
        r10.append(recall_at_k(ids, gold, 10))
        rr.append(mrr(ids, gold))
    return {
        "recall_at_5": _mean(r5),
        "recall_at_10": _mean(r10),
        "mrr": _mean(rr),
    }


def main():
    run = Run("EXP-029", "exp_029_real_retrieval")
    chunks = load_chunks()
    documents = json.loads(DOCS_PATH.read_text())
    passages = [{"id": c["chunk_id"], "chunk_id": c["chunk_id"], "text": c["text"], "doc_id": c["doc_id"]} for c in chunks]

    summary_queries = build_summary_queries(chunks)
    headline_queries = build_headline_queries(documents, chunks)
    run.write_json("queries.json", {"summary_queries": summary_queries, "headline_queries": headline_queries})

    classical_index = Index(passages)
    real_index = RealIndex(passages)

    summary_classical = _score(classical_index, passages, summary_queries)
    summary_real = _score(real_index, passages, summary_queries)
    headline_classical = _score(classical_index, passages, headline_queries)
    headline_real = _score(real_index, passages, headline_queries)

    metrics = {
        "n_passages": len(chunks),
        "n_summary_queries": len(summary_queries),
        "n_headline_queries": len(headline_queries),
        "summary_queries_sanity_check": {
            "note": "query is a literal substring of the gold passage; both scorers can win on exact overlap",
            "classical_tfidf_dense": summary_classical,
            "real_pretrained_dense": summary_real,
            "lift_recall_at_5": round(summary_real["recall_at_5"] - summary_classical["recall_at_5"], 4),
            "lift_mrr": round(summary_real["mrr"] - summary_classical["mrr"], 4),
        },
        "headline_queries_hard_test": {
            "note": "query is the article's real headline, not copied verbatim into any chunk body",
            "classical_tfidf_dense": headline_classical,
            "real_pretrained_dense": headline_real,
            "lift_recall_at_5": round(headline_real["recall_at_5"] - headline_classical["recall_at_5"], 4),
            "lift_recall_at_10": round(headline_real["recall_at_10"] - headline_classical["recall_at_10"], 4),
            "lift_mrr": round(headline_real["mrr"] - headline_classical["mrr"], 4),
        },
        "real_model_card": model_card(),
    }
    prose = (
        f"Sanity check ({metrics['n_summary_queries']} substring-summary queries, {metrics['n_passages']} passages): "
        f"classical Recall@5 {summary_classical['recall_at_5']}, real-model Recall@5 {summary_real['recall_at_5']} "
        f"(lift {metrics['summary_queries_sanity_check']['lift_recall_at_5']:+.4f}) -- both near ceiling because the "
        f"query is literally inside the gold passage. "
        f"Hard test ({metrics['n_headline_queries']} real-headline queries, gold is the whole document's chunk set): "
        f"classical Recall@5 {headline_classical['recall_at_5']}, Recall@10 {headline_classical['recall_at_10']}; "
        f"real-model Recall@5 {headline_real['recall_at_5']}, Recall@10 {headline_real['recall_at_10']} "
        f"(lift {metrics['headline_queries_hard_test']['lift_recall_at_5']:+.4f} at 5, "
        f"{metrics['headline_queries_hard_test']['lift_recall_at_10']:+.4f} at 10). "
        f"On this harder, more realistic test the real pretrained static-vector dense leg does not beat classical "
        f"TF-IDF; it measures lower. The measured number is reported as found, not adjusted."
    )
    run.finish(
        title="Hybrid retrieval with a real pretrained dense model, on real documents",
        goal="Re-measure EXP-004-style hybrid retrieval with a real pretrained encoder for the dense leg, over the real document collection from EXP-025 instead of synthetic lease passages.",
        method=(
            "Both indexes share the same Okapi BM25 sparse leg (lab/common/index.BM25, unchanged). The classical "
            "index's dense leg is sklearn TfidfVectorizer cosine (EXP-004's substitute). The real index's dense leg "
            "is mean-pooled spaCy en_core_web_md static word vectors, min-max normalized and averaged 0.5/0.5 with "
            "the sparse score, same fusion formula as lab/common/index.Index. Two query sets run over the same 76 "
            "real passages from 25 real documents: (1) each chunk's own verified-substring extractive summary, gold "
            "is that chunk's id -- a sanity check where the query is literally inside the gold passage; (2) each "
            "document's real headline, gold is every chunk of that document's body -- a harder test where the query "
            "wording is not copied into any chunk."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=(
            "The real pretrained dense leg is measured against the classical TF-IDF dense leg on the same real "
            "corpus and the same two query sets. See real_model_card in the metrics for exactly which checkpoint "
            "ran and why it is not bge-small-en-v1.5. The two tests disagree: on the substring sanity check both "
            "legs sit at the Recall@5/10 ceiling, matching EXP-004's own 'reranker lift 0.0' finding on an easy set. "
            "On the harder headline test the real pretrained static-vector leg scores lower than classical TF-IDF "
            "(Recall@5 and @10 both negative lift). A plausible reason: mean-pooling 300-d vectors over a short, "
            "all-caps wire headline likely washes out the few content words that matter, while TF-IDF's rare-term "
            "weighting keeps exact shared tokens (a name, a commodity) salient. This closes the EXP-029 rerun todo "
            "for the embeddings component -- it is no longer unrun -- but the honest result is that this particular "
            "real pretrained encoder did not outperform the classical substitute on real documents at this scale."
        ),
        scale_down=(
            "25 real documents / 76 chunks, not a 1,000-page collection (EXP-022 on-disk index is still a separate "
            "todo). bge-small-en-v1.5, Qdrant sparse vectors, and bge-reranker-v2-m3 remain unloaded because "
            "huggingface.co is blocked by this sandbox's egress policy; see real_model_card."
        ),
        referenced_files=FILES,
        follow_ups=[
            "If huggingface.co access is ever granted in this sandbox, rerun with the actual bge-small-en-v1.5 checkpoint and compare against this spaCy result.",
            "Add a cross-encoder reranking pass once a real reranker checkpoint is reachable.",
        ],
        models_used=(
            "Real pretrained spaCy en_core_web_md static word vectors (GloVe-style, trained on a web/news crawl) "
            "for the dense leg, fused with the unchanged in-process Okapi BM25 sparse leg. bge-small-en-v1.5, "
            "Qdrant, and bge-reranker-v2-m3 were not loaded: huggingface.co is blocked in this sandbox (403 CONNECT, "
            "policy denial). This is a real, reachable, non-generative encoder, not the exact blueprint checkpoint. "
            "See lab/common/real_models.py:model_card()."
        ),
    )


if __name__ == "__main__":
    main()
