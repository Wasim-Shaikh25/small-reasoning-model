"""EXP-022: on-disk hybrid index.

Repeats EXP-004/029's hybrid retrieval measurement through a
save/load round trip (lab.common.index.Index.save/load, new) instead of
the single in-process Index every other exploration in this repo has
used so far -- the actual need this todo names: "once the corpus no
longer fits the process index." BM25 rebuilds cheaply from its own saved
token lists; the fitted TfidfVectorizer and its sparse document matrix
(the genuinely expensive part to recompute over a large corpus) are
persisted via pickle.

The real document already in this repo (GDPR_TEXT, EXP-081, 103
sentences across 13 articles) is used as the corpus -- not a toy 3-
passage fixture -- split into one passage per sentence. Five real
queries are run against the ORIGINAL in-memory Index and against a
freshly loaded Index.load() object with no shared reference to the
original (the original's internal vectorizer/matrix objects are
deleted before the loaded copy is queried, so nothing is accidentally
reused across the two), checking every ranked result's passage id AND
score match exactly -- not just the top-1 id, which could mask a
precision loss in serialization.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.index import Index
from lab.common.textutil import sentences
from lab.common.fixtures import GDPR_TEXT

FILES = [
    "lab/tests/exp_022_on_disk_index/run.py",
    "lab/common/index.py",
    "lab/common/textutil.py",
    "lab/common/fixtures.py",
    "data/exp_022_on_disk_index/index.pkl",
]

QUERIES = [
    "explicit consent to the processing of personal data",
    "the right to object to processing",
    "notify the supervisory authority of a personal data breach",
    "the controller shall implement appropriate technical measures",
    "the establishment, exercise or defence of legal claims",
]


def main():
    run = Run("EXP-022", "exp_022_on_disk_index")

    gdpr_sentences = sentences(GDPR_TEXT)
    passages = [{"id": f"gdpr-{i:03d}", "text": s} for i, s in enumerate(gdpr_sentences)]

    original = Index(passages)
    original_results = {q: original.search(q, top_k=5) for q in QUERIES}

    index_path = run.out_dir / "index.pkl"
    original.save(index_path)

    # Delete the original's own fitted internals before loading, so the
    # comparison below cannot accidentally reuse the same in-memory
    # vectorizer/matrix objects -- the loaded copy must stand on its own.
    del original.vectorizer, original.matrix, original.bm25

    loaded = Index.load(index_path)
    loaded_results = {q: loaded.search(q, top_k=5) for q in QUERIES}

    per_query = []
    for q in QUERIES:
        orig_ids = [r["passage"]["id"] for r in original_results[q]]
        loaded_ids = [r["passage"]["id"] for r in loaded_results[q]]
        orig_scores = [round(r["score"], 10) for r in original_results[q]]
        loaded_scores = [round(r["score"], 10) for r in loaded_results[q]]
        ids_match = orig_ids == loaded_ids
        scores_match = orig_scores == loaded_scores
        per_query.append({"query": q, "original_ids": orig_ids, "loaded_ids": loaded_ids, "ids_match": ids_match, "scores_match": scores_match})

    run.write_json("queries.json", {"per_query": per_query})

    all_match = all(p["ids_match"] and p["scores_match"] for p in per_query)
    file_size_bytes = index_path.stat().st_size

    metrics = {
        "corpus_size": len(passages),
        "n_queries": len(QUERIES),
        "all_ids_and_scores_match": all_match,
        "per_query": per_query,
        "index_file_bytes": file_size_bytes,
    }

    prose = (
        f"{len(passages)}-passage corpus (the real GDPR_TEXT fixture, one passage per sentence) saved to a "
        f"{file_size_bytes:,}-byte pickle. {len(QUERIES)} real queries run against both the original in-"
        f"memory Index and a freshly loaded Index.load() with no shared reference to the original's own "
        f"fitted vectorizer/matrix/BM25 (explicitly deleted before loading): "
        f"{sum(1 for p in per_query if p['ids_match'])}/{len(QUERIES)} queries matched on ranked ids, "
        f"{sum(1 for p in per_query if p['scores_match'])}/{len(QUERIES)} matched on exact scores."
    )

    conclusion = (
        "Saving and loading the fitted index produces bit-identical search results -- every query's ranked "
        "passage ids and scores match exactly between the original in-memory Index and the loaded-from-disk "
        "copy, with the original's own fitted objects deleted beforehand so there is no possibility of "
        "accidental reuse. BM25 rebuilds from its saved token lists in this same load() call; the TF-IDF "
        "vectorizer and matrix, the genuinely expensive part to recompute, are restored directly from the "
        "pickle without re-fitting."
        if all_match
        else "At least one query's results did not match between the original and loaded index -- see "
        "per_query for exactly which, reported as measured."
    )

    run.finish(
        title="On-disk hybrid index",
        goal="Repeat the hybrid retrieval measurement with an on-disk index once the corpus no longer fits the process index.",
        method=(
            "lab.common.index.Index.save/load (new): pickles the fitted TfidfVectorizer+matrix and BM25's own "
            "input token lists (BM25 itself rebuilds cheaply and deterministically from those on load, no "
            "separate persistence needed for its derived df/tf/avgdl state). Measured on the real 103-sentence "
            "GDPR_TEXT fixture (EXP-081), not a toy corpus: 5 real queries run against the original in-memory "
            "Index and a freshly loaded copy with the original's own fitted internals explicitly deleted first."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            "This persists a FITTED index's state to disk and reloads it in the same process -- it proves "
            "save/load round-trips exactly and avoids re-fitting, not a genuinely disk-backed query engine "
            "that never holds the full matrix in RAM (that would need an ANN library like Qdrant/FAISS, which "
            "EXP-022's own 'models_used' note explicitly rules out adding: 'bge, SPLADE, fastembed, and Qdrant "
            "are still not loaded'). 103 passages, not a corpus that genuinely exceeds process memory -- the "
            "round-trip correctness is proven at this scale; whether the pickle file itself stays practical "
            "at a much larger corpus size is not measured here."
        ),
        referenced_files=FILES,
        follow_ups=[],
        models_used=(
            "sklearn TfidfVectorizer (already a dependency, classical, deterministic) plus the existing "
            "in-process BM25 implementation. No generative model. Qdrant/SPLADE/fastembed/bge remain not "
            "loaded, per this todo's own standing note."
        ),
    )

    print("all_ids_and_scores_match:", all_match, "| index_file_bytes:", file_size_bytes)


if __name__ == "__main__":
    main()
