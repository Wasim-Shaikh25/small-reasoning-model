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

Identity/total detection used to be two literal keyword checks (a fixed
TOTAL_CUES word list; "name" + "address" as literal substrings) plus a
dependency on lab.common.ask's task_type classifier, which itself used to
hardcode "lessee"/"lessor" -- real lease-contract vocabulary -- into what was
supposed to be a domain-agnostic signal. Found when a paraphrased ask passed
disambiguation correctly but got no answer anyway (EXP-068), and replaced
(EXP-069) with lab.common.intent_signals: semantic exemplar matching (bge),
calibrated and tested against medical, insurance, and engineering asks, not
just the lease/contract wording every other fixture in this repo happens to
use.

Every tool this calls is a primitive already built and separately measured:
  - lab.common.index.Index: hybrid retrieval, EXP-004/015/029/040/058.
  - lab.common.intent_signals: domain-agnostic identity/total detection,
    EXP-069 (bge exemplar similarity, not literal keywords).
  - lab.common.semantic_index.SemanticIndex: real bge embeddings, EXP-067,
    used alongside Index (not instead of it) for flat disambiguation --
    lexical and semantic are independent signals that must agree.
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
from lab.common.intent_signals import wants_identity, wants_total
from lab.common.nested_index import MIN_DENSE_SCORE, build_nested_index, navigate
from lab.common.qa import answer_with_agreement
from lab.common.rules import apply_rule, apply_threshold_rule, extract_fact_triple, parse_conditional_rule, parse_threshold_rule
from lab.common.semantic_index import MIN_SEMANTIC_MARGIN, SemanticIndex
from lab.common.textutil import normalize
from lab.common.verify import quote_check

ABSTAIN_TEXT = "Insufficient evidence."


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
        #
        # Two independent signals, neither trusted alone (EXP-067): lexical
        # (TF-IDF) catches exact wording and abstains via MIN_DENSE_SCORE --
        # a strictly-positive floor, since disjoint vocabulary dot-products to
        # exactly 0.0 regardless of document count. Semantic (bge) catches
        # paraphrase/synonym asks TF-IDF can't, and abstains via
        # MIN_SEMANTIC_MARGIN -- a top1-vs-runner-up gap, since embeddings
        # never score unrelated text near zero the way TF-IDF does, so a
        # floor can't work for them. If only one signal is confident, its
        # pick is used (the other simply had nothing to go on). If both are
        # confident but name different groups, that's a real conflict, not a
        # case either signal is equipped to resolve alone -- abstain rather
        # than pick a winner arbitrarily.
        story_passages = [p for p in passages if p.get("group")]
        lexical_hits = Index(story_passages).search(ask, top_k=2)
        semantic_hits = SemanticIndex(story_passages).search(ask, top_k=2)
        if not lexical_hits or not semantic_hits:
            return _finish(ask, trace, "inconclusive", ABSTAIN_TEXT, citations, reason="no passage matched the ask")

        lexical_abstain = lexical_hits[0]["dense"] < MIN_DENSE_SCORE
        semantic_margin = semantic_hits[0]["score"] - semantic_hits[1]["score"] if len(semantic_hits) > 1 else semantic_hits[0]["score"]
        semantic_abstain = semantic_margin < MIN_SEMANTIC_MARGIN
        lexical_group = lexical_hits[0]["passage"].get("group")
        semantic_group = semantic_hits[0]["passage"].get("group")

        trace.append(
            {
                "step": "disambiguate",
                "lexical_group": lexical_group,
                "lexical_dense": round(lexical_hits[0]["dense"], 4),
                "lexical_abstain": lexical_abstain,
                "semantic_group": semantic_group,
                "semantic_margin": round(semantic_margin, 4),
                "semantic_abstain": semantic_abstain,
            }
        )

        if lexical_abstain and semantic_abstain:
            return _finish(ask, trace, "inconclusive", ABSTAIN_TEXT, citations, reason="neither lexical nor semantic retrieval found a confident match")
        if not lexical_abstain and not semantic_abstain and lexical_group != semantic_group:
            return _finish(ask, trace, "inconclusive", ABSTAIN_TEXT, citations, reason=f"lexical and semantic retrieval disagree on which story matches ({lexical_group!r} vs {semantic_group!r})")

        matched = semantic_hits[0]["passage"] if lexical_abstain else lexical_hits[0]["passage"]
        resolved_group = matched.get("group")
        citations.add(matched["id"])
        scoped = [p for p in passages if p.get("group") == resolved_group]

    facts: dict = {}
    answer_parts: list[str] = []

    identity_signal = wants_identity(ask)
    trace.append({"step": "intent_signal", "signal": "identity", **identity_signal})
    if identity_signal["fires"]:
        full_text = " ".join(p["text"] for p in scoped)
        mentions = detect_primary(full_text)
        # Prefer a person mention that is unique to this resolved scope over
        # one that also appears outside it (e.g. a doctor's name repeated
        # across every patient's own passages) -- a set-difference check
        # over which passages mention whom, not a role word list, so it
        # stays domain-agnostic. Falls back to the first mention (the
        # original behavior) when no mention is scope-unique, so documents
        # with only one person per group are unaffected.
        other_text = " ".join(p["text"] for p in passages if p not in scoped)
        person = next((m for m in mentions if m["label"] == "person" and m["text"] not in other_text), None)
        person = person or next((m for m in mentions if m["label"] == "person"), None)
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

    total_signal = wants_total(ask)
    trace.append({"step": "intent_signal", "signal": "total", **total_signal})
    if total_signal["fires"]:
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
