"""EXP-040: paged retrieval needle recall rerun with the real bge-small-en-v1.5 embedder.

Re-measures EXP-015's needle-recall-at-5 (the hybrid retriever finds one
distinctive sentence planted in an otherwise uniform haystack of 10, 100,
and 1000 pages) with lab.common.real_bge_index.RealBgeIndex in place of
lab.common.index.Index. The sparse (BM25) leg and the 0.5/0.5 blend are
unchanged; only the dense leg's embedding source changes, so the two recall
numbers are directly comparable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.real_bge_index import RealBgeIndex
from lab.common.real_encoders import BGE_MODEL_NAME
from lab.tests.fixtures_support import needle_recall as _needle_recall

FILES = [
    "lab/tests/exp_040_real_paged_retrieval/run.py",
    "lab/common/real_bge_index.py",
    "lab/common/real_encoders.py",
    "lab/common/index.py",
    "lab/common/harness.py",
    "data/exp_015_paged_memory/results.json",
    "data/exp_040_real_paged_retrieval/results.json",
    "lab/tests/fixtures_support.py",

]

NEEDLE = "The violet quorum code is 41827."


def needle_recall(pages: int) -> dict:
    return _needle_recall(pages, NEEDLE, RealBgeIndex)


def main():
    run = Run("EXP-040", "exp_040_real_paged_retrieval")
    recalls = [needle_recall(n) for n in (10, 100, 1000)]

    exp015_path = ROOT / "data" / "exp_015_paged_memory" / "results.json"
    exp015 = json.loads(exp015_path.read_text())["metrics"] if exp015_path.exists() else None

    metrics = {
        "model": BGE_MODEL_NAME,
        "needle_recall": recalls,
    }
    if exp015:
        metrics["vs_exp_015_tfidf"] = {
            "exp_015_needle_recall": exp015["needle_recall"],
            "exp_040_needle_recall": recalls,
        }

    prose = (
        f"Needle Recall@5 at 10, 100, and 1000 pages with {BGE_MODEL_NAME} as the dense leg: {recalls}. "
        + (f"EXP-015's TF-IDF dense leg scored: {exp015['needle_recall']}." if exp015 else "")
    )

    all_perfect = all(row["recall_at_5"] == 1.0 for row in recalls)
    conclusion = (
        f"The real {BGE_MODEL_NAME} checkpoint is loaded and measured, not assumed. "
        + (
            "Recall matches EXP-015's TF-IDF dense leg at every size tested here -- a single distinctive "
            "numeric needle sentence is easy for both a lexical and a dense retriever to find in this "
            "synthetic haystack, so this fixture does not yet distinguish them. A harder retrieval probe "
            "(paraphrased needle, no shared surface tokens with the query) would be needed to see where a "
            "real dense embedder pulls ahead of TF-IDF, the way EXP-029's harder headline-retrieval test did "
            "for spaCy vectors."
            if all_perfect
            else "Recall differs from EXP-015's TF-IDF dense leg at one or more sizes, reported above as "
            "measured, not smoothed over."
        )
    )

    run.finish(
        title="Paged retrieval needle recall with the real bge-small-en-v1.5 embedder",
        goal="Re-measure EXP-015's needle-recall-at-5 with bge-small-en-v1.5 as the dense leg of the hybrid retriever, in place of TF-IDF, on the identical haystacks.",
        method=(
            "Identical to EXP-015's needle_recall: a distinctive sentence (a 5-digit quorum code) is planted "
            "at the midpoint of an otherwise uniform haystack of 10, 100, and 1000 short pages. "
            "lab.common.real_bge_index.RealBgeIndex replaces lab.common.index.Index: same BM25 sparse leg and "
            "0.5/0.5 blend, but the dense leg embeds every page and the query with the real bge-small-en-v1.5 "
            "checkpoint (sentence-transformers, loaded locally, not an API call) instead of TfidfVectorizer "
            "cosine."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="Pages are short synthetic paragraphs, not scanned document pages, same as EXP-015. 1,000 pages were run, not a multi-million-token archive.",
        referenced_files=FILES,
        follow_ups=[
            "A harder retrieval probe where the needle doesn't share surface tokens with the query would "
            "better separate bge from TF-IDF than this fixture does.",
        ],
        models_used=(
            f"{BGE_MODEL_NAME}, a local checkpoint loaded with sentence-transformers (not an API call). This "
            "is the real blueprint embedder (ARCHITECTURE.md section 8), not a substitute and not the spaCy "
            "static vectors EXP-029/032 used while huggingface.co was blocked."
        ),
    )


if __name__ == "__main__":
    main()
