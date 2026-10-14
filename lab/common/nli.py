"""Lexical support/contradiction judge. A scaled substitute for a DeBERTa NLI cross-encoder."""

from __future__ import annotations

from lab.common.textutil import content_tokens, coverage, numbers, polarity_flipped


def _softmax(scores: dict[str, float]) -> dict[str, float]:
    import math

    m = max(scores.values())
    exps = {k: math.exp(v - m) for k, v in scores.items()}
    total = sum(exps.values()) or 1.0
    return {k: exps[k] / total for k in scores}


def judge(premise: str, hypothesis: str) -> dict[str, float]:
    """Return entail / neutral / contradict probabilities that sum to 1.

    Number mismatch on overlapping claims and polarity flips are contradictions.
    Exception and qualification wording is not specially parsed, so those probes
    measure the known weakness rather than hiding it.
    """
    h_tokens = content_tokens(hypothesis)
    p_tokens = content_tokens(premise)
    cov = coverage(h_tokens, p_tokens) if h_tokens else 0.0
    p_nums, h_nums = set(numbers(premise)), set(numbers(hypothesis))
    introduced = h_nums - p_nums
    number_conflict = bool(introduced) and bool(p_nums) and cov >= 0.35
    flipped = polarity_flipped(premise, hypothesis) and cov >= 0.45

    entail_s = cov
    contra_s = 0.15
    neutral_s = 1.0 - cov
    if number_conflict or flipped:
        contra_s = 1.4
        entail_s = 0.05
        neutral_s = 0.25
    elif cov >= 0.75:
        entail_s = 1.3
        neutral_s = 0.2
        contra_s = 0.05
    probs = _softmax({"entail": entail_s, "neutral": neutral_s, "contradict": contra_s})
    return {k: round(v, 4) for k, v in probs.items()}


def label_of(probs: dict[str, float]) -> str:
    return max(probs, key=probs.get)


def aggregate(prob_list: list[dict[str, float]]) -> dict[str, float]:
    if not prob_list:
        return {"entail": 0.0, "neutral": 1.0, "contradict": 0.0, "entail_max": 0.0, "contradict_max": 0.0}
    keys = ("entail", "neutral", "contradict")
    mean = {k: sum(p[k] for p in prob_list) / len(prob_list) for k in keys}
    return {
        "entail": round(mean["entail"], 4),
        "neutral": round(mean["neutral"], 4),
        "contradict": round(mean["contradict"], 4),
        "entail_max": round(max(p["entail"] for p in prob_list), 4),
        "contradict_max": round(max(p["contradict"] for p in prob_list), 4),
    }
