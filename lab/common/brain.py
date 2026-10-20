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
want an identity? a total? a full written document? is there a rule anywhere
in context? -- and only the tools whose signal fires actually run. A plain
lookup question fires none of the extra signals and falls back to the same
lab.common.qa extractor lab.common.engine already uses. A question like
EXP-058's fires three of them at once and chains their results. A document
request (EXP-078, closing what this docstring itself used to name as a
fifth-signal todo) fires its own signal first and exclusively, dispatching
to lab.common.longform instead of falling through to the short-answer
signals below it. Same function, same code path, every time; the input
decides how much of it is used, not a label chosen for the input ahead of
time.

One case sits outside that signal-chain entirely and is checked first: zero
passages at all (FORBIDDEN.md's narrow exception, 2026-10-16). That is not
"no signal fired" -- it is "there was nothing to check a signal against" --
so it never reaches the evidence-grounded path below, and it never returns
`decision == "supported"`, only the new `"ungrounded"` value, with a fixed
visible disclaimer. lab.common.open_domain, not this module, does the
actual answering; this function only enforces exactly when that path is
reachable.

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
  - lab.common.intent_signals: domain-agnostic identity/total/document
    detection, EXP-069/078 (bge exemplar similarity, not literal keywords).
  - lab.common.semantic_index.SemanticIndex / navigate_dual: real bge
    embeddings, EXP-067/070, used alongside Index (not instead of it) for
    both flat disambiguation and hierarchical navigation -- lexical and
    semantic are independent signals that must agree in both branches.
  - lab.common.nested_index.build_nested_index: builds the tree a
    structured document (a "hierarchy" tag) navigates level by level,
    EXP-065; navigate_dual (above) does the actual level-by-level descent.
  - lab.common.graph_index: entity co-occurrence graph, EXP-075, for
    combining facts about one named entity across groups/chapters the
    single-path flat/hierarchical resolution above can't reach by design.
  - lab.common.entities: name/address extraction, EXP-009.
  - lab.common.longform / lab.common.working_memory: ask-derived
    long-form document writing and cross-page consistency checking,
    EXP-052/053/078 -- the controller's own bounded "RAM", never the
    full data, only pointers and short digests back to it.
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
from lab.common.graph_index import build_entity_graph, expand_from_entity
from lab.common.index import Index
from lab.common.inference import check_exceptions, forward_chain, instantiate_consequence, split_exceptions
from lab.common.intent_signals import wants_document, wants_identity, wants_rule_application, wants_total
from lab.common.nested_index import MIN_DENSE_SCORE, build_nested_index
from lab.common.qa import answer_with_agreement
from lab.common.rules import apply_rule, apply_threshold_rule, extract_fact_triple, parse_conditional_rule, parse_threshold_rule
from lab.common.semantic_index import MIN_LEXICAL_MARGIN, MIN_SEMANTIC_MARGIN, SemanticIndex, navigate_dual
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


def _find_verb_rules(passages: list[dict]) -> list[dict]:
    """Every verb-trigger rule (not just the first, unlike _find_rule) --
    EXP-084's forward_chain dispatch needs the full rule set to chain a
    derived fact into a SECOND rule, which a single-rule scan can never
    see.
    """
    rules = []
    for passage in passages:
        rule = parse_conditional_rule(passage.get("text", ""))
        if rule:
            rules.append(rule)
    return rules


STAGE_REGISTRY = (
    "no_context_fallback",
    "document_write",
    "hierarchical_navigate",
    "disambiguate",
    "graph_expand",
    "identity_extraction",
    "total_computation",
    "rule_application",
    "lookup_fallback",
)


def plan_stages(ask: str, passages: list[dict], use_real_ner: bool = False) -> dict:
    """The explicit, inspectable list of pipeline stages this reason()
    call will run, computed from a fixed, named registry (STAGE_REGISTRY
    above) BEFORE any stage actually executes -- the project owner's own
    proposal, verbatim: "give one simple prompt and system have to
    perform multistep work so it should first create full plan and than
    execute that... it will keep it in control." Every stage name is
    chosen from that fixed registry, never freely generated text, so this
    introduces no new hallucination risk beyond what wants_document
    already carried as a signal.

    This computes the SAME signals reason() itself checks (document/
    identity/total, plus the new wants_rule_application), in the same
    order, so the plan accurately predicts what reason() is actually
    about to do -- not a second, independent guess that could disagree
    with the real execution.

    rule_application has two distinct methods, not one: "single_step"
    (today's existing apply_rule-based derivation, unchanged, used
    whenever a rule is structurally present regardless of the ask's own
    wording -- exactly as reason() already behaved before this
    exploration) and "forward_chain" (EXP-084's actual new capability:
    additionally chains a derived fact into a SECOND rule found among the
    other given passages, reachable through reason() itself for the first
    time, not just through a standalone forward_chain() call in an
    exploration script) -- only when wants_rule_application's own signal
    fires, so an ask that never asked about compliance at all keeps
    exactly today's single-step behavior, zero regression.
    """
    if not passages:
        return {"stages": ["no_context_fallback"], "signals": {}, "rule_application_method": None}

    document_signal = wants_document(ask)
    if document_signal["fires"]:
        return {"stages": ["document_write"], "signals": {"document": document_signal}, "rule_application_method": None}

    stages = []
    groups = {p.get("group") for p in passages if p.get("group")}
    hierarchical = any(p.get("hierarchy") for p in passages)
    if hierarchical:
        stages.append("hierarchical_navigate")
    elif len(groups) > 1:
        stages.append("disambiguate")

    ask_entities = [m["text"] for m in detect_primary(ask, use_real_ner=use_real_ner) if m["label"] in ("person", "organization")]
    if ask_entities:
        stages.append("graph_expand")

    identity_signal = wants_identity(ask)
    if identity_signal["fires"]:
        stages.append("identity_extraction")

    total_signal = wants_total(ask)
    if total_signal["fires"]:
        stages.append("total_computation")

    rule_signal = wants_rule_application(ask)
    verb_rules = _find_verb_rules(passages)
    rule_hit = _find_rule(passages)
    rule_application_method = None
    if rule_hit:
        stages.append("rule_application")
        rule_application_method = "forward_chain" if (rule_signal["fires"] and len(verb_rules) > 1) else "single_step"

    if not stages:
        stages.append("lookup_fallback")

    return {
        "stages": stages,
        "signals": {"document": document_signal, "identity": identity_signal, "total": total_signal, "rule_application": rule_signal},
        "rule_application_method": rule_application_method,
    }


def _role_matches(rule: dict, passages: list[dict]) -> bool:
    import re

    role_noun = re.sub(r"^(a|an|the)\s+", "", rule["subject_placeholder"].strip().lower())
    full_text = " ".join(p.get("text", "") for p in passages).lower()
    return role_noun in full_text


def _group_margin(hits: list[dict], score_key: str) -> float:
    """The real top-group-vs-runner-up-group gap, not whatever gap exists
    between the top 2 individual *passages*.

    Flat disambiguation's candidates are passages, but the actual decision
    is which GROUP the ask is about, and a group can have several
    passages. If the top 2 passages by score both happen to belong to the
    same (correct) group -- expected, even desirable, since that group's
    passages should score similarly -- comparing hits[0] against hits[1]
    directly measures within-group noise, not the real separation from a
    competing group, and can come out tiny or zero even when that group
    decisively beats every other one (EXP-069 found this exact case: two
    E2 passages tied for the top dense score, margin computed as 0.0,
    even though E2 clearly outscored E1 overall). Takes each group's best
    score, then the gap between the best group and the runner-up group.
    `hits` must include every passage (top_k=len(story_passages)) for this
    to see every group's best score, not just the top couple of passages.
    """
    best_by_group: dict = {}
    for hit in hits:
        group = hit["passage"].get("group")
        value = hit[score_key]
        if group not in best_by_group or value > best_by_group[group]:
            best_by_group[group] = value
    scores = sorted(best_by_group.values(), reverse=True)
    if len(scores) < 2:
        return scores[0] if scores else 0.0
    return scores[0] - scores[1]


def reason(ask: str, passages: list[dict], use_real_ner: bool = False) -> dict:
    """`use_real_ner=True` threads through to every lab.common.entities.
    detect_primary call this function makes (identity extraction, graph
    expansion, long-form outlining) -- see that function for why it
    defaults to False: a real transformers model call is real added
    latency, which every existing caller of reason() keeps unchanged
    unless it explicitly opts in.
    """
    trace = []
    stage_plan = plan_stages(ask, passages, use_real_ner=use_real_ner)
    trace.append({"step": "plan", **stage_plan})
    if not passages:
        # FORBIDDEN.md's narrow exception, recorded 2026-10-16: literally no
        # passages at all (not "retrieval found nothing" -- that is a
        # different, later case, and still abstains the existing way). The
        # checked-but-empty case never reaches this branch; it is checked
        # before anything else runs, precisely so it can never be reached by
        # feeding an ask that merely fails to match real content.
        from lab.common.open_domain import answer_from_general_knowledge

        result = answer_from_general_knowledge(ask)
        trace.append({"step": "no_context_fallback", "fallback_reason": result["fallback_reason"]})
        return _finish(ask, trace, result["decision"], result["text"], set())
    plan = analyze(ask)
    trace.append({"step": "analyze_ask", "task_type": plan["task_type"], "subquestions": plan["subquestions"]})

    # Long-form dispatch (lab.common.longform, EXP-052/053/078): the fifth
    # signal this module's own docstring named as a todo since before this
    # function existed. Checked early and exclusively -- an ask that wants
    # a written document is a genuinely different shape of answer, not a
    # longer version of the same short lookup below, so it does not fall
    # through to disambiguation/identity/total/rule at all once it fires.
    # decision="supported_with_flags" (a fourth value, alongside
    # "supported"/"inconclusive"/"ungrounded") is used rather than
    # unconditionally "supported" when lab.common.working_memory found a
    # real cross-page contradiction -- calling a self-contradictory
    # document "supported" would hide exactly the thing this signal exists
    # to catch.
    document_signal = stage_plan["signals"]["document"]
    trace.append({"step": "intent_signal", "signal": "document", **document_signal})
    if document_signal["fires"]:
        from lab.common.ingest import findings_from_chunks
        from lab.common.longform import write_long_document

        # findings_from_chunks assigns a clean, sequential citation label
        # ("1", "2", ...) instead of reusing a passage's own id directly --
        # that id is whatever naming scheme the caller's retrieval/ingest
        # step happens to use internally (a chunk id, a database key, a
        # leaf id), never meant for a document's reader to see, and
        # lab.common.assemble.render_unit writes the citation field
        # verbatim into the rendered document body (caught on a real
        # document whose passages were named "CHUNK0008" -- that string
        # ended up in the final .docx, EXP-081).
        findings = findings_from_chunks([p for p in passages if p.get("text")])
        doc_result = write_long_document(ask, findings, task=plan["task_type"], use_real_ner=use_real_ner)
        trace.append(
            {
                "step": "longform_write",
                "leaves": len(doc_result["rewrite_diagnostics"]),
                "rewrite_diagnostics": doc_result["rewrite_diagnostics"],
                "consistency_flags": doc_result["consistency_flags"],
                "working_memory": doc_result["working_memory"],
            }
        )
        decision = "supported_with_flags" if doc_result["consistency_flags"] else "supported"
        return _finish(ask, trace, decision, doc_result["document"], set(doc_result["working_memory"]["citations"]))

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
        #
        # navigate_dual (lab.common.semantic_index), not nested_index's
        # plain lexical-only navigate: this branch used to have no semantic
        # signal at all, so a paraphrased ask had no way through it -- the
        # same gap EXP-067 fixed for flat disambiguation, finally carried
        # over here too. Same lexical-floor + semantic-margin, independent
        # signals that must agree, as the flat branch below.
        level_keys = list(hierarchical[0]["hierarchy"].keys())
        items = [{**p, **p["hierarchy"]} for p in hierarchical]
        root = build_nested_index(items, level_keys)
        nav = navigate_dual(ask, root)
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
        # top_k=len(...) for both signals: the margin checks below need
        # every passage's score, in every group, to find each group's best
        # score -- not just the top couple of passages overall, which can
        # all belong to one group (EXP-069's regression -- see
        # _group_margin's docstring).
        lexical_hits = Index(story_passages).search(ask, top_k=len(story_passages))
        semantic_hits = SemanticIndex(story_passages).search(ask, top_k=len(story_passages))
        if not lexical_hits or not semantic_hits:
            return _finish(ask, trace, "inconclusive", ABSTAIN_TEXT, citations, reason="no passage matched the ask")

        # lexical_abstain also requires a real margin over the runner-up
        # *group*, not just clearing the floor (EXP-071) and not just the
        # gap between the top 2 individual passages (EXP-069: those can
        # both be the correct group's own passages, understating how
        # decisive that group really is). _group_margin takes each group's
        # best score first, then compares group to group.
        lexical_margin = _group_margin(lexical_hits, "dense")
        lexical_abstain = lexical_hits[0]["dense"] < MIN_DENSE_SCORE or lexical_margin < MIN_LEXICAL_MARGIN
        semantic_margin = _group_margin(semantic_hits, "score")
        semantic_abstain = semantic_margin < MIN_SEMANTIC_MARGIN
        lexical_group = lexical_hits[0]["passage"].get("group")
        semantic_group = semantic_hits[0]["passage"].get("group")

        trace.append(
            {
                "step": "disambiguate",
                "lexical_group": lexical_group,
                "lexical_dense": round(lexical_hits[0]["dense"], 4),
                "lexical_margin": round(lexical_margin, 4),
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

    # Cross-reference expansion (lab.common.graph_index, EXP-075): the one
    # gap neither the flat nor the hierarchical path above can close by
    # design -- each commits to one group/leaf and returns only its
    # passages, so a fact about the same named entity living in a
    # *different* group/chapter (e.g. the company a resolved person works
    # for, documented in its own separate section) is never reachable.
    # Purely additive and classical: if the ask names a person/org that
    # the entity graph also finds connected to passages outside the
    # already-resolved scope, those are unioned in, never removed from or
    # substituted for what was already resolved. Does nothing when no
    # named entity is in the ask, or when expansion finds nothing new --
    # the existing single-path resolution above is still what does the
    # real work for every ask that doesn't need this.
    facts: dict = {}
    answer_parts: list[str] = []
    rule_conditional = False

    ask_entities = [m["text"] for m in detect_primary(ask, use_real_ner=use_real_ner) if m["label"] in ("person", "organization")]
    if ask_entities:
        graph = build_entity_graph(passages, use_real_ner=use_real_ner)
        passages_by_id = {p["id"]: p for p in passages}
        scoped_ids = {p["id"] for p in scoped}
        for entity_text in ask_entities:
            expansion = expand_from_entity(entity_text, graph, passages_by_id, max_hops=2)
            new_passages = [p for p in expansion["passages"] if p["id"] not in scoped_ids]
            if new_passages:
                scoped = scoped + new_passages
                scoped_ids.update(p["id"] for p in new_passages)
                trace.append({"step": "graph_expand", "entity": entity_text, "added_passage_ids": [p["id"] for p in new_passages], "path": expansion["path"]})
                # Surfacing, not just widening: a fact in a newly-added
                # passage otherwise sits in scope but never reaches the
                # answer unless another signal (identity/total/rule)
                # happens to also cover it -- measured directly in EXP-075,
                # where the registry fact was correctly added to scope but
                # silently dropped from the answer text until this lookup
                # was added. Same extractor and same quote_check the final
                # lookup_fallback below uses, just run against only the
                # newly-added passages so it answers the specific
                # cross-referenced sub-question, not the whole ask again.
                # tau is deliberately lower than the main lookup_fallback's
                # 0.34: that threshold guards against pulling a span from an
                # irrelevant passage among many candidates, a risk that
                # doesn't apply here -- new_passages already passed the
                # entity-graph relevance check, so a weaker lexical overlap
                # with the full compound ask (measured directly, EXP-075:
                # score 0.1442, well under 0.34) doesn't mean the content is
                # off-topic, just that the ask's other half (about a
                # different fact) dilutes the match.
                cross_ref = answer_with_agreement(ask, new_passages, tau=0.1)
                cross_ref_text = next((p["text"] for p in new_passages if p["id"] == cross_ref.get("passage_id")), "")
                if cross_ref["span"] and quote_check(cross_ref["span"], cross_ref_text):
                    answer_parts.append(f"{cross_ref['span']} [{cross_ref['passage_id']}]")
                    citations.add(cross_ref["passage_id"])
                    trace.append({"step": "graph_expand_lookup", "entity": entity_text, "span": cross_ref["span"], "passage_id": cross_ref.get("passage_id")})

    identity_signal = stage_plan["signals"]["identity"]
    trace.append({"step": "intent_signal", "signal": "identity", **identity_signal})
    if identity_signal["fires"]:
        full_text = " ".join(p["text"] for p in scoped)
        mentions = detect_primary(full_text, use_real_ner=use_real_ner)
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

    total_signal = stage_plan["signals"]["total"]
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
                if applied["matched"]:
                    # Same exception/condition check the verb-rule branch
                    # already has (EXP-089/026) -- a threshold rule's own
                    # consequence can carry a trailing "unless"/"provided
                    # that" clause exactly like the verb-rule shape, and
                    # nothing checked it until now, a real, named gap.
                    _, exception_conditions, polarity = split_exceptions(rule["consequence"])
                    exception_context = [p["text"] for p in passages if p["id"] != rule_passage["id"]]
                    exception_result = check_exceptions(exception_conditions, exception_context, polarity or "negative")
                    trace.append({"step": "check_exception", "result": exception_result, "polarity": polarity})
                    if exception_result["status"] == "holds":
                        reason_phrase = "the rule's exception holds" if polarity == "negative" else "the rule's condition is not satisfied"
                        answer_parts.append(f"policy does not apply: {reason_phrase} ({rule['raw']!r}) [{rule_passage['id']}]")
                    else:
                        citations.add(rule_passage["id"])
                        conditional = exception_result["status"] == "unknown"
                        if conditional:
                            rule_conditional = True
                        unresolved_phrase = "the rule's exception is unresolved" if polarity == "negative" else "the rule's condition is unresolved"
                        suffix = f" ({unresolved_phrase} -- not confirmed either way)" if conditional else ""
                        answer_parts.append(f"policy applies: {applied['consequence']}{suffix} [{rule_passage['id']}]")
                else:
                    answer_parts.append(f"policy does not apply (threshold not exceeded) [{rule_passage['id']}]")
        else:
            # Excludes any passage that is itself a rule (verb or threshold
            # shape), not just rule_passage -- found by EXP-084's own
            # multi-rule fixture: extract_fact_triple doesn't reject every
            # rule-shaped sentence (e.g. "If anyone goes to jail, their
            # license will be suspended." parses as a spurious triple,
            # subject="their license"/verb="suspend"), so a SECOND rule
            # among the passages was silently picked as "the fact" instead
            # of the real fact passage whenever it happened to sort before
            # it -- a latent bug no single-rule fixture could ever surface.
            fact_passage = next(
                (p for p in scoped if not parse_conditional_rule(p.get("text", "")) and not parse_threshold_rule(p.get("text", "")) and extract_fact_triple(p["text"])),
                None,
            )
            if fact_passage:
                fact = extract_fact_triple(fact_passage["text"])
                applied = apply_rule(rule, fact)
                trace.append({"step": "apply_rule", "kind": "verb", "result": applied, "fact_passage": fact_passage["id"]})
                if applied["matched"]:
                    # apply_rule's own lemma-match check has no idea the
                    # rule's consequence might carry a trailing exception/
                    # condition clause -- EXP-083/085 proved split_exceptions/
                    # check_exceptions standalone, but until this call
                    # existed, reason() itself never checked a matched
                    # rule's own condition at all (EXP-089). EXP-026
                    # generalized the mechanism beyond "unless"-style
                    # negative exceptions to also recognize "provided that"-
                    # style positive conditions (the opposite polarity: they
                    # block the consequence if FALSE, not if true), so
                    # polarity is threaded through here too. Every OTHER
                    # given passage is the context a condition is checked
                    # against -- the same "exceptions are global policy
                    # text, not scoped to one story" principle _find_rule
                    # already applies when it scans every passage, not just
                    # `scoped`.
                    _, exception_conditions, polarity = split_exceptions(rule["consequence"])
                    exception_context = [p["text"] for p in passages if p["id"] not in (rule_passage["id"], fact_passage["id"])]
                    exception_result = check_exceptions(exception_conditions, exception_context, polarity or "negative")
                    trace.append({"step": "check_exception", "result": exception_result, "polarity": polarity})
                    if exception_result["status"] == "holds":
                        reason_phrase = "the rule's exception holds" if polarity == "negative" else "the rule's condition is not satisfied"
                        answer_parts.append(f"policy does not apply: {reason_phrase} ({rule['raw']!r}) [{rule_passage['id']}]")
                    else:
                        citations.update([rule_passage["id"], fact_passage["id"]])
                        conditional = exception_result["status"] == "unknown"
                        if conditional:
                            rule_conditional = True
                        unresolved_phrase = "the rule's exception is unresolved" if polarity == "negative" else "the rule's condition is unresolved"
                        suffix = f" ({unresolved_phrase} -- not confirmed either way)" if conditional else ""
                        answer_parts.append(
                            f"{fact_passage['text']} [{fact_passage['id']}] matches the rule's trigger ({applied['trigger_lemma']}): "
                            f"{rule['raw']} [{rule_passage['id']}] Therefore, {applied['consequence']}{suffix}."
                        )

                        if stage_plan["rule_application_method"] == "forward_chain":
                            # EXP-084's actual new capability: a derived fact
                            # can itself trigger a SECOND rule among the
                            # other given passages -- forward_chain's own
                            # multi-step fixpoint loop (EXP-083), reachable
                            # through reason() itself for the first time, not
                            # just through a standalone forward_chain() call
                            # in an exploration script. Purely additive: the
                            # primary single-step sentence above is
                            # untouched, and a rule set with only one usable
                            # rule (today's entire existing regression suite)
                            # never reaches this branch at all (plan_stages
                            # only chooses "forward_chain" when more than one
                            # verb rule exists), so no existing case changes.
                            primary_signatures = {(d["subject"], d["verb_lemma"], d.get("object")) for d in instantiate_consequence(rule, fact)}
                            seed_signature = (fact["subject"], fact["verb_lemma"], fact.get("object"))
                            chain_result = forward_chain([fact], _find_verb_rules(passages), context_texts=exception_context)
                            extra_facts = [
                                d
                                for d in chain_result["facts"]
                                if (d["subject"], d["verb_lemma"], d.get("object")) not in primary_signatures
                                and (d["subject"], d["verb_lemma"], d.get("object")) != seed_signature
                            ]
                            trace.append({"step": "forward_chain", "extra_facts": extra_facts})
                            for extra in extra_facts:
                                if extra.get("conditional"):
                                    rule_conditional = True
                                extra_suffix = " (unresolved -- not confirmed either way)" if extra.get("conditional") else ""
                                answer_parts.append(f"Furthermore, {extra['subject']} {extra['verb_lemma']} {extra['object']}{extra_suffix}")

    if not answer_parts:
        # No identity/total/rule signal fired -- this is a plain lookup ask.
        # Fall back to the same single-slot extractor lab.common.engine uses.
        qa = answer_with_agreement(ask, scoped, tau=0.34)
        trace.append({"step": "lookup_fallback", "span": qa["span"], "passage_id": qa.get("passage_id")})
        if not qa["span"] or not quote_check(qa["span"], next((p["text"] for p in scoped if p["id"] == qa.get("passage_id")), "")):
            return _finish(ask, trace, "inconclusive", ABSTAIN_TEXT, citations, reason="no span found")
        citations.add(qa["passage_id"])
        return _finish(ask, trace, "supported", f"{qa['span']} [{qa['passage_id']}]", citations, facts=facts)

    final_decision = "supported_with_flags" if rule_conditional else "supported"
    return _finish(ask, trace, final_decision, ". ".join(answer_parts) + ".", citations, facts=facts)


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
