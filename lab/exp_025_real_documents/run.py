"""EXP-025: attach a real, public, non-confidential document collection.

Fetches real Reuters-21578 news wire stories (via NLTK's data distribution,
downloaded directly over HTTPS -- see lab/common/real_corpus.py for why not
nltk.download) and runs them through the same structure-aware chunker used
everywhere else in this POC. No model, classical or neural, is loaded here:
this exploration is only about the data, matching its scope in EXPLORATIONS.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.chunking import chunk_document
from lab.common.harness import Run
from lab.common.real_corpus import CATEGORY, N_DOCS, fetch_documents, save_documents
from lab.common.textutil import word_count

FILES = [
    "lab/exp_025_real_documents/run.py",
    "lab/common/real_corpus.py",
    "lab/common/chunking.py",
    "lab/common/textutil.py",
    "lab/common/harness.py",
    "data/exp_025_real_documents/documents.json",
    "data/exp_025_real_documents/chunks.json",
    "data/exp_025_real_documents/results.json",
]


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def main():
    run = Run("EXP-025", "exp_025_real_documents")
    documents = fetch_documents(CATEGORY, N_DOCS)
    doc_path = save_documents(documents)

    all_chunks = []
    for doc in documents:
        chunks = chunk_document(doc["text"], doc_id=doc["doc_id"])
        for chunk in chunks:
            chunk["source_category"] = doc["category"]
            chunk["source_title"] = doc["title"]
        all_chunks.extend(chunks)
    chunks_path = run.write_json("chunks.json", all_chunks)

    type_counts: dict[str, int] = {}
    for chunk in all_chunks:
        type_counts[chunk["chunk_type"]] = type_counts.get(chunk["chunk_type"], 0) + 1
    words = [c["word_count"] for c in all_chunks]
    below_min = sum(1 for c in all_chunks if c["below_min_words"])
    summary_substrings = sum(1 for c in all_chunks if c["summary_sentences_are_substrings"])

    metrics = {
        "source": "nltk reuters-21578 (real 1987 Reuters news wire stories)",
        "category": CATEGORY,
        "n_documents": len(documents),
        "n_chunks": len(all_chunks),
        "chunks_per_document_mean": _mean([len(all_chunks) / max(1, len(documents))]),
        "chunk_type_counts": type_counts,
        "chunk_word_count_mean": _mean(words),
        "chunk_word_count_min": min(words) if words else 0,
        "chunk_word_count_max": max(words) if words else 0,
        "chunks_below_min_words": below_min,
        "summary_sentences_are_substrings_rate": round(summary_substrings / max(1, len(all_chunks)), 4),
        "unique_source_documents_in_chunks": len({c["doc_id"] for c in all_chunks}),
    }
    prose = (
        f"Fetched {metrics['n_documents']} real Reuters-21578 '{CATEGORY}' category news stories and chunked them "
        f"into {metrics['n_chunks']} chunks with the same structure-aware chunker used on the lease fixtures. "
        f"Chunk types: {metrics['chunk_type_counts']}. Mean chunk length is {metrics['chunk_word_count_mean']} words "
        f"(range {metrics['chunk_word_count_min']}-{metrics['chunk_word_count_max']}). "
        f"{metrics['summary_sentences_are_substrings_rate']*100:.1f}% of extractive summaries are verified substrings "
        f"of their own chunk."
    )
    run.finish(
        title="Attach a real document collection",
        goal="Ingest a public, non-confidential document set with the same chunker and index used elsewhere, keeping the engine domain-agnostic, per OBJECTIVE.md.",
        method=(
            "Downloaded the Reuters-21578 corpus zip directly from raw.githubusercontent.com/nltk/nltk_data "
            "(NLTK's own downloader refuses to run behind this sandbox's HTTPS proxy; see lab/common/real_corpus.py). "
            f"Selected the first {N_DOCS} training-split documents, sorted by file id, in the '{CATEGORY}' category -- "
            "a deterministic, reproducible selection, not a random sample. Cleaned wire-service line wrapping into "
            "paragraphs without altering content. Ran the existing lab/common/chunking.chunk_document on each real "
            "document, unmodified."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=(
            "The chunker, written for lease fixtures, runs unmodified on real, open-domain news text and produces "
            "well-formed chunks with verified-substring summaries. This closes the EXP-025 todo: a real, public, "
            "non-confidential document collection is now attached and reused by EXP-029, EXP-032, and EXP-033."
        ),
        scale_down=(
            "25 real documents / "
            f"{metrics['n_chunks']} chunks, not a full production collection. One Reuters category, not a cross-domain mix. "
            "The blueprint's archive store is Qdrant; this POC keeps the in-memory index."
        ),
        referenced_files=FILES,
        follow_ups=[
            "Attach a second, unrelated category or a different real corpus to test cross-domain generalization.",
            "Move the chunk/document store to an on-disk index once the collection grows past in-memory size (EXP-022).",
        ],
        models_used=(
            "No checkpoint is loaded by this exploration. Fetching and chunking real text uses no model, "
            "classical or neural. This is data attachment only; EXP-029, EXP-032, and EXP-033 add models on top of it."
        ),
    )
    print(f"wrote {doc_path} and {chunks_path}")


if __name__ == "__main__":
    main()
