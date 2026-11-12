"""Shared test-support utilities: scoring/metrics, and the handful of
secondary code paths (an abandoned-in-production navigator, a never-wired
rule-application mode, a never-wired output gate) that experiments still
exercise directly even though lab.common.brain's own pipeline doesn't call
them.

Java-style src/main-vs-test split (AGENT.md): lab/common/ is production,
reachable from lab.common.brain.reason/lab.common.engine.run. Nothing here
may be imported BY lab/common -- this module only ever imports FROM it.
Moved here 2026-11-12 when a deterministic audit found each function below
had zero callers anywhere in lab/common itself, only in lab/tests/exp_*/
run.py scripts grading or exercising brain's output.
"""

from __future__ import annotations

from lab.common.doc_tools import list_templates, list_tools
from lab.common.index import Index
from lab.common.nested_index import MIN_DENSE_SCORE, NestedNode
from lab.common.nli import judge
from lab.common.qa import spans_overlap
from lab.common.calc import parse_date, sum_amounts
from lab.common.real_encoders import bge_embed, real_nli
from lab.common.relevance import ask_relevance
from lab.common.rules import apply_rule, extract_fact_triple, parse_conditional_rule
from lab.common.semantic_index import MIN_SEMANTIC_MARGIN, SemanticIndex
from lab.common.textutil import modals, normalize, numbers, span_in_passage
from lab.common.verify import entity_number_check, modality_preserved, qualifier_added

# ---------------------------------------------------------------------------
# lab.common.harness: pure scoring functions (Run/peak_rss_mb stay in
# lab.common.harness -- every experiment needs those to report results at
# all, so they are the one piece of that module that IS production-shared
# test infrastructure, not test-only in the sense the rest of this file is).
# ---------------------------------------------------------------------------


def prf(pred: set, gold: set) -> dict[str, float]:
    tp = len(pred & gold)
    p = tp / max(1, len(pred))
    r = tp / max(1, len(gold))
    f = 2 * p * r / max(1e-9, p + r)
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4), "tp": tp}


def score_qa(item: dict, qa_out: dict) -> dict[str, bool]:
    answerable = item["answerable"]
    abstained = qa_out["no_answer"] >= item["tau_no_answer"] or qa_out["span"] is None
    passages = item["passages"]
    passage = passages.get(qa_out.get("passage_id"), "")
    exact = (
        answerable
        and not abstained
        and normalize(qa_out["span"]) == normalize(item["gold"])
    )
    return {
        "correct_abstain": (not answerable) and abstained,
        "false_answer": (not answerable) and not abstained,
        "missed_answer": answerable and abstained,
        "exact_match": exact,
        "span_valid": (not abstained) and span_in_passage(qa_out["span"], passage),
    }


def fidelity(src: str, out: str) -> dict:
    sn, on = set(numbers(src)), set(numbers(out))
    sm = sorted(modals(src))
    om = sorted(modals(out))
    return {
        "numbers_dropped": sorted(sn - on),
        "numbers_added": sorted(on - sn),
        "modal_changed": sm != om,
    }


# ---------------------------------------------------------------------------
# lab.common.index: retrieval-eval metrics.
# ---------------------------------------------------------------------------


def recall_at_k(retrieved_ids: list[str], gold_ids: set[str], k: int) -> float:
    if not gold_ids:
        return 0.0
    hit = set(retrieved_ids[:k]) & gold_ids
    return len(hit) / len(gold_ids)


def mrr(retrieved_ids: list[str], gold_ids: set[str]) -> float:
    for i, pid in enumerate(retrieved_ids, start=1):
        if pid in gold_ids:
            return 1.0 / i
    return 0.0


# ---------------------------------------------------------------------------
# lab.common.nli: aggregation helpers never used by the production judge
# path (lab.common.brain imports only `judge`).
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# lab.common.nested_index / lab.common.semantic_index: the lexical-only and
# semantic-only navigators. lab.common.brain's hierarchical_navigate stage
# uses navigate_dual (both signals combined) -- these single-signal versions
# were each superseded by navigate_dual but stay reachable here for the
# experiments that measure them against it (EXP-065/067/068/070/071/075).
# ---------------------------------------------------------------------------


def navigate(ask: str, root: NestedNode, top_k: int = 1, min_dense_score: float = MIN_DENSE_SCORE) -> dict:
    """lab.common.nested_index's original lexical-only descent. See
    lab.common.semantic_index.navigate_dual for the production path."""
    trace = []
    node = root
    while not node.is_leaf:
        candidates = [{"id": child.node_id, "text": child.summary_text} for child in node.children]
        child_level = node.children[0].level
        index = Index(candidates)
        hits = index.search(ask, top_k=top_k)
        if not hits:
            return {"path": trace, "leaf": None, "leaf_passages": [], "abstain_reason": f"no {child_level} candidates to score"}
        if hits[0]["dense"] < min_dense_score:
            return {
                "path": trace,
                "leaf": None,
                "leaf_passages": [],
                "abstain_reason": f"no {child_level} scored above the dense-similarity floor (best: {hits[0]['dense']:.4f} < {min_dense_score})",
            }
        best_id = hits[0]["passage"]["id"]
        chosen = next(child for child in node.children if child.node_id == best_id)
        trace.append(
            {
                "level": chosen.level,
                "chosen": chosen.title,
                "chosen_id": chosen.node_id,
                "score": round(hits[0]["score"], 4),
                "candidates_considered": len(candidates),
            }
        )
        node = chosen
    return {"path": trace, "leaf": node, "leaf_passages": node.leaf_passages}


def navigate_semantic(ask: str, root: NestedNode, min_margin: float = MIN_SEMANTIC_MARGIN) -> dict:
    """lab.common.semantic_index's semantic-only descent. See
    lab.common.semantic_index.navigate_dual for the production path."""
    trace = []
    node = root
    while not node.is_leaf:
        candidates = [{"id": child.node_id, "text": child.summary_text} for child in node.children]
        child_level = node.children[0].level

        if len(candidates) == 1:
            dense = Index(candidates).search(ask, top_k=1)[0]["dense"]
            if dense < MIN_DENSE_SCORE:
                return {
                    "path": trace,
                    "leaf": None,
                    "leaf_passages": [],
                    "abstain_reason": (
                        f"only one {child_level} candidate and it scored at the dense-similarity floor "
                        f"(dense {dense:.4f} < {MIN_DENSE_SCORE}) -- no margin was computable to check instead"
                    ),
                }
            chosen = node.children[0]
            trace.append({"level": chosen.level, "chosen": chosen.title, "chosen_id": chosen.node_id, "score": None, "margin": None, "candidates_considered": 1, "fallback": "single_candidate_dense_floor"})
            node = chosen
            continue

        index = SemanticIndex(candidates)
        hits = index.search(ask, top_k=2)
        if not hits:
            return {"path": trace, "leaf": None, "leaf_passages": [], "abstain_reason": f"no {child_level} candidates to score"}
        margin = hits[0]["score"] - hits[1]["score"]
        if margin < min_margin:
            return {
                "path": trace,
                "leaf": None,
                "leaf_passages": [],
                "abstain_reason": (
                    f"no {child_level} clearly separated from the runner-up "
                    f"(margin {margin:.4f} < {min_margin}, top score {hits[0]['score']:.4f})"
                ),
            }
        best_id = hits[0]["passage"]["id"]
        chosen = next(child for child in node.children if child.node_id == best_id)
        trace.append(
            {
                "level": chosen.level,
                "chosen": chosen.title,
                "chosen_id": chosen.node_id,
                "score": round(hits[0]["score"], 4),
                "margin": round(margin, 4),
                "candidates_considered": len(candidates),
            }
        )
        node = chosen
    return {"path": trace, "leaf": node, "leaf_passages": node.leaf_passages}


# ---------------------------------------------------------------------------
# lab.common.rules: a second, never-wired rule-application mode
# (semantic/paraphrase matching, and a whole-pipeline demo entry point).
# lab.common.brain's rule_application stage uses apply_rule (exact lemma
# match) only.
# ---------------------------------------------------------------------------


def sum_amounts_for_subject(passages: list[dict], amount_re) -> dict:
    spans = []
    sources = []
    for passage in passages:
        for found in amount_re.findall(passage.get("text", "")):
            spans.append(found)
            sources.append(passage.get("id"))
    result = sum_amounts(spans)
    result["sources"] = sources
    return result


def semantic_apply_rule(rule: dict, fact_text: str, tau: float = 0.75) -> dict:
    probs = real_nli(fact_text, rule["condition_text"])
    matched = probs["entail"] >= tau and probs["contradict"] < 0.2
    return {
        "matched": matched,
        "condition_text": rule["condition_text"],
        "fact_text": fact_text,
        "nli": probs,
        "consequence": rule["consequence"] if matched else None,
    }


def answer_rule_question(ask: str, passages: list[dict]) -> dict:
    rule = rule_passage = None
    fact = fact_passage = None
    for passage in passages:
        text = passage.get("text", "")
        if rule is None:
            candidate = parse_conditional_rule(text)
            if candidate:
                rule, rule_passage = candidate, passage
                continue
        if fact is None:
            candidate = extract_fact_triple(text)
            if candidate and candidate["subject"] and candidate["subject"].lower() not in {
                "it", "someone", "anyone", "somebody", "something",
            }:
                fact, fact_passage = candidate, passage
    if rule is None or fact is None:
        return {
            "decision": "inconclusive",
            "reason": "missing_rule" if rule is None else "missing_fact",
            "rule": rule,
            "fact": fact,
            "text": "Insufficient evidence.",
        }
    result = apply_rule(rule, fact)
    if not result["matched"]:
        return {
            "decision": "inconclusive",
            "reason": "no_verb_match",
            "rule": rule,
            "fact": fact,
            "applied": result,
            "text": "Insufficient evidence.",
        }
    rule_cite = rule_passage.get("id", "rule")
    fact_cite = fact_passage.get("id", "fact")
    text = (
        f"{fact['raw']} [{fact_cite}] This matches the rule's trigger ({result['trigger_lemma']}): "
        f"{rule['raw']} [{rule_cite}] Therefore, {rule['consequence']}."
    )
    return {
        "decision": "supported",
        "reason": "verb_match",
        "rule": rule,
        "fact": fact,
        "applied": result,
        "text": text,
        "citations": [rule_cite, fact_cite],
    }


# ---------------------------------------------------------------------------
# lab.common.verify: checks never wired into lab.common.brain's own
# verification path (which reimplements conflict_across inline, brain.py
# ~line 478, and otherwise uses quote_check/citation_markers directly).
# ---------------------------------------------------------------------------


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


def output_validator(text: str, findings_text: str, citations: list[str], decision: str, ask: str | None = None) -> dict:
    missing_citations = [c for c in citations if f"[{c}]" not in text]
    qualifiers = qualifier_added(findings_text, text)
    numbers_ok = entity_number_check(findings_text, text)["ok"]
    modals_ok = modality_preserved(findings_text, text)
    caveat_ok = True
    if decision in {"inconclusive", "ambiguous"}:
        caveat_ok = any(word in text.lower() for word in ("insufficient", "ambiguous", "unresolved", "missing"))
    relevance = ask_relevance(ask, text) if ask else None
    ask_ok = relevance is None or relevance["relevant"]
    ok = not missing_citations and not qualifiers and numbers_ok and modals_ok and caveat_ok and ask_ok
    return {
        "ok": ok,
        "missing_citations": missing_citations,
        "qualifiers_added": qualifiers,
        "numbers_ok": numbers_ok,
        "modals_ok": modals_ok,
        "caveat_ok": caveat_ok,
        "ask_relevance": relevance,
    }


# ---------------------------------------------------------------------------
# lab.common.doc_tools: tool/template selection by description similarity.
# Only check_section_contract/check_template_contracts (wired into
# lab.common.longform) and list_tools/list_templates/load_template are
# production-used; select_tool/select_template never are.
# ---------------------------------------------------------------------------


def _best_match(ask: str, candidates: list[dict], text_key: str) -> dict:
    if not candidates:
        return {"match": None, "score": 0.0, "ranked": []}
    descriptions = [c[text_key] for c in candidates]
    vecs = bge_embed([ask, *descriptions])
    ask_vec, cand_vecs = vecs[0], vecs[1:]
    scores = cand_vecs @ ask_vec
    ranked = sorted(zip(candidates, scores.tolist()), key=lambda pair: pair[1], reverse=True)
    best_candidate, best_score = ranked[0]
    return {
        "match": best_candidate,
        "score": round(float(best_score), 4),
        "ranked": [{"id": c.get("id", c.get("tool")), "score": round(float(s), 4)} for c, s in ranked],
    }


def select_tool(ask: str) -> dict:
    result = _best_match(ask, list_tools(), "description")
    return {"tool": result["match"]["tool"] if result["match"] else None, "score": result["score"], "ranked": result["ranked"]}


def select_template(ask: str, tool: str | None = None) -> dict:
    result = _best_match(ask, list_templates(tool), "description")
    match = result["match"]
    return {
        "template_id": match["id"] if match else None,
        "tool": match["tool"] if match else None,
        "score": result["score"],
        "ranked": result["ranked"],
    }


# ---------------------------------------------------------------------------
# lab.common.calc: a date-math helper no production stage calls.
# ---------------------------------------------------------------------------


def add_period(start_text: str, period_text: str) -> dict:
    import re
    from datetime import timedelta

    start = parse_date(start_text)
    if start is None:
        return {"ok": False, "error": "unparsed_date", "inputs": [start_text, period_text]}
    days = re.search(r"(\d+)\s*day", period_text or "", re.I)
    months = re.search(r"(\d+)\s*month", period_text or "", re.I)
    if days:
        end = start + timedelta(days=int(days.group(1)))
        rule = "end = start + N days"
    elif months:
        month = start.month - 1 + int(months.group(1))
        year = start.year + month // 12
        month = month % 12 + 1
        end = start.replace(year=year, month=month)
        rule = "end = start + N calendar months"
    else:
        return {"ok": False, "error": "unparsed_period", "inputs": [start_text, period_text]}
    return {
        "ok": True,
        "result": end.strftime("%d %B %Y"),
        "inputs": {"start": start_text, "period": period_text},
        "rule": rule,
        "provenance": "inference",
    }


# ---------------------------------------------------------------------------
# lab.common.real_encoders: real-model substitutes used only by the real_*
# rerun experiments that measure the bounded-rewriter fidelity gate and
# longform repetition against the real BGE/DeBERTa checkpoints.
# ---------------------------------------------------------------------------


def bge_cosine_matrix(texts: list[str]):
    import numpy as np

    if not texts:
        return np.zeros((0, 0), dtype="float32")
    vecs = bge_embed(texts)
    return vecs @ vecs.T


def real_bidirectional_nli(source: str, output: str, tau: float = 0.55) -> dict:
    forward = real_nli(source, output)
    backward = real_nli(output, source)
    return {
        "forward": forward,
        "backward": backward,
        "ok": forward["entail"] >= tau and backward["entail"] >= tau,
    }
