"""The reasoning brain: one controller, not a dispatcher to separate task-type engines.

THE canonical entry point: `reason()` below. `lab.common.engine.run_task`
(a pre-dating, independent controller) is RETIRED as of 2026-11-03's
reasoning-layer audit follow-up (AUDIT.md Top Finding #2): its two
capabilities genuinely absent from this module -- a multi-round
retrieve-more-with-budget loop, and a `"contradicted"` decision label --
are now ported in below (`reason()`'s `retrieve_budget`/
`check_contradiction` params). The project now has exactly one live
reasoning controller.

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
lab.common.qa extractor lab.common.engine used (before its 2026-11-03
retirement, see above). A question like
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
from lab.common.connectors import fetch_context_passages
from lab.common.entities import AMOUNT_RE, detect_primary, parse_address
from lab.common.graph_index import build_entity_graph, expand_from_entity
from lab.common.index import Index
from lab.common.inference import check_exceptions, forward_chain, instantiate_consequence, split_exceptions
from lab.common.intent_signals import wants_document, wants_identity, wants_rule_application, wants_total
from lab.common.nested_index import MIN_DENSE_SCORE, build_nested_index
from lab.common.qa import answer_with_agreement, answer_with_real_qa
from lab.common.rules import apply_rule, apply_threshold_rule, extract_fact_triple, parse_conditional_rule, parse_threshold_rule
from lab.common.semantic_index import MIN_LEXICAL_MARGIN, MIN_SEMANTIC_MARGIN, SemanticIndex, navigate_dual
from lab.common.temporal import check_temporal_bound, find_temporal_bound
from lab.common.textutil import normalize
from lab.common.verify import quote_check

ABSTAIN_TEXT = "Insufficient evidence."


def _find_rule(passages: list[dict]):
    """Scan every passage for either rule shape. Rules can be global policy
    text, not necessarily inside the resolved story's own group, so this
    always searches the full passage set, not the disambiguated scope.

    Follow-up (2026-11-10): threshold shape is checked FIRST, not second.
    THRESHOLD_RULE_RE is strictly the more specific pattern (a possessive
    subject plus an explicit numeric comparison), while RULE_RE (parse_
    conditional_rule's own pattern) is a generic "if X, Y." match that
    also happens to accept a threshold-shaped sentence whenever its if-
    clause has an extractable main verb (e.g. "exceeds") -- found by
    direct testing (a bare "If a customer's total exceeds $500, a $50
    fee applies." sentence, with no leading "Company policy:"/"Hospital
    policy:" prefix) to always lose to parse_conditional_rule under the
    old verb-first order, misclassifying it as kind="verb" and silently
    producing no answer (no fact passage has an "exceed" verb to match
    against). None of this project's existing threshold-rule fixtures hit
    this: every one of them prefixes the sentence with a label ("Company
    policy:", "Hospital policy:", ...) that RULE_RE's `^\\s*if\\s+` anchor
    already rejects outright, which is why the collision went unnoticed
    until a bare "If ..." threshold sentence was tried directly. Trying
    the narrower, more specific pattern first is strictly safe for every
    existing fixture (a verb-rule sentence, lacking THRESHOLD_RULE_RE's
    possessive+comparison shape, never matches it) and fixes the bare-
    sentence case going forward.
    """
    for passage in passages:
        rule = parse_threshold_rule(passage.get("text", ""))
        if rule:
            return "threshold", rule, passage
        rule = parse_conditional_rule(passage.get("text", ""))
        if rule:
            return "verb", rule, passage
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


def _find_verb_rules_with_passages(passages: list[dict]) -> list[tuple[dict, dict]]:
    """Same scan as _find_verb_rules, but keeping each rule's source
    passage alongside it. FIX (audit 2026-11-03): parse_conditional_rule's
    own return shape has no passage-id field (a rule dict only knows its
    own raw text), so a plain `_find_verb_rules(passages)` call -- which is
    what forward_chain actually receives -- structurally cannot say which
    passage any given rule came from. This function exists only so
    reason()'s forward_chain call site can build a raw-rule-text ->
    passage-id lookup for its dependency_tree, without changing
    _find_verb_rules' own return shape (still a plain list[dict], exactly
    what forward_chain's `rules` parameter expects, and exactly what
    plan_stages' count-only usage already relies on).
    """
    pairs = []
    for passage in passages:
        rule = parse_conditional_rule(passage.get("text", ""))
        if rule:
            pairs.append((rule, passage))
    return pairs


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
        # FIX (audit 2026-11-03, Finding 1): forward_chain is a verb-rule-only
        # mechanism (reason()'s own forward_chain dispatch sits inside the
        # `kind == "verb"` branch, never the threshold branch). Gating this
        # choice on `len(verb_rules) > 1` alone, without also checking that
        # THIS call's rule_hit is itself verb-kind, let the plan predict
        # "forward_chain" for a call that would actually execute the
        # threshold branch (whenever a passage set mixes a threshold rule,
        # sorted first by _find_rule's passage-order scan, with 2+ verb
        # rules elsewhere) -- a real, confirmed disagreement between this
        # function's own documented invariant ("accurately predicts what
        # reason() is actually about to do") and actual execution.
        rule_application_method = "forward_chain" if (rule_hit[0] == "verb" and rule_signal["fires"] and len(verb_rules) > 1) else "single_step"

    if not stages:
        stages.append("lookup_fallback")

    return {
        "stages": stages,
        "signals": {"document": document_signal, "identity": identity_signal, "total": total_signal, "rule_application": rule_signal},
        "rule_application_method": rule_application_method,
    }


def _check_rule_gate(rule: dict, context_texts: list[str]) -> dict:
    """Which gate (if any) governs this matched rule's consequence, and
    its current status -- condition/exception (EXP-026/091) checked
    first; a temporal bound (EXP-097, until/before/after/once) only
    when NO condition connective is present at all. A consequence is
    assumed to carry at most one gate, never both in the same step.

    Returns status in holds/not_holds/unknown/no_exception regardless
    of which underlying mechanism produced it -- "holds" always means
    "block the consequence", "not_holds" always means "proceed
    cleanly" -- so every existing caller keeps checking status==
    "holds"/"unknown" exactly as it already did; this function absorbs
    the difference between a truth-gate and a timing-gate internally,
    the same way check_exceptions already absorbs negative-vs-positive
    polarity.
    """
    _, exception_conditions, polarity = split_exceptions(rule["consequence"])
    if exception_conditions:
        result = check_exceptions(exception_conditions, context_texts, polarity or "negative")
        return {"kind": "condition", "polarity": polarity, "status": result["status"], "detail": result}

    temporal_bound = find_temporal_bound(rule["consequence"])
    if temporal_bound:
        result = check_temporal_bound(temporal_bound["bound_clause"], context_texts, temporal_bound["direction"])
        status = {"not_in_effect": "holds", "in_effect": "not_holds", "unknown": "unknown"}[result["status"]]
        return {"kind": "temporal", "polarity": None, "status": status, "detail": result, "phrase": temporal_bound["phrase"]}

    return {"kind": "none", "polarity": None, "status": "no_exception", "detail": None}


def _role_matches(rule: dict, passages: list[dict]) -> bool:
    import re

    role_noun = re.sub(r"^(a|an|the)\s+", "", rule["subject_placeholder"].strip().lower())
    full_text = " ".join(p.get("text", "") for p in passages).lower()
    return role_noun in full_text


def _add_dependency(dep_nodes: list[dict], node_id: str, kind: str, summary: str, depends_on=()) -> None:
    """Appends one node to reason()'s dependency tree: `node_id` is a
    stable, human-readable label derived from data already computed at
    the call site (a passage id, a rule's own passage id, a fixed stage
    label) -- never freely generated. `depends_on` names the other node
    ids (almost always passage ids, or an earlier node this function
    itself added) this node's truth rests on. Appending in execution
    order, with no dedup, is deliberate: a tree is read by walking
    `depends_on` edges backward from whichever node the final answer
    cites, not by scanning the flat list for uniqueness.
    """
    dep_nodes.append({"id": node_id, "kind": kind, "summary": summary, "depends_on": list(depends_on)})


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


def _check_cross_passage_contradiction(ask: str, passages: list[dict], use_real_qa: bool = False, use_real_nli: bool = False) -> list[dict]:
    """Port of lab.common.engine's own `judge_question`/`conflict_across`
    usage -- the one piece of engine.py's `"contradicted"` decision label
    (2026-11-03 audit, AUDIT.md Top Finding #2) genuinely absent from
    reason(): reason() finds only ONE best-scoring span per question and
    never checks whether a DIFFERENT passage would answer the same
    question differently. Answers `ask` against each passage
    independently, then checks every pair of resulting spans for
    contradiction, exactly the way engine.judge_question/
    verify.conflict_across already do -- same primitives, not a new
    mechanism, reimplemented inline here only because conflict_across
    itself hardcodes the classical `nli.judge` call and `use_real_nli`
    needs to swap it for the real checkpoint (`real_encoders.real_nli`,
    same {"entail","neutral","contradict"} shape), same opt-in discipline
    every other real-model flag in this module already follows.

    Called only from reason() when `check_contradiction=True` (default
    False) -- see that function's own docstring.
    """
    from lab.common.nli import judge as classical_judge
    from lab.common.textutil import normalize, numbers

    judge_fn = classical_judge
    if use_real_nli:
        from lab.common.real_encoders import real_nli

        judge_fn = real_nli

    per_passage = []
    for p in passages:
        qa = answer_with_real_qa(ask, [p]) if use_real_qa else answer_with_agreement(ask, [p], tau=0.1)
        if qa.get("span"):
            per_passage.append((p.get("id"), qa["span"]))

    conflicts = []
    for i, (id_a, span_a) in enumerate(per_passage):
        for id_b, span_b in per_passage[i + 1 :]:
            if normalize(span_a) == normalize(span_b):
                continue
            probs = judge_fn(f"The value is {span_a}.", f"The value is {span_b}.")
            if probs["contradict"] >= 0.45 or set(numbers(span_a)) != set(numbers(span_b)):
                conflicts.append({"a": id_a, "b": id_b, "span_a": span_a, "span_b": span_b, "nli": probs})
    return conflicts


def reason(
    ask: str,
    passages: list[dict],
    use_real_ner: bool = False,
    connector=None,
    connector_top_k: int = 5,
    use_real_qa: bool = False,
    use_real_nli: bool = False,
    use_repair: bool = False,
    retrieve_budget: int = 1,
    check_contradiction: bool = False,
    plain_english: bool = False,
    template_id: str | None = None,
) -> dict:
    """Thin outer wrapper around `_reason_once` (the function this
    docstring used to belong to, unchanged below) adding the two
    capabilities `lab.common.engine.run_task` has that `_reason_once`
    alone does not (2026-11-03 audit, AUDIT.md Top Finding #2): a
    multi-round retrieve-more-with-budget loop, and a `"contradicted"`
    top-level decision. Porting these closes the gap that finding
    identified -- `engine.py` is retired as of this change (see its own
    former docstring's history in git log; this project now has exactly
    one live reasoning controller, as the finding recommended).

    `retrieve_budget` (default 1: exactly one pass, today's existing
    behavior, zero regression): when `connector` is given and the first
    pass's decision is `"inconclusive"`/`"ungrounded"`, retries up to
    `retrieve_budget` rounds total, doubling `connector_top_k` each
    round before giving up -- engine.py's own `retrieve_more` action,
    generalized to this module's connector (the one place in reason()
    that genuinely samples a limited top-k from a larger store rather
    than already searching every given passage in full, as every
    in-process signal check below does). A caller with no connector, or
    `retrieve_budget=1` (the default), takes the exact same single-pass
    path as before this parameter existed.

    `check_contradiction` (default False): after a pass that would
    otherwise return `"supported"`/`"supported_with_flags"`, additionally
    checks whether a DIFFERENT given passage would answer `ask`
    differently (via `_check_cross_passage_contradiction` above) --
    engine.py's own `judge_question`/`conflict_across` mechanism, ported
    rather than reimplemented. A genuine conflict downgrades the decision
    to `"contradicted"` (a new value, only ever returned when this flag
    is explicitly set) and adds a `"contradictions"` key plus one
    `contradiction_flag` dependency_tree node per conflicting pair.
    Default False: no existing caller's decision set changes unless it
    opts in.

    `plain_english` (default False, same opt-in shape, 2026-11-10):
    threads through to `write_long_document`'s own flag of the same
    name when `document_write` is one of this ask's stages -- see that
    function's docstring for what it actually does
    (`plain_language.simplify_document`: vocabulary substitution plus
    gated passive-to-active/sentence-splitting). A no-op for any ask
    that doesn't reach the document-writing stage.

    `template_id` (default None, same opt-in shape, 2026-11-10): threads
    through to `write_long_document`'s own `template_id` -- when given
    (a registered `lab.common.doc_tools` template), the document-writing
    stage's outline comes from that template's own declared sections
    instead of entity-grouping, and the trace's `document_write` step
    gains a `contract_violations` field (lab.common.doc_tools.
    check_template_contracts). A no-op (outline unchanged, contract_
    violations stays None) for any ask that doesn't reach that stage, or
    when this is left at its default.
    """
    result = _reason_once(
        ask,
        passages,
        use_real_ner=use_real_ner,
        connector=connector,
        connector_top_k=connector_top_k,
        use_real_qa=use_real_qa,
        use_real_nli=use_real_nli,
        use_repair=use_repair,
        plain_english=plain_english,
        template_id=template_id,
    )
    round_num = 1
    while connector is not None and round_num < retrieve_budget and result["decision"] in ("inconclusive", "ungrounded"):
        round_num += 1
        connector_top_k = connector_top_k * 2
        retried = _reason_once(
            ask,
            passages,
            use_real_ner=use_real_ner,
            connector=connector,
            connector_top_k=connector_top_k,
            use_real_qa=use_real_qa,
            use_real_nli=use_real_nli,
            use_repair=use_repair,
            plain_english=plain_english,
            template_id=template_id,
        )
        retried["trace"] = result["trace"] + [{"step": "retrieve_more", "round": round_num, "connector_top_k": connector_top_k}] + retried["trace"]
        result = retried

    if check_contradiction and result["decision"] in ("supported", "supported_with_flags"):
        conflicts = _check_cross_passage_contradiction(ask, passages, use_real_qa=use_real_qa, use_real_nli=use_real_nli)
        if conflicts:
            result = dict(result)
            result["decision"] = "contradicted"
            result["contradictions"] = conflicts
            dependency_tree = list(result["dependency_tree"])
            for c in conflicts:
                dependency_tree.append(
                    {
                        "id": f"contradiction:{c['a']}:{c['b']}",
                        "kind": "contradiction_flag",
                        "summary": f"{c['span_a']!r} (from {c['a']}) conflicts with {c['span_b']!r} (from {c['b']})",
                        "depends_on": [c["a"], c["b"]],
                    }
                )
            result["dependency_tree"] = dependency_tree
            result["trace"] = result["trace"] + [{"step": "contradiction_check", "conflicts": conflicts}]

    return result


DYNAMIC_EXPANSION_KINDS = ("derived_fact", "related_case")


def reason_dynamic(
    ask: str,
    passages: list[dict],
    use_real_ner: bool = False,
    store=None,
    max_rounds: int = 5,
    **reason_kwargs,
) -> dict:
    """Follow-up (2026-11-10): a bounded, traced, closed-vocabulary tool
    router generalizing `reason()`'s single fixed pass into a loop --
    the project owner's own request, after direct testing showed the
    one case originally worried about (a multi-hop rule chain feeding
    an identity answer) already works in one pass, with no loop needed
    (see AUDIT.md, "tested the self-expanding core's own motivating
    scenario directly"). What genuinely doesn't exist yet is letting
    one round's result change what the NEXT round has available to
    reason over -- not a free-form planner inventing steps, but a fixed,
    named set of ways the input can grow, each one an EXISTING, already-
    measured tool, never a new one invented at call time:

    - `derived_fact`: a fact `forward_chain` derived this round (already
      bounded/deduplicated/traced internally -- see inference.py) gets
      textified into one new pseudo-passage (`id="derived:<round>:<i>"`,
      deterministic `f"{subject} {verb_lemma} {object}."` template, no
      generative model) so a LATER round's identity/total/graph stages,
      which only ever scan passage text today, can see it too -- closing
      exactly the gap this project's own rule-dispatch/total-scope bug
      hunt surfaced (a derived consequence never reaching another
      stage's input), without inventing a new reasoning mechanism.
    - `related_case`: when a `store` (lab.common.store.Store) is given
      AND this round's decision is `"inconclusive"`/`"ungrounded"`,
      `store.search(ask)` is called once and any REAL passages it finds
      that aren't already in the passage set are added -- the "find
      related cases automatically" capability, built on the already-
      measured RRF-fused hybrid search (store.py's own follow-up), not
      a new retrieval mechanism. These are real passages with real ids,
      never synthetic text, so they never weaken citation grounding the
      way a `derived_fact` pseudo-passage's id could (flagged below).

    Stops the moment a round adds nothing (fixpoint) or after
    `max_rounds` regardless (same cap discipline as `forward_chain`'s
    own `max_steps` -- a malformed input can't loop forever). Every
    round is one entry in the returned `"rounds"` list (round number,
    decision, passage count, what was added and why, or why it
    stopped) -- nothing silent. `reason()` itself is completely
    unchanged; this is a new, separate, opt-in entry point, never
    called by `reason()` or any existing caller.

    Named limit, honestly: a `derived_fact` pseudo-passage's citation id
    (`"derived:..."`) is not a literal source quote the way every other
    citation in this project is -- if a later round's answer cites one,
    that id's own provenance (`derivation` field, carried from
    `forward_chain`'s trace) names the real rule/fact it came from, the
    same non-literal-citation idiom `_add_dependency`'s own
    `"derived_fact"` dependency-tree nodes already use elsewhere in this
    module. A second named limit: `document_write` stays its own
    exclusive pipeline exactly as it is in `plan_stages` today (a
    document-writing ask short-circuits to ONLY that stage) -- this
    router does not attempt to interleave page-by-page document writing
    with the round loop, that would be a different, larger change.
    """
    current_passages = list(passages)
    seen_fact_signatures: set[tuple] = set()
    rounds = []
    result = None
    for round_num in range(1, max_rounds + 1):
        result = reason(ask, current_passages, use_real_ner=use_real_ner, **reason_kwargs)
        round_entry = {"round": round_num, "decision": result["decision"], "passage_count": len(current_passages)}

        derived_facts = [f for t in result["trace"] if t.get("step") == "forward_chain" for f in t.get("extra_facts", [])]
        new_passages = []
        for i, fact in enumerate(derived_facts):
            signature = (fact["subject"], fact["verb_lemma"], fact.get("object"))
            if signature in seen_fact_signatures:
                continue
            seen_fact_signatures.add(signature)
            new_passages.append(
                {
                    "id": f"derived:{round_num}:{i}",
                    "text": f"{fact['subject']} {fact['verb_lemma']} {fact['object']}.",
                    "kind": "derived_fact",
                    "derivation": fact.get("derivation"),
                }
            )

        if store is not None and result["decision"] in ("inconclusive", "ungrounded"):
            existing_ids = {p.get("id") for p in current_passages}
            for hit in store.search(ask, top_k=5):
                candidate = hit.get("passage", hit)
                if candidate.get("id") not in existing_ids:
                    new_passages.append({**candidate, "kind": "related_case"})
                    existing_ids.add(candidate.get("id"))

        if not new_passages:
            round_entry["added"] = []
            round_entry["stopped_reason"] = "fixpoint"
            rounds.append(round_entry)
            break
        round_entry["added"] = [{"id": p["id"], "kind": p["kind"]} for p in new_passages]
        rounds.append(round_entry)
        current_passages = current_passages + new_passages
    else:
        rounds[-1]["stopped_reason"] = "max_rounds"

    result = dict(result)
    result["rounds"] = rounds
    return result


def _reason_once(ask: str, passages: list[dict], use_real_ner: bool = False, connector=None, connector_top_k: int = 5, use_real_qa: bool = False, use_real_nli: bool = False, use_repair: bool = False, plain_english: bool = False, template_id: str | None = None) -> dict:
    """One single pass of the signal-chain below -- called directly by
    reason() above, once per retry round. `use_real_ner=True` threads
    through to every lab.common.entities.
    detect_primary call this function makes (identity extraction, graph
    expansion, long-form outlining) -- see that function for why it
    defaults to False: a real transformers model call is real added
    latency, which every existing caller of reason() keeps unchanged
    unless it explicitly opts in.

    `use_real_qa`/`use_real_nli` (both default False, same opt-in shape
    as `use_real_ner`): flagged by the 2026-11-03 reasoning-layer audit
    (AUDIT.md, Top Finding #1) -- this project has repeatedly measured
    real QA (EXP-030/080) and real bidirectional NLI (EXP-031/041/056)
    checkpoints that no live caller of reason() ever actually used.
    `use_real_qa=True` swaps `graph_expand_lookup`'s and
    `lookup_fallback`'s span extraction from the classical lexical
    extractor to `qa.answer_with_real_qa` (the real deepset/deberta-v3-
    base-squad2 checkpoint). `use_real_nli=True` swaps the rewriter's own
    fidelity check (inside the `document_write` stage only) from the
    classical judge to `real_encoders.real_bidirectional_nli`. Neither
    touches the rule-exception/condition/temporal gate's own NLI check
    (`_check_rule_gate`), which already called the real model
    unconditionally before this flag existed. `use_real_qa`/`use_real_nli`
    default False, so every existing caller keeps exactly its already-
    measured behavior unless it explicitly opts in -- zero regression
    risk, same discipline `use_real_ner` already established.

    `use_repair` (default False, `document_write` stage only): opt-in use
    of each rewriter backend's own repair mechanism (flan-t5-small's
    retry-with-feedback, gemma3:270m's citation-splice) instead of this
    project's rewriter_backends.rewrite_unit dispatcher bypassing both --
    same audit finding as above; see that function's own docstring.

    `connector` (lab.common.connectors.QdrantConnector or GraphConnector,
    default None) is the external-data-connector hookup the project
    owner asked for: when given, its hits are fetched once, up front
    (lab.common.connectors.fetch_context_passages), deduplicated
    against `passages` by id, and unioned into `passages` BEFORE
    plan_stages or anything else below runs -- exactly the same
    "additional candidate passages" treatment the existing graph_expand
    stage already gives entity-graph hits, generalized to an external
    store. Every existing caller (connector=None, the default) takes
    the exact same code path as before this parameter existed: this is
    the one and only new branch, and it is a no-op whenever `connector`
    is not supplied. A connector can also turn a caller-supplied empty
    `passages` list into a non-empty one -- deliberate, since "no
    passages given directly" and "no context available at all" are
    different things once an external connector exists; FORBIDDEN.md's
    no_context_fallback exception is about the latter.

    This function also builds, alongside its existing `trace` (a flat,
    ordered execution log), an explicit dependency tree: a flat list of
    nodes under `dependency_tree`, each `{"id", "kind", "summary",
    "depends_on"}`, where `depends_on` names the other node ids (almost
    always passage ids) a node's truth rests on -- a resolved scope
    depends on the passage that resolved it, a rule's consequence
    depends on the rule passage AND the fact passage AND its own gate
    check, a forward-chained derived fact depends on the consequence
    that triggered it, and so on. This is purely additive bookkeeping
    over data every branch below was already computing for its own
    prose answer_parts/trace entries -- no new judgment call, no new
    extraction, nothing here changes `decision`/`text`/`citations`.
    """
    trace = []
    dep_nodes: list[dict] = []
    if connector is not None:
        connector_entities = [m["text"] for m in detect_primary(ask, use_real_ner=use_real_ner) if m["label"] in ("person", "organization")]
        external_passages = fetch_context_passages(connector, ask, ask_entities=connector_entities, top_k=connector_top_k)
        existing_ids = {p.get("id") for p in passages}
        new_passages = [p for p in external_passages if p.get("id") not in existing_ids]
        if new_passages:
            passages = passages + new_passages
            trace.append({"step": "connector_fetch", "added_passage_ids": [p["id"] for p in new_passages]})
            for p in new_passages:
                _add_dependency(dep_nodes, p["id"], "connector_evidence", f"fetched from external connector for ask {ask!r}", [])
    stage_plan = plan_stages(ask, passages, use_real_ner=use_real_ner)
    trace.append({"step": "plan", **stage_plan})
    # From here on, whether a block below EXECUTES is always decided by
    # membership in stage_plan["stages"] -- the plan computed above, once,
    # before anything ran -- never by a fresh, independently re-derived
    # condition that merely happens to currently agree with it. Each block
    # still computes its own local value (the hierarchical passage list,
    # ask_entities, rule_hit, ...) because it needs that VALUE to do its
    # work, not just a yes/no; plan_stages() calls the same deterministic
    # functions over the same inputs to decide the gate, so the two can
    # never disagree. lookup_fallback is the one deliberate exception
    # (search its name below for why).
    if "no_context_fallback" in stage_plan["stages"]:
        # FORBIDDEN.md's narrow exception, recorded 2026-10-16: literally no
        # passages at all (not "retrieval found nothing" -- that is a
        # different, later case, and still abstains the existing way). The
        # checked-but-empty case never reaches this branch; it is checked
        # before anything else runs, precisely so it can never be reached by
        # feeding an ask that merely fails to match real content.
        from lab.common.open_domain import answer_from_general_knowledge

        result = answer_from_general_knowledge(ask)
        trace.append({"step": "no_context_fallback", "fallback_reason": result["fallback_reason"]})
        return _finish(ask, trace, result["decision"], result["text"], set(), dependency_tree=dep_nodes)
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
    if "document_write" in stage_plan["stages"]:
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
        doc_result = write_long_document(ask, findings, task=plan["task_type"], use_real_ner=use_real_ner, use_real_nli=use_real_nli, use_repair=use_repair, plain_english=plain_english, template_id=template_id)
        trace.append(
            {
                "step": "longform_write",
                "leaves": len(doc_result["rewrite_diagnostics"]),
                "rewrite_diagnostics": doc_result["rewrite_diagnostics"],
                "consistency_flags": doc_result["consistency_flags"],
                "working_memory": doc_result["working_memory"],
                "contract_violations": doc_result["contract_violations"],
            }
        )
        decision = "supported_with_flags" if doc_result["consistency_flags"] else "supported"
        return _finish(ask, trace, decision, doc_result["document"], set(doc_result["working_memory"]["citations"]), dependency_tree=dep_nodes + doc_result["dependency_tree"])

    citations: set[str] = set()
    scoped = passages

    hierarchical = [p for p in passages if p.get("hierarchy")]
    if "hierarchical_navigate" in stage_plan["stages"]:
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
            return _finish(ask, trace, "inconclusive", ABSTAIN_TEXT, citations, reason=nav.get("abstain_reason", "navigation failed"), dependency_tree=dep_nodes)
        scoped = nav["leaf_passages"]
        _add_dependency(dep_nodes, "scope", "scope_resolution", f"hierarchical navigation resolved to {nav['path']}", [p["id"] for p in scoped])
    elif "disambiguate" in stage_plan["stages"]:
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
            return _finish(ask, trace, "inconclusive", ABSTAIN_TEXT, citations, reason="no passage matched the ask", dependency_tree=dep_nodes)

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
            return _finish(ask, trace, "inconclusive", ABSTAIN_TEXT, citations, reason="neither lexical nor semantic retrieval found a confident match", dependency_tree=dep_nodes)
        if not lexical_abstain and not semantic_abstain and lexical_group != semantic_group:
            return _finish(ask, trace, "inconclusive", ABSTAIN_TEXT, citations, reason=f"lexical and semantic retrieval disagree on which story matches ({lexical_group!r} vs {semantic_group!r})", dependency_tree=dep_nodes)

        matched = semantic_hits[0]["passage"] if lexical_abstain else lexical_hits[0]["passage"]
        resolved_group = matched.get("group")
        citations.add(matched["id"])
        scoped = [p for p in passages if p.get("group") == resolved_group]
        _add_dependency(dep_nodes, "scope", "scope_resolution", f"disambiguation resolved to group {resolved_group!r} via passage {matched['id']}", [matched["id"]])

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
    if "graph_expand" in stage_plan["stages"]:
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
                prev_hop_id = None
                for hop in expansion["path"]:
                    hop_id = f"entity:{entity_text}:{hop['hop']}:{hop['entity']}"
                    _add_dependency(dep_nodes, hop_id, "entity_link", f"hop {hop['hop']}: {hop['entity']}" + (f" via {hop['via']}" if hop["via"] else " (expansion root)"), [prev_hop_id] if prev_hop_id else [])
                    prev_hop_id = hop_id
                for p in new_passages:
                    _add_dependency(dep_nodes, p["id"], "graph_linked_evidence", f"reached via entity graph expansion from {entity_text!r}", [prev_hop_id] if prev_hop_id else [])
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
                cross_ref = answer_with_real_qa(ask, new_passages) if use_real_qa else answer_with_agreement(ask, new_passages, tau=0.1)
                cross_ref_text = next((p["text"] for p in new_passages if p["id"] == cross_ref.get("passage_id")), "")
                if cross_ref["span"] and quote_check(cross_ref["span"], cross_ref_text):
                    answer_parts.append(f"{cross_ref['span']} [{cross_ref['passage_id']}]")
                    citations.add(cross_ref["passage_id"])
                    trace.append({"step": "graph_expand_lookup", "entity": entity_text, "span": cross_ref["span"], "passage_id": cross_ref.get("passage_id")})
                    _add_dependency(dep_nodes, f"fact:graph_expand:{entity_text}", "derived_fact", f"{cross_ref['span']!r}", [cross_ref["passage_id"]])

    identity_signal = stage_plan["signals"]["identity"]
    trace.append({"step": "intent_signal", "signal": "identity", **identity_signal})
    if "identity_extraction" in stage_plan["stages"]:
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
            _add_dependency(dep_nodes, "fact:identity", "fact", f"name={facts['name']!r}, address={address}", [name_cite] if name_cite else [])

    total_signal = stage_plan["signals"]["total"]
    trace.append({"step": "intent_signal", "signal": "total", **total_signal})
    if "total_computation" in stage_plan["stages"]:
        spans, sources = [], []
        for p in scoped:
            # Follow-up (2026-11-10): a rule-shaped passage (verb or
            # threshold) is policy text, not a fact to sum -- its own
            # numbers (a threshold, a fee) are not another line item.
            # Found by direct testing: an ungrouped threshold rule sitting
            # alongside ungrouped fact passages (no disambiguation group
            # to filter it out, unlike every existing grouped fixture)
            # had its own $500/$50 counted into the total, inflating it.
            # Same exclusion _reason_once's own fact_passage lookup
            # already applies for the identical reason (line ~925 above).
            if parse_conditional_rule(p.get("text", "")) or parse_threshold_rule(p.get("text", "")):
                continue
            for found in AMOUNT_RE.findall(p["text"]):
                spans.append(found)
                sources.append(p["id"])
        money = sum_amounts(spans)
        facts["total"] = money["total"]
        citations.update(sources)
        trace.append({"step": "compute_total", "total": money["total"], "sources": sources})
        if money["ok"]:
            answer_parts.append(f"total {money['total']:,.0f} [{', '.join(sources)}]")
            _add_dependency(dep_nodes, "fact:total", "fact", f"total={money['total']}", sources)

    rule_hit = _find_rule(passages)
    if "rule_application" in stage_plan["stages"]:
        kind, rule, rule_passage = rule_hit
        trace.append({"step": "find_rule", "kind": kind, "rule": rule["raw"]})
        if kind == "threshold":
            if "total" not in facts:
                # FIX (audit 2026-11-03, Finding 2): this used to be the one
                # "rule present but doesn't apply" case with NO answer_parts
                # entry and no dependency node at all -- not even a rule
                # node -- while the role-mismatch and not-exceeded cases
                # below both explain themselves. Symmetric with those now.
                trace.append({"step": "apply_rule", "skipped": "no computed total to compare"})
                # Deliberately NOT added to answer_parts: that would change
                # `if not answer_parts:` control flow below (falling through
                # to lookup_fallback today) and so change decision/text for
                # any existing fixture that hits this path -- the audit's
                # own Finding 2 was about trace/dependency_tree
                # explainability, not about changing what gets answered.
                # Purely additive bookkeeping, same discipline as every
                # other dependency_tree node in this function.
                _add_dependency(dep_nodes, f"rule:{rule_passage['id']}", "rule", rule["raw"], [rule_passage["id"]])
                _add_dependency(dep_nodes, f"conclusion:{rule_passage['id']}:no_total", "conclusion", "policy could not be evaluated: no total computed", [f"rule:{rule_passage['id']}"])
            elif not _role_matches(rule, scoped):
                trace.append({"step": "apply_rule", "skipped": f"role mismatch with {rule['subject_placeholder']!r}"})
                answer_parts.append(f"policy does not apply (role mismatch with {rule['subject_placeholder']!r}) [{rule_passage['id']}]")
                # FIX (audit 2026-11-03, Finding 3): "conclusion" was reused
                # as a bare literal id across 6 call sites, relying on an
                # implicit (control-flow-proven, not code-enforced) mutual
                # exclusivity. Parameterized by rule/fact passage id + case
                # name so a future edit can't silently collide two live
                # conclusion nodes in the same dependency_tree.
                _add_dependency(dep_nodes, f"conclusion:{rule_passage['id']}:role_mismatch", "conclusion", f"role mismatch with {rule['subject_placeholder']!r}", [rule_passage["id"]])
            else:
                applied = apply_threshold_rule(rule, facts["total"])
                trace.append({"step": "apply_rule", "kind": "threshold", "result": applied})
                _add_dependency(dep_nodes, f"rule:{rule_passage['id']}", "rule", rule["raw"], [rule_passage["id"]])
                if applied["matched"]:
                    # Same gate check the verb-rule branch already has
                    # (EXP-089/026, now EXP-097 for temporal bounds) -- a
                    # threshold rule's own consequence can carry a
                    # trailing "unless"/"provided that"/"until" clause
                    # exactly like the verb-rule shape.
                    gate_context = [p["text"] for p in passages if p["id"] != rule_passage["id"]]
                    gate_result = _check_rule_gate(rule, gate_context)
                    trace.append({"step": "check_exception", "result": gate_result})
                    gate_node = f"gate:{rule_passage['id']}"
                    _add_dependency(dep_nodes, gate_node, "gate_check", f"{gate_result['kind']} gate status={gate_result['status']}", ["fact:total", f"rule:{rule_passage['id']}"])
                    if gate_result["status"] == "holds":
                        if gate_result["kind"] == "temporal":
                            reason_phrase = f"the rule's temporal bound ({gate_result['phrase']!r}) is not currently satisfied"
                        else:
                            reason_phrase = "the rule's exception holds" if gate_result["polarity"] == "negative" else "the rule's condition is not satisfied"
                        answer_parts.append(f"policy does not apply: {reason_phrase} ({rule['raw']!r}) [{rule_passage['id']}]")
                        _add_dependency(dep_nodes, f"conclusion:{rule_passage['id']}:blocked", "conclusion", f"policy blocked: {reason_phrase}", [gate_node])
                    else:
                        citations.add(rule_passage["id"])
                        conditional = gate_result["status"] == "unknown"
                        if conditional:
                            rule_conditional = True
                        unresolved_phrase = "the rule's temporal bound is unresolved" if gate_result["kind"] == "temporal" else ("the rule's exception is unresolved" if gate_result["polarity"] == "negative" else "the rule's condition is unresolved")
                        suffix = f" ({unresolved_phrase} -- not confirmed either way)" if conditional else ""
                        answer_parts.append(f"policy applies: {applied['consequence']}{suffix} [{rule_passage['id']}]")
                        _add_dependency(dep_nodes, f"conclusion:{rule_passage['id']}:applied", "conclusion", f"policy applies: {applied['consequence']}{suffix}", ["fact:total", f"rule:{rule_passage['id']}", gate_node])
                else:
                    answer_parts.append(f"policy does not apply (threshold not exceeded) [{rule_passage['id']}]")
                    _add_dependency(dep_nodes, f"conclusion:{rule_passage['id']}:not_exceeded", "conclusion", "threshold not exceeded", ["fact:total", f"rule:{rule_passage['id']}"])
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
                _add_dependency(dep_nodes, f"rule:{rule_passage['id']}", "rule", rule["raw"], [rule_passage["id"]])
                _add_dependency(dep_nodes, f"fact:{fact_passage['id']}", "fact", f"{fact['subject']} {fact['verb_lemma']} {fact.get('object')}", [fact_passage["id"]])
                if applied["matched"]:
                    # apply_rule's own lemma-match check has no idea the
                    # rule's consequence might carry a trailing exception/
                    # condition/temporal clause -- EXP-083/085 proved
                    # split_exceptions/check_exceptions standalone, but
                    # until this call existed, reason() itself never
                    # checked a matched rule's own gate at all (EXP-089).
                    # EXP-026 generalized the mechanism beyond "unless"-
                    # style negative exceptions to also recognize
                    # "provided that"-style positive conditions, and
                    # EXP-097 added a genuinely different gate kind
                    # (temporal bounds -- until/before/after/once answer
                    # a WHEN question, not a WHETHER question), both
                    # unified behind _check_rule_gate so this call site
                    # doesn't need to know which kind it got. Every OTHER
                    # given passage is the context a gate is checked
                    # against -- the same "exceptions are global policy
                    # text, not scoped to one story" principle _find_rule
                    # already applies when it scans every passage, not just
                    # `scoped`.
                    exception_context = [p["text"] for p in passages if p["id"] not in (rule_passage["id"], fact_passage["id"])]
                    gate_result = _check_rule_gate(rule, exception_context)
                    trace.append({"step": "check_exception", "result": gate_result})
                    gate_node = f"gate:{rule_passage['id']}"
                    _add_dependency(dep_nodes, gate_node, "gate_check", f"{gate_result['kind']} gate status={gate_result['status']}", [f"rule:{rule_passage['id']}", f"fact:{fact_passage['id']}"])
                    if gate_result["status"] == "holds":
                        if gate_result["kind"] == "temporal":
                            reason_phrase = f"the rule's temporal bound ({gate_result['phrase']!r}) is not currently satisfied"
                        else:
                            reason_phrase = "the rule's exception holds" if gate_result["polarity"] == "negative" else "the rule's condition is not satisfied"
                        answer_parts.append(f"policy does not apply: {reason_phrase} ({rule['raw']!r}) [{rule_passage['id']}]")
                        _add_dependency(dep_nodes, f"conclusion:{rule_passage['id']}:{fact_passage['id']}:blocked", "conclusion", f"policy blocked: {reason_phrase}", [gate_node])
                    else:
                        citations.update([rule_passage["id"], fact_passage["id"]])
                        conditional = gate_result["status"] == "unknown"
                        if conditional:
                            rule_conditional = True
                        unresolved_phrase = "the rule's temporal bound is unresolved" if gate_result["kind"] == "temporal" else ("the rule's exception is unresolved" if gate_result["polarity"] == "negative" else "the rule's condition is unresolved")
                        suffix = f" ({unresolved_phrase} -- not confirmed either way)" if conditional else ""
                        answer_parts.append(
                            f"{fact_passage['text']} [{fact_passage['id']}] matches the rule's trigger ({applied['trigger_lemma']}): "
                            f"{rule['raw']} [{rule_passage['id']}] Therefore, {applied['consequence']}{suffix}."
                        )
                        # Parameterized (Finding 3) AND the one site forward_chain's
                        # own raw_to_node_id lookup below resolves back to, by
                        # variable rather than by re-typing the literal (Finding 3's
                        # own recommendation: a future edit to this id can't
                        # silently desync from the lookup that depends on it).
                        primary_conclusion_id = f"conclusion:{rule_passage['id']}:{fact_passage['id']}:applied"
                        _add_dependency(dep_nodes, primary_conclusion_id, "conclusion", f"policy applies: {applied['consequence']}{suffix}", [f"rule:{rule_passage['id']}", f"fact:{fact_passage['id']}", gate_node])

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
                            primary_derived = instantiate_consequence(rule, fact)
                            primary_signatures = {(d["subject"], d["verb_lemma"], d.get("object")) for d in primary_derived}
                            seed_signature = (fact["subject"], fact["verb_lemma"], fact.get("object"))
                            verb_rule_pairs = _find_verb_rules_with_passages(passages)
                            chain_result = forward_chain([fact], [r for r, _ in verb_rule_pairs], context_texts=exception_context)
                            extra_facts = [
                                d
                                for d in chain_result["facts"]
                                if (d["subject"], d["verb_lemma"], d.get("object")) not in primary_signatures
                                and (d["subject"], d["verb_lemma"], d.get("object")) != seed_signature
                            ]
                            trace.append({"step": "forward_chain", "extra_facts": extra_facts})
                            # FIX (audit 2026-11-03, extraction-cluster Finding
                            # 3): every extra fact used to get a hardcoded
                            # depends_on=["conclusion"], the single node for
                            # the PRIMARY rule+fact's consequence -- correct
                            # for a step-1 fact (which really does derive from
                            # that consequence), but wrong for a step-2+ fact,
                            # which derives from a SPECIFIC earlier derived
                            # fact and a SECOND rule neither "conclusion" nor
                            # the old code ever cited. forward_chain's own
                            # derivation record (inference.py) already names
                            # the exact rule/fact raw text that produced each
                            # derived fact -- this builds a raw-text -> node-id
                            # lookup (seed fact, every verb rule passage, and
                            # every primary-step derived fact all resolve to
                            # the nodes already created for them) and resolves
                            # each extra fact's real dependencies against it,
                            # falling back to the old conclusion-only edge
                            # only if a raw text genuinely can't be resolved
                            # (should not happen for a well-formed chain).
                            raw_to_node_id = {fact["raw"]: f"fact:{fact_passage['id']}"}
                            for r, p in verb_rule_pairs:
                                raw_to_node_id[r["raw"]] = f"rule:{p['id']}"
                            for d in primary_derived:
                                raw_to_node_id[d["raw"]] = primary_conclusion_id
                            for i, extra in enumerate(extra_facts):
                                if extra.get("conditional"):
                                    rule_conditional = True
                                extra_suffix = " (unresolved -- not confirmed either way)" if extra.get("conditional") else ""
                                answer_parts.append(f"Furthermore, {extra['subject']} {extra['verb_lemma']} {extra['object']}{extra_suffix}")
                                derivation = extra.get("derivation") or {}
                                rule_node = raw_to_node_id.get(derivation.get("rule"), f"rule:{rule_passage['id']}")
                                antecedent_node = raw_to_node_id.get(derivation.get("fact"), primary_conclusion_id)
                                derived_node_id = f"derived:{i}:{extra['subject']}:{extra['verb_lemma']}"
                                _add_dependency(dep_nodes, derived_node_id, "derived_fact", f"{extra['subject']} {extra['verb_lemma']} {extra['object']}{extra_suffix}", [rule_node, antecedent_node])
                                raw_to_node_id[extra["raw"]] = derived_node_id

                else:
                    # FIX (audit 2026-11-03, Finding 2): the verb-rule branch
                    # used to have no else here at all -- a rule structurally
                    # present whose trigger doesn't match the fact's verb
                    # silently vanished (no trace entry, no answer_parts, no
                    # dependency node), while the threshold branch's
                    # equivalent ("threshold not exceeded") explicitly
                    # reports itself. Symmetric with that now.
                    # Same deliberate omission as the threshold branch's
                    # "no_total" case above: no answer_parts entry, so
                    # existing callers that rely on this falling through to
                    # lookup_fallback keep doing exactly that. Only the
                    # dependency_tree/trace gain a node explaining why
                    # rule_application contributed nothing here.
                    _add_dependency(dep_nodes, f"conclusion:{rule_passage['id']}:{fact_passage['id']}:not_matched", "conclusion", f"rule trigger ({applied['trigger_lemma']}) not matched by fact verb ({applied['fact_verb_lemma']})", [f"rule:{rule_passage['id']}", f"fact:{fact_passage['id']}"])
            else:
                # Same fix, the fact_passage == None case: a verb rule is
                # present but no passage's extracted fact could even be
                # compared against it -- the verb-branch analog of the
                # threshold branch's "no computed total to compare" case
                # above, now equally self-explaining.
                trace.append({"step": "apply_rule", "skipped": "no matching fact passage found", "kind": "verb"})
                _add_dependency(dep_nodes, f"rule:{rule_passage['id']}", "rule", rule["raw"], [rule_passage["id"]])
                _add_dependency(dep_nodes, f"conclusion:{rule_passage['id']}:no_fact", "conclusion", "policy could not be evaluated: no matching fact found", [f"rule:{rule_passage['id']}"])

    if not answer_parts:
        # Deliberately NOT gated by "lookup_fallback" in stage_plan["stages"]
        # (unlike every stage above) -- that membership only means "no
        # signal fired at PLANNING time", a narrower condition than this.
        # An informative stage can be planned and still produce nothing
        # (identity fires but no name is found; a rule is present but its
        # fact_passage never matches) -- something plan_stages cannot know
        # without actually running extraction, not just checking a signal.
        # This is the genuinely execution-time question "did everything we
        # attempted still come back empty", a strict superset of the
        # planning-time one, so it stays keyed off the real answer_parts
        # outcome rather than a plan membership check that could under-fire.
        qa = answer_with_real_qa(ask, scoped) if use_real_qa else answer_with_agreement(ask, scoped, tau=0.34)
        trace.append({"step": "lookup_fallback", "span": qa["span"], "passage_id": qa.get("passage_id")})
        if not qa["span"] or not quote_check(qa["span"], next((p["text"] for p in scoped if p["id"] == qa.get("passage_id")), "")):
            return _finish(ask, trace, "inconclusive", ABSTAIN_TEXT, citations, reason="no span found", dependency_tree=dep_nodes)
        citations.add(qa["passage_id"])
        _add_dependency(dep_nodes, f"conclusion:{qa['passage_id']}", "conclusion", f"{qa['span']!r}", [qa["passage_id"]])
        return _finish(ask, trace, "supported", f"{qa['span']} [{qa['passage_id']}]", citations, facts=facts, dependency_tree=dep_nodes)

    final_decision = "supported_with_flags" if rule_conditional else "supported"
    return _finish(ask, trace, final_decision, ". ".join(answer_parts) + ".", citations, facts=facts, dependency_tree=dep_nodes)


def _finish(ask, trace, decision, text, citations, facts=None, reason=None, dependency_tree=None) -> dict:
    result = {
        "ask": ask,
        "decision": decision,
        "text": text,
        "citations": sorted(citations),
        "facts": facts or {},
        "trace": trace,
        "dependency_tree": dependency_tree or [],
    }
    if reason:
        result["abstain_reason"] = reason
    return result
