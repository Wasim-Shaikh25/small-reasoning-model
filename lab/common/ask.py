"""Ask analyzer: task type, depth, keyphrases, template sub-questions, query variants.

No generator. Unusual multi-clause asks are a known weak spot (architecture section 3.2).
"""

from __future__ import annotations

import re

from lab.common.textutil import content_tokens, word_count

REWRITE_CUES = (
    "rewrite", "simplify", "formalize", "formalise", "shorten", "rephrase",
    "paraphrase", "make this shorter", "in memo style",
)
COMPARE_CUES = (
    "compare", "comparison", "difference", "differ", "versus", " vs ", "vs.",
    "which is longer", "which is higher", "side by side",
)
CHRON_CUES = (
    "timeline", "chronology", "in what order", "sequence", "before or after",
    "when did", "when does", "when was", "what date", "how long after",
    "which came first", "order of",
)
ENTITY_CUES = (
    "who is", "who was", "who are", "address of", "lessee", "lessor",
    "the parties", "which party", "whose address",
)
REASON_CUES = (
    "why ", "why?", "what happens if", "unless", "provided that", "is it permitted",
    "on condition",
)


def _has(text: str, cues: tuple[str, ...]) -> bool:
    low = f" {text.lower()} "
    return any(cue in low or cue in text.lower() for cue in cues)


def classify_task(ask: str) -> str:
    low = ask.lower().strip()
    if any(low.startswith(cue) or f" {cue} " in f" {low} " for cue in ("rewrite", "simplify", "shorten", "rephrase", "formalize", "formalise", "paraphrase")):
        return "rewrite"
    if _has(ask, COMPARE_CUES):
        return "compare"
    if _has(ask, CHRON_CUES):
        return "chronology"
    if _has(ask, ENTITY_CUES):
        return "entity"
    if _has(ask, REASON_CUES) or low.startswith("why"):
        return "reason"
    return "lookup"


def classify_depth(ask: str, task_type: str) -> str:
    if task_type == "rewrite":
        return "none"
    low = ask.lower()
    review = any(p in low for p in ("review all", "every document", "full review", "contradiction"))
    if review:
        return "review"
    if task_type in {"entity", "chronology", "reason"}:
        return "deep"
    if task_type == "compare" or " and " in low or ";" in ask:
        return "medium"
    if word_count(ask) > 25:
        return "medium"
    return "light"


def keyphrases(ask: str, limit: int = 6) -> list[str]:
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', ask)
    phrases = [a or b for a, b in quoted]
    counts: dict[str, int] = {}
    for tok in content_tokens(ask):
        counts[tok] = counts.get(tok, 0) + 1
    ranked = sorted(counts, key=lambda t: (-counts[t], t))
    out = []
    for phrase in phrases + ranked:
        if phrase not in out:
            out.append(phrase)
        if len(out) >= limit:
            break
    return out


def _clean_part(part: str) -> str:
    part = re.sub(r"^(please|tell me|explain|show)\s+", "", part.strip(), flags=re.I)
    return part.strip(" ?.")


def decompose(ask: str, task_type: str) -> list[str]:
    if task_type == "rewrite":
        return []
    parts = [
        _clean_part(p)
        for p in re.split(
            r"\s+(?:and|versus|vs\.?|compared to|compared with)\s+|;\s+",
            ask,
            flags=re.I,
        )
        if _clean_part(p)
    ]
    subs: list[str] = []
    low = ask.lower()
    if task_type == "compare" and len(parts) >= 2:
        subs.append(f"What is {_clean_part(parts[0])}?")
        subs.append(f"What is {_clean_part(parts[1])}?")
        subs.append("How do these values differ?")
    elif task_type == "entity":
        if "lessee" in low:
            subs.append("Who is the Lessee?")
        if "lessor" in low:
            subs.append("Who is the Lessor?")
        if "address" in low:
            subs.append("What is the address?")
        if "who" in low and not subs:
            subs.append("Who is named?")
        if not subs:
            subs.append(ask if ask.endswith("?") else ask + "?")
    elif task_type == "chronology":
        subs.append(ask if ask.endswith("?") else ask + "?")
        subs.append("Which dates are stated?")
    elif task_type == "reason":
        subs.append(ask if ask.endswith("?") else ask + "?")
        if "unless" in low or "provided that" in low or "if " in low:
            subs.append("Which condition is stated?")
    else:
        if len(parts) > 1:
            for part in parts:
                subs.append(part if part.endswith("?") else f"What is {part}?")
        else:
            subs.append(ask if ask.endswith("?") else ask + "?")
    # Deduplicate, cap at 5 (controller item cap, same bound the architecture puts on proposals).
    deduped = []
    for sub in subs:
        if sub not in deduped:
            deduped.append(sub)
    return deduped[:5]


def query_variants(ask: str, phrases: list[str], subquestions: list[str]) -> list[str]:
    variants = [ask]
    if phrases:
        variants.append(" ".join(phrases[:6]))
    variants.extend(subquestions)
    out = []
    for variant in variants:
        variant = variant.strip()
        if variant and variant not in out:
            out.append(variant)
    return out[:8]


def pseudo_relevance(top_passage: str, limit: int = 4) -> list[str]:
    counts: dict[str, int] = {}
    for tok in content_tokens(top_passage):
        counts[tok] = counts.get(tok, 0) + 1
    return sorted(counts, key=lambda t: (-counts[t], t))[:limit]


def analyze(ask: str) -> dict:
    task = classify_task(ask)
    depth = classify_depth(ask, task)
    phrases = keyphrases(ask)
    subs = decompose(ask, task)
    queries = query_variants(ask, phrases, subs)
    fallback = task != "rewrite" and (len(subs) <= 1) and (" and " in ask.lower() or ";" in ask)
    if fallback and ask not in queries:
        queries = [ask, *queries]
    return {
        "ask": ask,
        "task_type": task,
        "depth": depth,
        "keyphrases": phrases,
        "subquestions": subs,
        "queries": queries,
        "whole_ask_fallback": fallback or True,
        "raw_ask_is_a_query": ask in queries or task == "rewrite",
    }
