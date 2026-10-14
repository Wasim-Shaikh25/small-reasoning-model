"""Outline-driven assembly of verified findings. Code writes the document; nothing is generated."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from lab.common.textutil import word_count
from lab.common.verify import citation_markers


def build_outline(findings: list[dict], task: str) -> list[dict]:
    if task == "chronology":
        ordered = sorted(findings, key=lambda f: (f.get("sort_key") is None, f.get("sort_key"), f.get("finding_id")))
    else:
        ordered = list(findings)
    leaves = []
    unit: list[dict] = []
    for finding in ordered:
        unit.append(finding)
        if len(unit) == 4:
            leaves.append(unit)
            unit = []
    if unit:
        leaves.append(unit)
    return [
        {
            "leaf_id": f"L{i:04d}",
            "title": f"Section {i + 1}",
            "finding_ids": [f["finding_id"] for f in leaf],
            "findings": leaf,
        }
        for i, leaf in enumerate(leaves)
    ]


def render_unit(leaf: dict, glossary: dict[str, str]) -> str:
    lines = [leaf["title"]]
    for finding in leaf["findings"]:
        statement = finding["statement"]
        for variant, canonical in glossary.items():
            statement = re.sub(rf"\b{re.escape(variant)}\b", canonical, statement)
        cite = finding.get("citation") or finding.get("evidence_id")
        lines.append(f"{statement} [{cite}]")
    return "\n".join(lines)


def repetition_pairs(units: list[str], threshold: float = 0.92) -> list[dict]:
    if len(units) < 2:
        return []
    # Citations and section numbers are assembly chrome. Repetition is about the findings.
    stripped = []
    for unit in units:
        body = re.sub(r"\[[^\]]+\]", " ", unit)
        body = re.sub(r"^Section \d+\s*", "", body)
        stripped.append(body)
    vectorizer = TfidfVectorizer(stop_words="english")
    matrix = vectorizer.fit_transform(stripped)
    sims = cosine_similarity(matrix)
    pairs = []
    for i in range(len(units)):
        for j in range(i + 1, len(units)):
            if sims[i, j] >= threshold:
                pairs.append({"i": i, "j": j, "similarity": round(float(sims[i, j]), 4)})
    return pairs


def coverage_report(findings: list[dict], document: str) -> dict:
    present = []
    missing = []
    for finding in findings:
        cite = finding.get("citation") or finding.get("evidence_id")
        if f"[{cite}]" in document or finding["statement"] in document:
            present.append(finding["finding_id"])
        else:
            missing.append(finding["finding_id"])
    return {
        "present": len(present),
        "missing": missing,
        "coverage": round(len(present) / max(1, len(findings)), 4),
    }


def citation_integrity(document: str, valid_ids: set[str]) -> dict:
    markers = citation_markers(document)
    broken = [m for m in markers if m not in valid_ids]
    units_without = []
    for i, block in enumerate(document.split("\n\n")):
        if block.strip() and "[" not in block:
            units_without.append(i)
    return {
        "markers": len(markers),
        "broken": broken,
        "units_without_citation": units_without,
    }


def glossary_flags(document: str, variants: dict[str, str]) -> list[dict]:
    flags = []
    for variant, canonical in variants.items():
        if re.search(rf"\b{re.escape(variant)}\b", document) and variant != canonical:
            flags.append({"variant": variant, "canonical": canonical})
    return flags


def assemble(findings: list[dict], task: str, glossary: dict[str, str], checkpoint: Path | None = None) -> dict:
    outline = build_outline(findings, task)
    rendered = []
    resumed_from = None
    done_ids = set()
    if checkpoint and checkpoint.exists():
        saved = json.loads(checkpoint.read_text())
        rendered = saved["units"]
        done_ids = set(saved["done_leaf_ids"])
        resumed_from = len(done_ids)
    for leaf in outline:
        if leaf["leaf_id"] in done_ids:
            continue
        rendered.append(render_unit(leaf, glossary))
        done_ids.add(leaf["leaf_id"])
        if checkpoint:
            checkpoint.write_text(
                json.dumps({"units": rendered, "done_leaf_ids": sorted(done_ids)})
            )
    document = "\n\n".join(rendered)
    valid_ids = {f.get("citation") or f.get("evidence_id") for f in findings}
    raw_blob = "\n".join(f["statement"] for f in findings)
    return {
        "document": document,
        "outline_leaves": len(outline),
        "word_count": word_count(document),
        "sha256": hashlib.sha256(document.encode()).hexdigest(),
        "coverage": coverage_report(findings, document),
        "citations": citation_integrity(document, valid_ids),
        "repetition": repetition_pairs(rendered),
        "glossary_flags": glossary_flags(raw_blob, glossary),
        "resumed_from": resumed_from,
        "input_hash": hashlib.sha256(json.dumps([f["finding_id"] for f in findings]).encode()).hexdigest(),
    }
