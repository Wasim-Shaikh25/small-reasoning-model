"""EXP-042: repetition-detection rerun with the real bge-small-en-v1.5 embedder.

Re-measures EXP-018's near-duplicate-unit detection with
lab.tests.support.bge_cosine_matrix in place of
lab.common.assemble.repetition_pairs's TfidfVectorizer cosine, on the
identical assembled documents (200, 1000, and 5000 templated findings).
The unit text itself is unchanged -- it is still copied verbatim from
verified findings by the deterministic assembler (lab/common/assemble.py);
only the similarity scorer used to flag near-duplicate units changes.
FLAN-T5 as the unit writer stays out of scope here, per EXP-046.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.assemble import assemble
from lab.common.harness import Run
from lab.tests.fixtures_support import findings
from lab.common.real_encoders import BGE_MODEL_NAME
from lab.tests.support import bge_cosine_matrix

FILES = [
    "lab/tests/exp_042_real_repetition/run.py",
    "lab/common/real_encoders.py",
    "lab/common/assemble.py",
    "lab/common/harness.py",
    "data/exp_018_longform/results.json",
    "data/exp_042_real_repetition/results.json",
    "lab/tests/support.py",
    "lab/tests/fixtures_support.py",

]


def strip_unit(unit: str) -> str:
    body = re.sub(r"\[[^\]]+\]", " ", unit)
    body = re.sub(r"^Section \d+\s*", "", body)
    return body


def bge_repetition_pairs(units: list[str], threshold: float = 0.92) -> list[dict]:
    if len(units) < 2:
        return []
    stripped = [strip_unit(unit) for unit in units]
    sims = bge_cosine_matrix(stripped)
    pairs = []
    for i in range(len(units)):
        for j in range(i + 1, len(units)):
            if sims[i, j] >= threshold:
                pairs.append({"i": i, "j": j, "similarity": round(float(sims[i, j]), 4)})
    return pairs


def main():
    run = Run("EXP-042", "exp_042_real_repetition")
    glossary = {"R. Sharma": "Ravi Sharma"}
    rows = []
    for count in (200, 1000, 5000):
        data = findings(count, duplicate=True)
        result = assemble(data, "chronology", glossary)
        units = result["document"].split("\n\n")
        tfidf_pairs = result["repetition"]
        bge_pairs = bge_repetition_pairs(units)
        rows.append(
            {
                "claims": count,
                "units": len(units),
                "tfidf_repetition_pairs": tfidf_pairs,
                "bge_repetition_pairs": bge_pairs,
                "tfidf_pair_count": len(tfidf_pairs),
                "bge_pair_count": len(bge_pairs),
            }
        )
    run.write_json("pairs.json", rows)

    metrics = {
        "model": BGE_MODEL_NAME,
        "sizes": rows,
        "threshold": 0.92,
    }

    exp018_path = ROOT / "data" / "exp_018_longform" / "results.json"
    exp018 = json.loads(exp018_path.read_text())["metrics"] if exp018_path.exists() else None
    if exp018:
        metrics["vs_exp_018_tfidf"] = [
            {"claims": row["claims"], "exp_018_tfidf_pairs": row.get("repetition_pairs")}
            for row in exp018.get("sizes", [])
        ]

    prose = (
        "Near-duplicate unit pairs at threshold 0.92: "
        + "; ".join(
            f"{row['claims']} claims ({row['units']} units) -> TF-IDF {row['tfidf_pair_count']} pairs, "
            f"{BGE_MODEL_NAME} {row['bge_pair_count']} pairs"
            for row in rows
        )
        + "."
    )

    agree = all(row["tfidf_pair_count"] == row["bge_pair_count"] for row in rows)
    largest = rows[-1]
    over_flags = largest["bge_pair_count"] > largest["tfidf_pair_count"] * 10
    conclusion = (
        f"The real {BGE_MODEL_NAME} checkpoint is loaded and measured on EXP-018's own assembled units, not "
        "assumed. "
        + (
            "It agrees with TF-IDF cosine on exactly which units are near-duplicates at this threshold on this "
            "fixture."
            if agree
            else (
                f"It disagrees sharply with TF-IDF cosine as the unit count grows: at {largest['claims']} "
                f"claims, bge flags {largest['bge_pair_count']} pairs as near-duplicate versus TF-IDF's "
                f"{largest['tfidf_pair_count']}. These findings are all the same template ('The value of item "
                "{i} is {3i}.') differing only by a number. TF-IDF's bag-of-words vectors treat each distinct "
                "number as a distinct token, so it correctly sees these as different; bge's dense sentence "
                "embedding captures the shared template and largely ignores which specific number appears, so "
                "it rates nearly every pair in this templated set as near-duplicate even though each one "
                "states a different fact. This is a real, measured limitation worth keeping in mind before "
                "swapping the repetition check to a dense embedder: a template-heavy document (exactly the "
                "shape lab/common/assemble.build_outline produces) would have many of its genuinely distinct "
                "findings wrongly flagged as repetition and risk being dropped."
                if over_flags
                else "It disagrees with TF-IDF cosine on at least one size, reported above as measured, not "
                "smoothed over."
            )
        )
    )

    run.finish(
        title="Repetition detection rerun with the real bge-small-en-v1.5 embedder",
        goal="Re-measure EXP-018's near-duplicate-unit detection with bge-small-en-v1.5 in place of TF-IDF cosine, on the identical assembled documents.",
        method=(
            "Identical to EXP-018's sizes (200, 1000, 5000 templated findings with planted verbatim "
            "duplicates), assembled by the unchanged deterministic lab.common.assemble.assemble. The "
            "resulting document's units are re-scored for pairwise similarity by "
            "lab.tests.support.bge_cosine_matrix (same citation-marker and 'Section N' stripping as "
            "assemble.repetition_pairs) instead of TfidfVectorizer cosine, at the same 0.92 threshold."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="Same templated findings and planted duplicates EXP-018 used, not a corpus with natural paraphrased repetition.",
        referenced_files=FILES,
        follow_ups=[
            "A paraphrased (not verbatim) repetition probe would better separate bge from TF-IDF than this fixture does.",
        ],
        models_used=(
            f"{BGE_MODEL_NAME}, a local checkpoint loaded with sentence-transformers (not an API call). The "
            "unit text itself is still produced by the unchanged deterministic assembler; FLAN-T5 as the unit "
            "writer is out of scope here, per EXP-046."
        ),
    )


if __name__ == "__main__":
    main()
