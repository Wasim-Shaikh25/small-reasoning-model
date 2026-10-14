"""Verification checks. A failure removes the claim or asks for another retrieval."""

from __future__ import annotations

from lab.common.nli import judge
from lab.common.qa import spans_overlap
from lab.common.textutil import modals, normalize, numbers, span_in_passage

QUALIFIERS = ("clearly", "always", "obviously", "undoubtedly", "certainly")


def quote_check(span: str | None, passage: str | None) -> bool:
    return span_in_passage(span, passage)


def support_check(claim: str, passage: str, tau: float = 0.55) -> dict:
    probs = judge(passage, claim)
    return {"ok": probs["entail"] >= tau and probs["contradict"] < 0.45, "nli": probs}


def conflict_across(claim_sets: list[tuple[str, str]]) -> list[dict]:
    """claim_sets: (passage_id, span) pairs that answer the same fact."""
    conflicts = []
    for i, (id_a, span_a) in enumerate(claim_sets):
        for id_b, span_b in claim_sets[i + 1 :]:
            if normalize(span_a) == normalize(span_b):
                continue
            probs = judge(f"The value is {span_a}.", f"The value is {span_b}.")
            if probs["contradict"] >= 0.45 or set(numbers(span_a)) != set(numbers(span_b)):
                conflicts.append({"a": id_a, "b": id_b, "span_a": span_a, "span_b": span_b, "nli": probs})
    return conflicts


def coverage_check(facts: list[dict]) -> dict:
    missing = [f for f in facts if f.get("status") == "missing"]
    found = [f for f in facts if f.get("status") == "found"]
    conflicted = [f for f in facts if f.get("status") == "conflicted"]
    total = len(facts) or 1
    return {
        "found": len(found),
        "missing": len(missing),
        "conflicted": len(conflicted),
        "coverage_ratio": round(len(found) / total, 4),
        "complete": len(missing) == 0 and len(conflicted) == 0 and len(facts) > 0,
    }


def calculation_check(reported: str, recomputed: str) -> bool:
    return normalize(reported) == normalize(recomputed)


def qualifier_added(source: str, output: str) -> list[str]:
    added = []
    src = source.lower()
    for word in QUALIFIERS:
        if word in output.lower() and word not in src:
            added.append(word)
    return added


def citation_markers(text: str) -> list[str]:
    import re

    return re.findall(r"\[([A-Za-z0-9_-]+)\]", text or "")


def modality_preserved(source: str, output: str) -> bool:
    return sorted(modals(source)) == sorted(modals(output))


def entity_number_check(source: str, output: str) -> dict:
    src_nums, out_nums = set(numbers(source)), set(numbers(output))
    return {
        "numbers_dropped": sorted(src_nums - out_nums),
        "numbers_added": sorted(out_nums - src_nums),
        "ok": not (src_nums - out_nums or out_nums - src_nums),
    }


def bidirectional_nli(source: str, output: str, tau: float = 0.55) -> dict:
    forward = judge(source, output)
    backward = judge(output, source)
    return {
        "forward": forward,
        "backward": backward,
        "ok": forward["entail"] >= tau and backward["entail"] >= tau,
    }


def second_span_agrees(span_a: str | None, span_b: str | None) -> bool:
    return spans_overlap(span_a, span_b)


def contradiction_queries(slot: str) -> list[str]:
    slot = slot.strip() or "claim"
    return [
        f"{slot} except",
        f"{slot} unless",
        f"{slot} not",
        f"{slot} provided that",
        f"no {slot}",
    ]


def output_validator(text: str, findings_text: str, citations: list[str], decision: str) -> dict:
    missing_citations = [c for c in citations if f"[{c}]" not in text]
    qualifiers = qualifier_added(findings_text, text)
    numbers_ok = entity_number_check(findings_text, text)["ok"]
    modals_ok = modality_preserved(findings_text, text)
    caveat_ok = True
    if decision in {"inconclusive", "ambiguous"}:
        caveat_ok = any(word in text.lower() for word in ("insufficient", "ambiguous", "unresolved", "missing"))
    ok = not missing_citations and not qualifiers and numbers_ok and modals_ok and caveat_ok
    return {
        "ok": ok,
        "missing_citations": missing_citations,
        "qualifiers_added": qualifiers,
        "numbers_ok": numbers_ok,
        "modals_ok": modals_ok,
        "caveat_ok": caveat_ok,
    }
