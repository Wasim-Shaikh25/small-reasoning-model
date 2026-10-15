"""The reasoning brain: one controller, not a dispatcher to separate task-type engines.

Everything built across EXP-057/058/059 proved the individual pieces work and
generalize: rule application, entity/address extraction, arithmetic, hybrid
retrieval. But each was exercised by its own exploration script calling its
own sequence of functions by hand -- there was no single entry point an
arbitrary ask and context could go through. This module is that entry point.

The key design choice, directly answering the objection that this would
otherwise just be a classifier picking between separate pipelines: `reason()`
does not classify the ask into one exclusive type and branch. It runs a fixed
sequence of independent, domain-agnostic *signal checks* -- is there more than
one candidate story here (flat, or nested across a hierarchy)? does the ask
want an identity? a total? is there a rule anywhere in context? -- and only
the tools whose signal fires actually run. A plain lookup question fires none
of the extra signals and falls back to the same lab.common.qa extractor
lab.common.engine already uses. A question like EXP-058's fires three of them
at once and chains their results. Same function, same code path, every time;
the input decides how much of it is used, not a label chosen for the input
ahead of time.

Every tool this calls is a primitive already built and separately measured:
  - lab.common.index.Index: hybrid retrieval, EXP-004/015/029/040/058.
  - lab.common.nested_index: hierarchical navigation over a structured
    document, EXP-065, used when passages carry a "hierarchy" tag instead
    of (or in addition to) a flat "group" tag.
  - lab.common.entities: name/address extraction, EXP-009.
  - lab.common.calc: arithmetic, EXP-007/014.
  - lab.common.rules: verb-trigger and threshold rule application,
    EXP-057/058/059 (including the role-match guard EXP-058 added).
  - lab.common.qa: the fallback single-slot extractor, EXP-005.
  - lab.common.verify / lab.common.nli: the same fidelity/entailment checks
    used everywhere else in this repo.

Nothing here is a generative model. The ask analyzer and every extraction
step are the same deterministic/classical code already measured elsewhere;
this module's only new contribution is the control flow that chains them.
"""

from __future__ import annotations

from lab.common.ask import analyze
from lab.common.calc import sum_amounts
from lab.common.entities import AMOUNT_RE, detect_primary, parse_address
from lab.common.index import Index
from lab.common.nested_index import build_nested_index, navigate
from lab.common.qa import answer_with_agreement
from lab.common.rules import apply_rule, apply_threshold_rule, extract_fact_triple, parse_conditional_rule, parse_threshold_rule
from lab.common.textutil import normalize
from lab.common.verify import quote_check

ABSTAIN_TEXT = "Insufficient evidence."

TOTAL_CUES = ("total", "how much", "sum", "altogether", "combined", "in all")


def _wants_total(ask: str) -> bool:
    low = ask.lower()
    return any(cue in low for cue in TOTAL_CUES)


def _wants_identity(ask: str, task_type: str) -> bool:
    if task_type == "entity":
        return True
    low = ask.lower()
    return "name" in low and "address" in low


def _find_rule(passages: list[dict]):
    """Scan every passage for either rule shape. Rules can be global policy
    text, not necessarily inside the resolved story's own group, so this
    always searches the full passage set, not the disambiguated scope.
    """
    for passage in passages:
        rule = parse_conditional_rule(passage.get("text", ""))
        if rule:
            return "verb", rule, passage
        rule = parse_threshold_rule(passage.get("text", ""))
        if rule:
            return "threshold", rule, passage
    return None


def _role_matches(rule: dict, passages: list[dict]) -> bool:
    import re

    role_noun = re.sub(r"^(a|an|the)\s+", "", rule["subject_placeholder"].strip().lower())
    full_text = " ".join(p.get("text", "") for p in passages).lower()
    return role_noun in full_text


def reason(ask: str, passages: list[dict]) -> dict:
    trace = []
    plan = analyze(ask)
    trace.append({"step": "analyze_ask", "task_type": plan["task_type"], "subquestions": plan["subquestions"]})

    groups = sorted({p.get("group") for p in passages if p.get("group")})
    citations: set[str] = set()
    scoped = passages

    hierarchical = [p for p in passages if p.get("hierarchy")]
    if hierarchical:
        # A structured document (chapter/section/... tags) navigates level by
        # level (lab.common.nested_index, EXP-065) instead of the flat
        # single-level search below. A passage with no "hierarchy" tag (a
        # global policy, say) is excluded from the tree the same way an
        # ungrouped passage is excluded from the flat story search -- it is
        # not itself a candidate "section", it is background text _find_rule
        # still scans separately over the full passage list.
        level_keys = list(hierarchical[0]["hierarchy"].keys())
        items = [{**p, **p["hierarchy"]} for p in hierarchical]
        root = build_nested_index(items, level_keys)
        nav = navigate(ask, root)
        trace.append({"step": "nested_navigate", "path": nav["path"], "abstain_reason": nav.get("abstain_reason")})
        if nav["leaf"] is None:
            return _finish(ask, trace, "inconclusive", ABSTAIN_TEXT, citations, reason=nav.get("abstain_reason", "navigation failed"))
        scoped = nav["leaf_passages"]
    elif len(groups) > 1:
        # Only passages tagged with a story group are candidates for "which
        # story is this ask about" -- an ungrouped passage is background
        # rule/policy text, a different category entirely, and must not
        # compete to be the resolved "story" just because it shares a word
        # with the ask (a policy mentioning "contractor" is not itself a
        # contractor's story).
        story_passages = [p for p in passages if p.get("group")]
        index = Index(story_passages)
        hits = index.search(ask, top_k=1)
        if not hits:
            return _finish(ask, trace, "inconclusive", ABSTAIN_TEXT, citations, reason="no passage matched the ask")
        matched = hits[0]["passage"]
        resolved_group = matched.get("group")
        citations.add(matched["id"])
        scoped = [p for p in passages if p.get("group") == resolved_group]
        trace.append({"step": "disambiguate", "resolved_group": resolved_group, "matched_passage": matched["id"], "score": round(hits[0]["score"], 4)})

    facts: dict = {}
    answer_parts: list[str] = []

    if _wants_identity(ask, plan["task_type"]):
        full_text = " ".join(p["text"] for p in scoped)
        mentions = detect_primary(full_text)
        person = next((m for m in mentions if m["label"] == "person"), None)
        address = parse_address(full_text)
        name_cite = next((p["id"] for p in scoped if person and person["text"] in p["text"]), None)
        facts["name"] = person["text"] if person else None
        facts["address"] = address
        if name_cite:
            citations.add(name_cite)
        trace.append({"step": "extract_identity", "name": facts["name"], "address_road": address.get("road")})
        if facts["name"]:
            road = address.get("road")
            answer_parts.append(f"{facts['name']}" + (f", {road}" if road else "") + (f" [{name_cite}]" if name_cite else ""))

    if _wants_total(ask):
        spans, sources = [], []
        for p in scoped:
            for found in AMOUNT_RE.findall(p["text"]):
                spans.append(found)
                sources.append(p["id"])
        money = sum_amounts(spans)
        facts["total"] = money["total"]
        citations.update(sources)
        trace.append({"step": "compute_total", "total": money["total"], "sources": sources})
        if money["ok"]:
            answer_parts.append(f"total {money['total']:,.0f} [{', '.join(sources)}]")

    rule_hit = _find_rule(passages)
    if rule_hit:
        kind, rule, rule_passage = rule_hit
        trace.append({"step": "find_rule", "kind": kind, "rule": rule["raw"]})
        if kind == "threshold":
            if "total" not in facts:
                trace.append({"step": "apply_rule", "skipped": "no computed total to compare"})
            elif not _role_matches(rule, scoped):
                trace.append({"step": "apply_rule", "skipped": f"role mismatch with {rule['subject_placeholder']!r}"})
                answer_parts.append(f"policy does not apply (role mismatch with {rule['subject_placeholder']!r}) [{rule_passage['id']}]")
            else:
                applied = apply_threshold_rule(rule, facts["total"])
                trace.append({"step": "apply_rule", "kind": "threshold", "result": applied})
                citations.add(rule_passage["id"])
                answer_parts.append(
                    f"policy applies: {applied['consequence']} [{rule_passage['id']}]"
                    if applied["matched"]
                    else f"policy does not apply (threshold not exceeded) [{rule_passage['id']}]"
                )
        else:
            fact_passage = next((p for p in scoped if extract_fact_triple(p["text"])), None)
            if fact_passage:
                fact = extract_fact_triple(fact_passage["text"])
                applied = apply_rule(rule, fact)
                trace.append({"step": "apply_rule", "kind": "verb", "result": applied, "fact_passage": fact_passage["id"]})
                if applied["matched"]:
                    citations.update([rule_passage["id"], fact_passage["id"]])
                    answer_parts.append(f"{fact_passage['text']} [{fact_passage['id']}] matches the rule's trigger ({applied['trigger_lemma']}): {rule['raw']} [{rule_passage['id']}] Therefore, {applied['consequence']}.")

    if not answer_parts:
        # No identity/total/rule signal fired -- this is a plain lookup ask.
        # Fall back to the same single-slot extractor lab.common.engine uses.
        qa = answer_with_agreement(ask, scoped, tau=0.34)
        trace.append({"step": "lookup_fallback", "span": qa["span"], "passage_id": qa.get("passage_id")})
        if not qa["span"] or not quote_check(qa["span"], next((p["text"] for p in scoped if p["id"] == qa.get("passage_id")), "")):
            return _finish(ask, trace, "inconclusive", ABSTAIN_TEXT, citations, reason="no span found")
        citations.add(qa["passage_id"])
        return _finish(ask, trace, "supported", f"{qa['span']} [{qa['passage_id']}]", citations, facts=facts)

    return _finish(ask, trace, "supported", ". ".join(answer_parts) + ".", citations, facts=facts)


def _finish(ask, trace, decision, text, citations, facts=None, reason=None) -> dict:
    result = {
        "ask": ask,
        "decision": decision,
        "text": text,
        "citations": sorted(citations),
        "facts": facts or {},
        "trace": trace,
    }
    if reason:
        result["abstain_reason"] = reason
    return result
