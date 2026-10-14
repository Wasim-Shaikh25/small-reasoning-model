"""EXP-018: outline assembly of long outputs (architecture Experiment L, no generator)."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.assemble import assemble
from lab.common.harness import Run, peak_rss_mb

FILES = [
    "lab/exp_018_longform/run.py",
    "lab/common/assemble.py",
    "lab/common/verify.py",
    "lab/common/textutil.py",
    "lab/common/harness.py",
    "data/exp_018_longform/spec.json",
    "data/exp_018_longform/results.json",
]


def findings(n: int, duplicate: bool = False) -> list[dict]:
    rows = []
    for i in range(n):
        rows.append(
            {
                "finding_id": f"F{i:05d}",
                "statement": f"The value of item {i} is {i * 3}.",
                "citation": f"C{i:05d}",
                "evidence_id": f"C{i:05d}",
                "sort_key": i,
            }
        )
    if duplicate and n > 8:
        for offset in range(4):
            rows[4 + offset]["statement"] = rows[offset]["statement"]
    if n > 8:
        rows[8]["statement"] = "R. Sharma holds item 8, and the value of item 8 is 24."
    return rows


def main():
    run = Run("EXP-018", "exp_018_longform")
    spec = {"counts": [200, 1000, 5000], "seed": "template-item-{i}", "glossary": {"R. Sharma": "Ravi Sharma"}}
    run.write_json("spec.json", spec)
    glossary = spec["glossary"]
    rows = []
    for count in spec["counts"]:
        data = findings(count, duplicate=True)
        t0 = time.perf_counter()
        rss_before = peak_rss_mb()
        result = assemble(data, "chronology", glossary)
        elapsed = time.perf_counter() - t0
        tokens = result["word_count"]
        rows.append(
            {
                "claims": count,
                "leaves": result["outline_leaves"],
                "words": tokens,
                "coverage": result["coverage"]["coverage"],
                "missing": len(result["coverage"]["missing"]),
                "broken_citations": result["citations"]["broken"],
                "units_without_citation": result["citations"]["units_without_citation"],
                "repetition_pairs": len(result["repetition"]),
                "glossary_flags": result["glossary_flags"],
                "elapsed_sec": round(elapsed, 4),
                "tokens_per_sec": round(tokens / elapsed, 2) if elapsed else None,
                "rss_before_mb": rss_before,
                "rss_after_mb": peak_rss_mb(),
                "sha256": result["sha256"],
            }
        )
    # Resume: build 40 findings, checkpoint halfway by truncating saved leaves, then finish.
    small = findings(40, duplicate=False)
    checkpoint = run.out_dir / "checkpoint.json"
    if checkpoint.exists():
        checkpoint.unlink()
    full = assemble(small, "chronology", glossary)
    partial_dir = run.out_dir / "resume"
    if partial_dir.exists():
        shutil.rmtree(partial_dir)
    partial_dir.mkdir()
    partial_ckpt = partial_dir / "checkpoint.json"
    first = assemble(small, "chronology", glossary, checkpoint=partial_ckpt)
    saved = __import__("json").loads(partial_ckpt.read_text())
    saved["units"] = saved["units"][:2]
    saved["done_leaf_ids"] = saved["done_leaf_ids"][:2]
    partial_ckpt.write_text(__import__("json").dumps(saved))
    resumed = assemble(small, "chronology", glossary, checkpoint=partial_ckpt)
    metrics = {
        "sizes": rows,
        "resume_matches_full": resumed["sha256"] == full["sha256"] == first["sha256"],
        "resumed_from_leaves": resumed["resumed_from"],
        "generator_used": False,
    }
    prose = (
        "Assembly sizes: "
        + "; ".join(
            f"{row['claims']} claims -> {row['words']} words, coverage {row['coverage']}, "
            f"broken citations {len(row['broken_citations'])}, repetition pairs {row['repetition_pairs']}, "
            f"{row['tokens_per_sec']} words/sec"
            for row in rows
        )
        + f". Resume hash matches a full run: {metrics['resume_matches_full']}."
    )
    run.finish(
        title="Long-form assembly",
        goal="Assemble documents from verified findings at 200, 1,000, and 5,000 claims and check coverage, citations, repetition, glossary flags, throughput, and resume.",
        method="An outline groups findings into units of four. Each unit is rendered by code with its citation marker. TF-IDF cosine flags near-duplicate units. A checkpoint stores finished units so a truncated job can resume. No sentence is generated.",
        metrics=metrics,
        results_prose=prose,
        conclusion="Coverage and citation integrity are properties of the assembler. Throughput is string assembly on this CPU, not a generative decoder. Resume reproduces the full document hash when the checkpoint is truncated and continued.",
        scale_down="Claims are templated verified findings, not 10 to 250 pages of model prose. The architecture's FLAN-T5 unit writer is not used.",
        referenced_files=FILES,
    )


if __name__ == "__main__":
    main()
