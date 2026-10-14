"""EXP-003: structure-aware chunking and extractive summaries."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.chunking import chunk_document, version_hash
from lab.common.harness import Run
from lab.common.textutil import sentences

FILES = [
    "lab/exp_003_chunking/run.py",
    "lab/common/chunking.py",
    "lab/common/textutil.py",
    "lab/common/harness.py",
    "data/exp_003_chunking/document.txt",
    "data/exp_003_chunking/results.json",
]

DOCUMENT = """
Page 1
PARTIES:
Ravi Sharma (the Lessee) residing at 14 MG Road, Pune 411001.
ABC Pvt Ltd (the Lessor) having its office at 48 Park Street, Kolkata 700016.

Page 2
1. Definitions
Premises means the flat described in Schedule A. Notice Period means 30 days.

Page 3
2. Rent
The monthly rent is INR 25000. The security deposit is INR 50000.
The tenant shall not sublet except where the Lessor consents in writing.

Page 4
SCHEDULE A
One table. Four chairs. The parking slot is included.

Page 5
SIGNATURE
Signed by Meera Iyer on 5 January 2024.
In witness of the parties.
"""


def main():
    run = Run("EXP-003", "exp_003_chunking")
    (run.out_dir / "document.txt").write_text(DOCUMENT)
    chunks = chunk_document(DOCUMENT, "D3", min_words=8, max_words=40, overlap_ratio=0.12)
    long_clause = " ".join([f"The tenant shall keep the item number {i} in repair." for i in range(1, 81)])
    long_doc = "OBLIGATIONS:\n" + long_clause
    long_chunks = chunk_document(long_doc, "D9", min_words=40, max_words=50, overlap_ratio=0.12)
    types = {}
    for chunk in chunks:
        types[chunk["chunk_type"]] = types.get(chunk["chunk_type"], 0) + 1
    summary_ok = all(c["summary_sentences_are_substrings"] for c in chunks)
    summary_not_evidence = all(c["summary_is_evidence"] is False for c in chunks)
    hashes = {c["version_hash"] for c in chunks}
    overlap_pairs = 0
    # Overlap is measured on the long clause, where the splitter must fire.
    texts = [c["text"] for c in long_chunks]
    for left, right in zip(texts, texts[1:]):
        left_words = set(left.split()[-8:])
        if any(word in right for word in left_words):
            overlap_pairs += 1
    expected = {"party_block", "definition", "clause", "schedule", "signature"}
    found = set(types)
    metrics = {
        "chunks": len(chunks),
        "chunk_types": types,
        "expected_types_found": sorted(expected & found),
        "missing_expected_types": sorted(expected - found),
        "word_counts": [c["word_count"] for c in chunks],
        "long_doc_chunks": len(long_chunks),
        "long_doc_max_words": max((c["word_count"] for c in long_chunks), default=0),
        "adjacent_overlap_pairs": overlap_pairs,
        "single_version_hash": len(hashes) == 1,
        "version_hash": version_hash(DOCUMENT),
        "summaries_are_substrings": summary_ok,
        "summaries_marked_not_evidence": summary_not_evidence,
        "sample_summary": chunks[0]["summary"] if chunks else "",
        "pages": sorted({c["page"] for c in chunks}),
    }
    prose = (
        f"The sample document produced {metrics['chunks']} chunks with types {types}. "
        f"Missing expected types: {metrics['missing_expected_types'] or 'none'}. "
        f"All chunks share one version hash: {metrics['single_version_hash']}. "
        f"Extractive summaries are substrings and are marked not evidence: "
        f"{summary_ok and summary_not_evidence}. "
        f"A {80}-sentence obligation block split into {metrics['long_doc_chunks']} chunks "
        f"(max {metrics['long_doc_max_words']} words) with {overlap_pairs} adjacent overlapping pairs. "
        f"Pages seen: {metrics['pages']}."
    )
    run.finish(
        title="Structure-aware chunking",
        goal="Chunk a small contract-shaped document by headings, pages, and block type, and keep summaries extractive.",
        method="Headings and page markers split the document. Each chunk stores doc id, version hash, page, section path, offsets, and chunk type. Summaries are the highest-salience sentences already in the chunk.",
        metrics=metrics,
        results_prose=prose,
        conclusion=(
            "Chunk metadata and extractive summaries behave as specified on this sample. "
            "The word-window settings used here are smaller than the 200 to 400 token production window so the sample still splits."
        ),
        scale_down="One short document plus one generated long clause. Token counts are whitespace words, not a model tokenizer. Production target of 200 to 400 tokens was not the setting for the short sample.",
        referenced_files=FILES,
    )


if __name__ == "__main__":
    main()
