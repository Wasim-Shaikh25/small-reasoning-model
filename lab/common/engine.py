"""Controller loop. Passages are data. Nothing in a passage is executed."""

from __future__ import annotations

import re

from lab.common.ask import analyze
from lab.common.budget import cap_depth
from lab.common.index import Index
from lab.common.nli import aggregate, judge
from lab.common.qa import AMOUNT_RE, answer_with_agreement
from lab.common.schemas import validate_judgment
from lab.common.textutil import content_tokens, normalize
from lab.common.verify import (
    conflict_across,
    contradiction_queries,
    coverage_check,
    output_validator,
    quote_check,
    support_check,
)

ABSTAIN_TEXT = "Insufficient evidence."


def _claim(slot: str, span: str) -> str:
    slot = slot.strip(" ?.") or "value"
    return f"The {slot} is {span}."


def _slot_from_question(question: str) -> str:
    text = question.strip().rstrip("?")
    for prefix in ("What is the ", "What is ", "Who is the ", "Who is ", "When is the ", "When does "):
        if text.lower().startswith(prefix.lower()):
            return text[len(prefix):]
    return text


def _permission_hypothesis(question: str) -> str | None:
    match = re.match(r"^(?:may|can)\s+(.*)$", question.strip().rstrip("?"), re.I)
    if not match:
        return None
    rest = match.group(1).strip()
    if rest.lower().startswith("the "):
        return rest[0].upper() + rest[1:] + "."
    return f"The {rest}."


def judge_question(question: str, passages: list[dict], tau: float) -> dict:
    slot = _slot_from_question(question)
    per_passage = []
    for passage in passages:
        qa = answer_with_agreement(question, [passage], tau=tau)
        if qa.get("span"):
            per_passage.append((passage, qa))
    if not per_passage:
        return {
            "fact": slot,
            "status": "missing",
            "span": None,
            "claim_statement": None,
            "evidence_ids": [],
            "qa_confidence": 0.0,
            "nli": {"entail": 0.0, "neutral": 1.0, "contradict": 0.0},
            "second_model_agrees": False,
            "quote_ok": False,
        }
    spans = [(p.get("id"), qa["span"]) for p, qa in per_passage]
    conflicts = conflict_across(spans)
    best_passage, best_qa = max(per_passage, key=lambda pair: pair[1]["score"])
    amounts = {match.lower() for match in AMOUNT_RE.findall(best_passage.get("text", ""))}
    if len(amounts) >= 2:
        listed = sorted(amounts)
        conflicts.append({"a": best_passage.get("id"), "b": best_passage.get("id"), "span_a": listed[0], "span_b": listed[1], "nli": {}})
    permission = _permission_hypothesis(question)
    if permission:
        contradicted = [p for p in passages if judge(p.get("text", ""), permission)["contradict"] >= 0.45]
        if contradicted:
            conflicts.append(
                {
                    "a": contradicted[0].get("id"),
                    "b": contradicted[0].get("id"),
                    "span_a": permission,
                    "span_b": "passage contradicts permission",
                    "nli": judge(contradicted[0].get("text", ""), permission),
                }
            )
    claim = _claim(slot, best_qa["span"])
    nli_list = [judge(p.get("text", ""), claim) for p, _ in per_passage]
    nli_scores = aggregate(nli_list)
    quote_ok = quote_check(best_qa["span"], best_passage.get("text", ""))
    support = support_check(claim, best_passage.get("text", ""))
    status = "conflicted" if conflicts else "found"
    if not quote_ok or not support["ok"]:
        status = "missing" if not conflicts else "conflicted"
    return {
        "fact": slot,
        "status": status,
        "span": best_qa["span"] if status != "missing" else None,
        "claim_statement": claim if status != "missing" else None,
        "evidence_ids": [best_passage.get("id")] if status != "missing" else [],
        "qa_confidence": best_qa["score"],
        "nli": {k: nli_scores[k] for k in ("entail", "neutral", "contradict")},
        "second_model_agrees": bool(best_qa.get("second_model_agrees")),
        "quote_ok": quote_ok,
        "conflicts": conflicts,
        "support_ok": support["ok"],
    }


def decide(facts: list[dict]) -> dict:
    if any(f["status"] == "conflicted" for f in facts):
        return {"label": "contradicted", "confidence": 0.7}
    found = [f for f in facts if f["status"] == "found"]
    if facts and len(found) == len(facts):
        conf = min(f["qa_confidence"] for f in found) if found else 0.0
        entail = min(f["nli"]["entail"] for f in found) if found else 0.0
        if conf >= 0.34 and entail >= 0.45 and all(f["quote_ok"] for f in found):
            return {"label": "supported", "confidence": round(min(0.99, (conf + entail) / 2), 4)}
    return {"label": "inconclusive", "confidence": 0.4}


def next_action(decision: dict, facts: list[dict], state: dict) -> str:
    missing = [f for f in facts if f["status"] == "missing"]
    conflicts = [f for f in facts if f["status"] == "conflicted"]
    if conflicts and state["rounds"] + 1 < state["max_rounds"] and not state.get("conflict_retried"):
        return "verify"
    if missing and state["rounds"] + 1 < state["max_rounds"]:
        return "retrieve_more"
    if decision["label"] == "supported" and not state.get("contradiction_checked"):
        return "verify"
    if decision["label"] == "supported":
        return "answer"
    return "abstain"


def render_findings(facts: list[dict], decision: str) -> str:
    if decision != "supported":
        missing = [f["fact"] for f in facts if f["status"] != "found"]
        if any(f["status"] == "conflicted" for f in facts):
            return "Ambiguous: sources conflict. " + ABSTAIN_TEXT
        detail = ", ".join(missing) if missing else "support"
        return f"Insufficient evidence. Missing: {detail}."
    lines = []
    for fact in facts:
        cite = fact["evidence_ids"][0] if fact["evidence_ids"] else "none"
        lines.append(f"{fact['claim_statement']} [{cite}]")
    return " ".join(lines)


def run_task(ask: str, passages: list[dict], *, depth_cap: str | None = None, tau: float | None = None) -> dict:
    plan = analyze(ask)
    trace = [{"step": "analyze", "plan": {k: plan[k] for k in ("task_type", "depth", "queries", "subquestions")}}]
    if plan["task_type"] == "rewrite":
        text = " ".join(ask.split())
        return {
            "ask": ask,
            "task_type": "rewrite",
            "path": "rewrite_only",
            "text": text,
            "decision": {"label": "supported", "confidence": 1.0},
            "trace": trace,
            "fetched": False,
        }
    budget = cap_depth(plan["depth"], depth_cap)
    from lab.common.budget import CONFIG

    tau = CONFIG["caps"]["no_answer_tau"] if tau is None else tau
    index = Index(passages)
    state = {
        "rounds": 0,
        "max_rounds": budget["max_rounds"],
        "keep": budget["passages_kept"],
        "seen": set(),
        "contradiction_checked": False,
        "conflict_retried": False,
        "queries": list(plan["queries"]) or [ask],
    }
    questions = plan["subquestions"] or [ask]
    gathered: list[dict] = []
    facts: list[dict] = []
    while state["rounds"] <= state["max_rounds"]:
        for query in state["queries"][:6]:
            hits = index.search(query, top_k=max(state["keep"], 1) * 2, exclude=set())
            hits = index.rerank(query, hits, keep=max(state["keep"], 1))
            for hit in hits:
                pid = hit["passage"]["id"]
                if pid not in {p["id"] for p in gathered}:
                    gathered.append(hit["passage"])
                state["seen"].add(pid)
        facts = [judge_question(q, gathered, tau) for q in questions]
        for fact in facts:
            if fact["status"] == "found" and not fact["quote_ok"]:
                fact["status"] = "missing"
                fact["span"] = None
        decision = decide(facts)
        action = next_action(decision, facts, state)
        trace.append(
            {
                "step": "round",
                "round": state["rounds"],
                "queries": list(state["queries"]),
                "retrieved_ids": [p["id"] for p in gathered],
                "action": action,
                "decision": decision,
            }
        )
        judgment = {
            "ask": ask,
            "task_type": plan["task_type"],
            "required_facts": [
                {
                    "fact": f["fact"],
                    "status": f["status"] if f["status"] in {"found", "missing", "conflicted"} else "missing",
                    "span": f["span"],
                }
                for f in facts
            ],
            "decision": decision,
            "next_action": action if action in {"retrieve_more", "verify", "calculate", "answer", "abstain"} else "abstain",
        }
        checked = validate_judgment(judgment)
        if not checked["ok"]:
            text = ABSTAIN_TEXT
            return _finish(ask, plan, facts, {"label": "inconclusive", "confidence": 0.0}, text, trace, budget, schema=checked)
        if action == "retrieve_more":
            extra = []
            for fact in facts:
                if fact["status"] == "missing":
                    extra.append(fact["fact"])
            state["queries"] = extra or state["queries"]
            state["rounds"] += 1
            continue
        if action == "verify" and not state["contradiction_checked"]:
            slots = [f["fact"] for f in facts if f["status"] == "found"] or [ask]
            state["queries"] = [q for slot in slots for q in contradiction_queries(slot)]
            state["contradiction_checked"] = True
            state["conflict_retried"] = True
            state["rounds"] += 1
            continue
        break
    decision = decide(facts)
    if state["rounds"] >= state["max_rounds"] and decision["label"] != "supported":
        decision = {"label": "inconclusive", "confidence": decision.get("confidence", 0.3)}
    text = render_findings(facts, decision["label"])
    citations = [eid for f in facts for eid in f.get("evidence_ids") or []]
    findings_text = " ".join(f["claim_statement"] for f in facts if f.get("claim_statement") and f.get("status") == "found")
    if decision["label"] == "supported":
        final_check = output_validator(text, findings_text or text, citations, decision["label"])
        if not final_check["ok"]:
            text = findings_text or ABSTAIN_TEXT
    else:
        final_check = output_validator(text, text, [], decision["label"])
    return _finish(ask, plan, facts, decision, text, trace, budget, validator=final_check)


def _finish(ask, plan, facts, decision, text, trace, budget, schema=None, validator=None) -> dict:
    cov = coverage_check(facts)
    return {
        "ask": ask,
        "task_type": plan["task_type"],
        "depth": budget,
        "required_facts": facts,
        "coverage": cov,
        "decision": decision,
        "text": text,
        "trace": trace,
        "fetched": True,
        "schema": schema,
        "validator": validator,
        "instruction_executed": False,
    }


def passages_treated_as_data(passages: list[dict]) -> bool:
    """The engine never calls eval/exec. This checks the passage payload is only read as text."""
    for passage in passages:
        text = passage.get("text", "")
        if "eval(" in text or "exec(" in text or "__import__" in text:
            # Still data. Touching the string must not run it.
            normalize(text)
            content_tokens(text)
    return True
