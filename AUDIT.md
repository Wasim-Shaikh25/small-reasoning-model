# Reasoning-layer audit

Started 2026-11-03, at the project owner's request: a full, deterministic,
line-by-line review of every module `lab/common/brain.py` depends on (and
every module in `lab/common/` that doesn't, to check it isn't a stray
duplicate of something live), looking specifically for:

1. **Overlap** -- two modules independently implementing the same decision
   (e.g. two NER paths, two entity-graph classes, two threshold constants
   for "is this match confident") that can silently drift apart.
2. **Conflict** -- two modules that *would* disagree on the same input if
   both were asked, or a module whose assumptions contradict another's.
3. **Dead/orphaned code** -- not reachable from `brain.reason()` at all,
   so it can't be part of "the brain" even if it still runs standalone.
4. **Determinism/FORBIDDEN.md discipline** -- nothing outside the one
   bounded rewriter exception making a generative, non-reproducible call.

This file is append-only in spirit (like the project's own findings
register convention) -- sections get added/filled in, not rewritten away,
as the audit proceeds across however many passes it takes. Each finding
cites exact file + line range.

## Fix status (2026-11-03, same-day follow-up, commit `01fd4d6`)

The project owner asked to fix all of the findings below. What actually
happened, so this stays honest about what's done vs. still open:

**Fixed and verified (full regression rerun, byte-identical except
EXP-045's own timing fields, which vary with machine load by design):**
- Finding 1 (brain.py): `plan_stages()`/execution conflict -- now gated
  on `rule_hit[0] == "verb"` too.
- Extraction-cluster Finding 3: forward-chained `dependency_tree` edges
  beyond step 1 now cite the real second rule, via
  `_find_verb_rules_with_passages` + a raw-text-to-node-id lookup.
- `engine.py` documented as explicitly historical/frozen; `brain.
  reason()` stated as canonical, cross-referenced both ways. **Not**
  done: porting its multi-round retrieve-budget capability into
  `brain.reason()`, or deleting/retiring it -- left as the project
  owner's own call, per the two options this file's Top Finding #2
  originally offered.
- `real_entities`/`ner_pipeline` naming collision: collision warnings
  added to both `real_entities` functions; `ner_pipeline` renamed to
  `parser_pipeline` (old name kept as a compatibility alias).
- `chunk_document` naming collision: cross-reference warnings added to
  both `ingest.py` and `chunking.py`.
- No model-version guard on calibrated thresholds: warning comments
  added to `intent_signals.py`'s four bge thresholds and
  `semantic_index.py`'s margin constants (not an automated check --
  there still isn't a runtime assertion tying a threshold to a model
  version, only a comment telling a future editor to re-measure).
- `Index`/`RealIndex`/`RealBgeIndex` DRY violation: `_minmax`/
  `_filters_ok` consolidated into `index.py`'s one copy.
- `textutil.MODAL_RE` vs. `connectives.py` disagreement: "unless"/
  "except" removed from `MODAL_RE` (both are unambiguous bare-word
  `CONDITION_NEGATIVE` entries in `CONNECTIVE_TABLE`); "only"/"provided"
  deliberately left alone (their bare-word classification is more
  ambiguous and wasn't the audit's own confirmed example).
- Real QA/NLI/rewriter-repair measured-but-unwired gap: added
  `reason(use_real_qa=True, use_real_nli=True, use_repair=True)` --
  all three opt-in, default False, verified by direct test to actually
  route through the real checkpoints/repair mechanisms when enabled,
  and verified by full regression rerun to change nothing when left at
  their default.

**Still open (project owner's call, not attempted this pass):**
- Whether to port `engine.py`'s retrieve-budget loop into
  `brain.reason()` and retire `engine.py`, or just leave it frozen as
  now documented.
- Whether `use_real_qa`/`use_real_nli`/`use_repair` should ever become
  the DEFAULT rather than opt-in -- doing that would change many
  closed explorations' own "live-equivalent" status and was
  deliberately not done without an explicit decision to do so.
- The five finished-but-never-wired-in capabilities (`deontic.py`,
  `coherence.py`, `word_relevance.py`, `memory.py`, `proposals.py`) --
  each needs its own design decision about where/how it would surface
  in `reason()`'s output; none was wired in during this pass.
- `entities.py`'s silent-miss diagnostic gap (no specific
  `abstain_reason` when a bare single name defeats the rule-based
  tagger) -- not fixed, still produces a generic abstain reason.
- The `dateparser`/event-relative-clause misroute risk in
  `temporal.check_temporal_bound` -- flagged, not fixed, no reproducing
  fixture built.
- The asymmetric "rule present but doesn't apply" reporting (Finding 2)
  and the fragile shared `"conclusion"` node id (Finding 3) from the
  original brain.py read -- flagged, not fixed.

## Second follow-up (2026-11-03, same day): Finding 2/3 fixed, engine.py ported and deleted

The project owner asked, directly: why weren't Finding 2/3 fixed when
everything else was, and if `engine.py` isn't needed and brain.reason()
covers everything, delete it. Both done this pass, verified by a full
regression rerun of every exploration that imports `lab.common.brain`
(25 explorations) plus direct smoke tests of the two new capabilities
below -- byte-identical at defaults.

**Finding 2 (asymmetric non-match reporting) -- fixed, bookkeeping only.**
The three previously-silent "rule present but doesn't apply" cases
(threshold: no computed total; verb: trigger doesn't match the fact;
verb: no fact passage found at all) now each add a `rule` dependency
node and an explanatory `conclusion:...` node to `dependency_tree`/
`trace`. Deliberately did **not** add matching `answer_parts` text --
that would flip `if not answer_parts:` and change `decision`/`text` for
any existing fixture landing in one of these cases (falling through to
`lookup_fallback` today; would stop falling through if these cases
suddenly produced their own answer text). The audit's own Finding 2 was
about `trace`/`dependency_tree` explainability, not about the answer
itself, so the fix stays scoped to exactly that -- purely additive, same
discipline every other `dependency_tree` node in this function follows.

**Finding 3 (fragile `"conclusion"` node id) -- fixed.** Every one of the
now-9 call sites that add a `kind: "conclusion"` node gets a unique,
parameterized `id` (e.g. `conclusion:{rule_passage_id}:{fact_passage_id}:applied`,
`...{}_not_matched`, `...{}_no_total`, `...{}_no_fact`, `...{}_blocked`,
`...{}_role_mismatch`, `...{}_not_exceeded`, plus lookup_fallback's own
`conclusion:{passage_id}`) instead of the bare literal `"conclusion"`.
`forward_chain`'s own `raw_to_node_id` lookup and its `antecedent_node`
fallback now reference the live `primary_conclusion_id` variable rather
than re-typing the string, so the two can't silently desync. `kind`
stays the literal `"conclusion"` on every one of them, so a reader
filtering by kind still finds "the" conclusion node(s); only `id`
uniqueness changed.

**Top Finding #2 (`engine.py`) -- resolved: ported, then deleted.**
`lab.common.engine.run_task`'s two capabilities genuinely absent from
`brain.reason()` are now ported into `reason()` itself, both opt-in,
both default to today's exact single-pass behavior:
- `retrieve_budget` (default `1`): when a `connector` is given and the
  first pass abstains (`"inconclusive"`/`"ungrounded"`), retries up to
  `retrieve_budget` rounds, doubling `connector_top_k` each round.
  Smoke-tested directly: a fake connector that only surfaces the right
  passage once `top_k` is large enough resolves on retry with
  `retrieve_budget=3` where `retrieve_budget=1` (the default) abstains.
- `check_contradiction` (default `False`): after a pass that would
  return `"supported"`/`"supported_with_flags"`, answers `ask` against
  every passage independently (same QA primitives `reason()` already
  uses) and checks every pair of resulting spans for contradiction --
  `engine.judge_question`/`verify.conflict_across`'s own mechanism,
  reimplemented inline (not calling `conflict_across` directly) only so
  `use_real_nli=True` can swap the classical `nli.judge` comparison for
  the real checkpoint (`real_encoders.real_nli`). A genuine conflict
  downgrades `decision` to a new `"contradicted"` value (only ever
  reachable with this flag set) and adds a `contradiction_flag`
  dependency_tree node per conflicting pair. Smoke-tested directly: two
  passages giving conflicting amounts for the same total, which
  `reason()` at defaults nonsensically **sums** into one wrong total
  (`"total 1,400"`), correctly comes back `"contradicted"` with
  `check_contradiction=True` instead -- the clearest concrete case this
  capability actually earns its keep, not just closes an audit note.

`lab.common.engine.py` was then **deleted** (not just documented as
frozen). Its only live importers were the 6 closed explorations the
original audit already identified (EXP-001/020/021/027/044/045) -- none
of the 25 explorations that exercise `brain.reason()` ever imported it.
Each of those 6 scripts' own docstrings now carries a short RETIRED note
explaining the deletion; their `results.json` stays as the permanent
historical record, but literally re-running any of those 6 scripts will
now `ImportError` -- recoverable only via `git show <commit before this
deletion>:lab/common/engine.py` if ever genuinely needed again. This is
a real, accepted tradeoff (the project owner's own explicit call, not a
default), not an oversight.

**Still open, unaffected by this pass:** the five finished-but-never-
wired-in capabilities, `entities.py`'s silent-miss diagnostic gap, the
`dateparser` misroute risk, and whether `use_real_qa`/`use_real_nli`/
`use_repair` should ever default on.

## How "coverage" is counted

`lab/common/` is 59 files, ~8,570 lines. Coverage below is tracked per
file: `not started` / `in progress` / `done`. A file is `done` only once
every line has actually been read in this audit pass (not skimmed from
memory of earlier sessions) and cross-checked against every other module
that overlaps with it.

## Module reachability from `brain.reason()` (computed 2026-11-03)

Transitive closure of `from lab.common.X import ...` starting at `brain`:

**Reachable (36 modules -- these ARE "the brain"):**
ask, assemble, calc, connectives, connectors, doc_tools, document_writer,
docx_writer, entities, graph_index, index, inference, ingest,
intent_signals, longform, nested_index, nli, open_domain, prompt_contract,
qa, real_encoders, real_models, real_ner, real_rewriter,
real_rewriter_legal_gemma, real_rewriter_ollama, real_rewriter_qwen,
relevance, rewriter_backends, rules, semantic_index, template_rewriter,
temporal, textutil, verify, working_memory

**NOT reachable from brain.reason() (20 modules -- standalone/exploration-only, or orphaned):**
budget, chunking, coherence, deontic, engine, graph, harness,
lora_finetune, memory, paged, proposals, provenance, real_bge_index,
real_corpus, real_index, real_squad, schemas, store, synthetic_fusion_data,
word_relevance

Notable from this list alone (full detail below as each is audited):
- `store.py` and `real_bge_index.py` (added 2026-11-01, this session) are
  genuinely standalone by design -- a caller builds/loads a `Store` and
  feeds its `.search()` results into `reason()`'s `passages` argument
  itself; `reason()` never calls into `store.py` directly. Already
  documented as a known gap in memory (`project_connectors_and_store.md`).
- `graph.py` (a simple class-based `EntityGraph`) is NOT used by the live
  path -- `graph_index.py` (functional, with hop-expansion and
  save/load) is what `brain.py` actually imports. Needs checking: is
  `graph.py` dead code entirely, or still used by some exploration
  script directly? (see Retrieval cluster findings below)
- `qa.py` IS reachable (via `entities.py` and directly via `brain.py`'s
  `answer_with_agreement`) -- so the "classical lexical QA" substitute
  and the "real DeBERTa QA" path (`real_encoders.real_qa`) coexist. Is
  `real_qa` actually called anywhere in the live `reason()` path, or
  only from standalone EXP-030-style explorations? Needs checking.
- `real_models.py` is reachable via `rules.py` AND `real_index.py`
  (itself unreachable) -- so `rules.py`, which is live, still depends on
  the OLD spaCy-substitute infrastructure, not `real_encoders.py`'s real
  checkpoints, for whatever it imports from `real_models`. Needs
  checking exactly what and whether that's stale.

## File-by-file status

| File | Lines | Reachable | Status |
|---|---|---|---|
| brain.py | 793 | - (root) | **done -- 3 findings (plan/exec conflict, non-match asymmetry, conclusion-id fragility)** |
| ask.py | 176 | yes | **done (verification cluster)** |
| assemble.py | 184 | yes | **done (document-gen cluster)** |
| budget.py | 24 | no | **done (misc cluster)** |
| calc.py | 85 | yes | **done (extraction cluster)** |
| chunking.py | 152 | no | **done (document-gen cluster) -- name collision w/ ingest.chunk_document** |
| coherence.py | 72 | no | **done (verification cluster) -- built, unused** |
| connectives.py | 306 | yes | **done (extraction cluster) -- MODAL_RE disagreement found** |
| connectors.py | 197 | yes | **done (retrieval cluster)** |
| deontic.py | 62 | no | **done (extraction cluster) -- built, unused** |
| doc_tools.py | 157 | yes | **done (document-gen cluster)** |
| document_writer.py | 86 | yes | **done (document-gen cluster)** |
| docx_writer.py | 71 | yes | **done (document-gen cluster)** |
| engine.py | 283 | no | **done (misc cluster) -- LIVE PARALLEL BRAIN, see top finding #2** |
| entities.py | 507 | yes | **done (extraction cluster) -- silent-miss diagnostic gap found** |
| graph.py | 35 | no | **done (retrieval cluster) -- pinned by EXP-004, correctly kept** |
| graph_index.py | 128 | yes | **done (retrieval cluster)** |
| harness.py | 119 | no | **done (misc cluster) -- pure infra, confirmed safe** |
| index.py | 202 | yes | **done (retrieval cluster) -- DRY dup w/ real_index/real_bge_index** |
| inference.py | 429 | yes | **done (extraction cluster) -- forward_chain provenance finding** |
| ingest.py | 96 | yes | **done (document-gen cluster)** |
| intent_signals.py | 178 | yes | **done (verification cluster) -- no model-version guard** |
| longform.py | 255 | yes | **done (document-gen cluster)** |
| lora_finetune.py | 115 | no | **done (misc cluster) -- training-time only, correct** |
| memory.py | 126 | no | **done (misc cluster) -- measured-not-wired-in (persistent recall)** |
| nested_index.py | 155 | yes | **done (retrieval cluster)** |
| nli.py | 62 | yes | **done (verification cluster) -- classical, live via fidelity_gate** |
| open_domain.py | 60 | yes | **done (verification cluster) -- FORBIDDEN.md exception confirmed safe** |
| paged.py | 69 | no | **done (retrieval cluster) -- zero callers found anywhere, orphaned prototype** |
| prompt_contract.py | 44 | yes | **done (verification cluster)** |
| proposals.py | 66 | no | **done (misc cluster) -- measured-not-wired-in** |
| provenance.py | 44 | no | **done (misc cluster) -- see top finding, redundant-by-divergent-design w/ dependency_tree** |
| qa.py | 153 | yes | **done (verification cluster) -- real_qa never called live** |
| real_bge_index.py | 104 | no | **done (retrieval cluster)** |
| real_corpus.py | 107 | no | **done (misc cluster) -- data fetcher, not a model** |
| real_encoders.py | 176 | yes | **done (verification cluster)** |
| real_index.py | 85 | no | **done (retrieval cluster) -- pinned by EXP-029/032/045, correctly kept** |
| real_models.py | 82 | yes | **done (extraction + verification clusters) -- real_entities name collision** |
| real_ner.py | 48 | yes | **done (verification cluster) -- opt-in only, default off** |
| real_rewriter.py | 214 | yes | **done (document-gen cluster) -- retry path bypassed live** |
| real_rewriter_legal_gemma.py | 75 | yes | **done (document-gen cluster)** |
| real_rewriter_ollama.py | 241 | yes | **done (document-gen cluster) -- citation-splice repair bypassed live** |
| real_rewriter_qwen.py | 66 | yes | **done (document-gen cluster)** |
| real_squad.py | 95 | no | **done (misc cluster) -- data fetcher, not a model** |
| relevance.py | 37 | yes | **done (verification cluster)** |
| rewriter_backends.py | 107 | yes | **done (document-gen cluster) -- bypasses all backend repair logic** |
| rules.py | 317 | yes | **done (extraction cluster)** |
| schemas.py | 84 | no | **done (misc cluster) -- validate_note fully dead code** |
| semantic_index.py | 292 | yes | **done (retrieval cluster)** |
| store.py | 166 | no | **done (retrieval cluster)** |
| synthetic_fusion_data.py | 148 | no | **done (misc cluster) -- training-time only, correct** |
| template_rewriter.py | 78 | yes | **done (document-gen cluster) -- dead relative to live call path** |
| temporal.py | 103 | yes | **done (extraction cluster) -- dateparser misroute risk flagged** |
| textutil.py | 113 | yes | **done (extraction cluster) -- MODAL_RE disagreement found** |
| verify.py | 154 | yes | **done (verification cluster)** |
| word_relevance.py | 72 | no | **done (main session) -- built, unused** |
| working_memory.py | 114 | yes | **done (document-gen cluster) -- dependency_tree() verified safe** |

**Progress: 57 / 57 files done, 8,569 / 8,569 lines read line-by-line (100% coverage of lab/common/, excluding the trivial 1-line __init__.py). First full pass complete 2026-11-03. See "Summary for the project owner" at the end of this file for the verdict and recommended next actions -- this audit stays open (append-only) for any follow-up fixes/decisions, per the project owner's own instruction to keep extending it rather than treating it as a one-shot report.**
(The reachability map above and the module list itself IS the first real
output of this audit -- it already answers "does anything obviously
duplicate anything else" at the module-graph level, ahead of the
line-by-line pass.)

## Findings

### brain.py (793 lines) -- read in full, line by line, 2026-11-03

**FINDING 1 (CONFLICT, confirmed, highest priority): `plan_stages()` can predict `rule_application_method == "forward_chain"` for a call that will actually execute the THRESHOLD branch, which never does forward chaining -- directly contradicting this module's own documented invariant.**

`plan_stages()` (brain.py:140-211) computes `rule_application_method` from only two things (line 202):
```python
rule_application_method = "forward_chain" if (rule_signal["fires"] and len(verb_rules) > 1) else "single_step"
```
`verb_rules` (`_find_verb_rules`, line 113) scans **every** passage for verb-conditional rules, independent of what `rule_hit` (`_find_rule`, line 98) actually returned. `_find_rule` returns the **first** passage (in list order) that matches either a verb-conditional or threshold shape -- verb shape checked first per-passage, but passage order decides which rule is "the" rule_hit, not ask relevance.

Concrete failure scenario: `passages = [threshold_passage, verb_rule_1, verb_rule_2]`, ask contains rule-application language (`wants_rule_application` fires).
- `_find_rule(passages)` checks `threshold_passage` first: not verb-shaped, is threshold-shaped -> returns `("threshold", rule, threshold_passage)` immediately, **never examining `verb_rule_1`/`verb_rule_2`**.
- `_find_verb_rules(passages)` separately scans all three passages and finds `verb_rule_1` and `verb_rule_2` -> `len(verb_rules) == 2`.
- `rule_signal["fires"]` is True -> `rule_application_method = "forward_chain"` (line 202), because the condition checks `len(verb_rules) > 1` with **no check that `rule_hit`'s own kind is "verb"**.
- `stage_plan["rule_application_method"]` is now `"forward_chain"`, visible in `trace`'s `"plan"` entry.
- In `reason()` (line 617 on): `kind, rule, rule_passage = rule_hit` -> `kind == "threshold"` -> the `if kind == "threshold":` branch (line 620) runs. **This branch never reads `stage_plan["rule_application_method"]` at all** -- only the verb branch (line 726) checks `if stage_plan["rule_application_method"] == "forward_chain":`. The two verb rules are never applied, never chained, despite the plan explicitly saying forward-chaining would happen.

This contradicts the module's own docstring (lines 151-155): *"This computes the SAME signals reason() itself checks ... so the plan accurately predicts what reason() is actually about to do -- not a second, independent guess that could disagree with the real execution."* It can disagree, in exactly this (admittedly narrow) case: a passage set containing both rule kinds, where a threshold rule happens to sort before any verb rule.

Not yet reproduced with a live regression script (would need a hand-built fixture with one threshold rule + 2 verb rules + an ask that fires `wants_rule_application`) -- recommend building a small one-off script to confirm empirically before deciding whether to fix (e.g. by also gating `forward_chain` method selection on `rule_hit[0] == "verb"`) or just documenting it as a known narrow limitation.

**FINDING 2 (inconsistency, confirmed): three different "rule matched structurally but doesn't apply" cases get three different treatments.**
- Threshold rule, no computed total (line 621-622): `trace.append({"skipped": "no computed total to compare"})` -- **no `answer_parts` entry, no dependency node, not even a rule node.**
- Threshold rule, role mismatch (line 623-626): explicit `answer_parts.append("policy does not apply (role mismatch...)")` **and** a `_add_dependency(..., "conclusion", ...)` node.
- Threshold rule, applied but threshold not exceeded (line 658-660): explicit `answer_parts.append("policy does not apply (threshold not exceeded)")` **and** a conclusion dependency node.
- Verb rule, `apply_rule` found no lemma match (`applied["matched"]` is False, after line 681): **there is no `else` branch at all** for this case (confirmed by reading lines 675-724 in full -- the `if applied["matched"]:` block runs from 681 to 724 with nothing following it before the function moves to `if not answer_parts:` fallback at line 757). No trace entry, no answer text, no dependency node -- this case is silently indistinguishable from "no rule was found at all" by the time `reason()` falls through to `lookup_fallback`.

Net effect: a verb-trigger rule that's present but doesn't match its fact silently vanishes, while the equivalent threshold case explicitly reports "threshold not exceeded." Not a correctness bug in the sense of a wrong *answer* (lookup_fallback still runs and may find something reasonable), but it is a real asymmetry in how much the `trace`/`dependency_tree` explain *why* rule_application contributed nothing -- directly relevant to the user's "work in sync, explain what depends on what" ask.

**FINDING 3 (fragility, not currently a bug): the literal string `"conclusion"` is reused as a dependency-tree node id across 6 different call sites** (lines 626, 648, 657, 660, 712, 724, 774) with no uniqueness guard (`_add_dependency`'s own docstring says "no dedup, is deliberate"). Verified by hand that every pair of these 6 sites is mutually exclusive within a single `reason()` call (each sits in a different branch of an if/elif/else chain, or behind `if not answer_parts:` which only runs when none of the others did) -- so today, at most one `"conclusion"` node is ever added per call. But this safety property is *implicit* (proven by this audit reading the control flow, not by any code-level guard), and a future edit to any one of these branches could silently violate it -- e.g. a future refactor that gives the verb-branch's `applied["matched"] == False` case a conclusion node (closing Finding 2) could, if careless, add a 7th `"conclusion"`-id site that is NOT provably exclusive with an existing one. Recommendation for whoever closes Finding 2: parameterize the id (e.g. `f"conclusion:{rule_passage['id']}"`) rather than reusing the bare literal.

**No other overlap/conflict found in brain.py itself** on this full read -- `plan_stages()`'s other three stage picks (document/hierarchical-vs-disambiguate/graph_expand/identity/total) all gate correctly off data computed identically in both `plan_stages` and `reason()` (same function calls, same arguments), and I did not find a second case of plan/execution disagreement beyond Finding 1.

### Cluster audits (retrieval, extraction, verification, document-generation, misc)

5 parallel sub-audits launched 2026-11-03, each covering one cluster of the remaining 58 files with explicit file:line citations. 4 of 5 reported back; merged below. The 5th (misc/orphaned: budget, engine, harness, lora_finetune, memory, proposals, provenance, real_corpus, real_squad, schemas, synthetic_fusion_data) is still running.

### TOP CROSS-CLUSTER FINDING: the project has repeatedly measured real-model capability that the live `brain.reason()` path does not actually use

This is the single most important pattern across all four completed clusters, confirmed independently by two different sub-audits (verification cluster's Q1, document-generation cluster's Headline Finding) and corroborated by a third (extraction cluster's real_ner findings):

1. **QA: the real DeBERTa-v3-squad2 checkpoint (`real_encoders.real_qa`) is NEVER called by `brain.reason()`.** Every live lookup (`lookup_fallback`, `graph_expand_lookup`) uses the classical lexical extractor `qa.answer_with_agreement` exclusively. `real_qa` only runs from standalone EXP-030/EXP-080 scripts. The real QA capability measured repeatedly across many explorations is not what answers a live question today.
2. **NLI is split by role, inconsistently.** The rule exception/condition/temporal gate (`brain._check_rule_gate` -> `inference.check_exception`) DOES call the real DeBERTa-v3 MNLI model (`real_encoders.real_nli`) live, every time a rule fires. But the rewriter's own fidelity check (`real_rewriter.fidelity_gate` -> `verify.bidirectional_nli` -> `nli.judge`) uses the classical substitute, every time, even though `real_encoders.real_bidirectional_nli` (the real-model equivalent, built specifically to parallel `verify.bidirectional_nli`) exists and has **zero callers anywhere in the repo**. Two pieces of the same `reason()` call are held to measurably different evidentiary standards.
3. **NER is opt-in and defaults off.** `real_ner.py`'s real dslim/bert-base-NER checkpoint only runs when a caller explicitly passes `use_real_ner=True`; every existing caller of `reason()` defaults to `False`, so the live default path uses `entities.py`'s rule/regex tagger.
4. **Generation repair mechanisms are bypassed.** `rewriter_backends.rewrite_unit` (the only rewriter entry point `longform.write_long_document` calls) does one raw `generate()` call per backend and falls back on fidelity failure -- it never calls any backend's own retry-with-feedback (`real_rewriter.rewrite_unit`) or citation-splice repair (`real_rewriter_ollama`'s `_splice_missing_citations`, measured recovering 11/13 otherwise-failed rewrites in EXP-063). All of that repair logic sits in each backend's own module, unreachable from the dispatcher that generalized across them.

None of these four are "wrong answer" bugs -- the fidelity/quote-check gates are uniformly applied regardless, so nothing ungrounded gets through. But together they describe a real, previously-undocumented shape: **this project's explorations (EXP-029 through EXP-080+) have repeatedly measured what the real models/repair mechanisms can do, and the live brain uses the weaker alternative in every one of these four cases**, with no comment anywhere in `brain.py`/`longform.py`/`rewriter_backends.py` acknowledging the gap. This is exactly the kind of "layers added over many explorations, do they still work in sync" question the project owner asked the audit to answer -- and the answer, for these four capabilities, is "the newer, stronger layer was built and measured but never actually connected."

### TOP CROSS-CLUSTER FINDING #2: `lab/common/engine.py` is a complete, live, undocumented SECOND "brain" -- not dead code

The misc-cluster audit disproved the working assumption (made in good faith by the verification cluster, based only on brain-reachability) that `engine.py` was simply dead. It is not: `engine.run_task(ask, passages, depth_cap=None, tau=None)` is a complete, independently-capable, alternative answer-from-passages controller, still actively exercised by exploration scripts as recently as **EXP-044/045 -- work done two days before this audit, in this same session's earlier RERUN_TODOS batch.**

What it has that `brain.reason()` does NOT:
- A genuine **multi-round retrieve-more-with-budget loop** (`state["rounds"]`/`max_rounds`, re-querying `index.search`+rerank each round when the first pass is insufficient) -- `brain.reason()` is single-pass retrieval only, it never re-queries.
- A **different decision vocabulary**: `{"supported", "contradicted", "inconclusive"}` vs. `reason()`'s `{"supported", "supported_with_flags", "inconclusive", "ungrounded"}`. `engine.py` has an explicit top-level `"contradicted"` outcome (via `conflict_across`'s cross-passage NLI contradiction check) that `reason()` has no equivalent return value for -- `reason()`'s rule-gate conflicts get folded into prose answer text, never surfaced as a distinct decision label.
- Its own schema-validated judgment payload (`schemas.validate_judgment`) and its own abstain-on-malformed-judgment path.

No document anywhere in the repo (`EXPLORATIONS.md`, `FORBIDDEN.md`, `engine.py`'s own docstring) ever states engine.py is deprecated, superseded, or should stop being used. The closest statement is EXP-060's own goal text framing `brain.reason` as "a single unified controller" -- which asserts brain.py's own design intent, but never retires the alternative. **This means the project currently has two live, independently-exercised "answer a question" entry points with genuinely different capabilities and decision vocabularies, and nothing in the codebase says which one is canonical for new work.** This is the single biggest risk this audit found to the user's stated goal ("they all should work in sync like a real brain") -- not because the two disagree on any single measured case, but because nothing stops a future exploration or caller from picking either one and further diverging.

**Recommendation (project owner's call, not applied by this audit):** either (a) formally document `engine.py` as a frozen, pre-EXP-060 historical alternative (not deleted -- it's still referenced in 6 closed explorations' own reproducibility manifests), explicitly stating `brain.reason()` is canonical for all new work, or (b) port `engine.py`'s one genuinely-missing capability (the multi-round retrieve-more budget loop) into `brain.reason()` and then retire `engine.py` for good.

### Cluster: Retrieval & Navigation (10 files, ~1,400 lines -- full report in commit history / scratch)

All resolved as either no-bug or low-severity:
- `Index`/`SemanticIndex` genuinely are two independent signals (TF-IDF cosine vs. real bge cosine) in the live disambiguate branch -- not a hidden wrap. `RealBgeIndex` exists only to give `store.py` a persistable BM25+bge bundle; not a missing wiring.
- Hierarchical `navigate_dual` correctly lacks EXP-069's `_group_margin` fix because its one-candidate-per-branch shape structurally can't hit that bug.
- All margin/floor constants (`MIN_DENSE_SCORE`, `MIN_SEMANTIC_MARGIN`, `MIN_LEXICAL_MARGIN`, `SEMANTIC_SINGLE_FLOOR`) have exactly one definition each, imported everywhere, never redefined.
- `graph.py`/`real_index.py` are NOT accidental dead duplicates of `graph_index.py`/`SemanticIndex` -- each is pinned in a closed exploration's own reproducibility manifest (EXP-004; EXP-029/032/045) and correctly superseded-but-kept, same pattern used elsewhere in this repo.
- **Real but low-risk:** `Index`, `RealIndex`, `RealBgeIndex` each reimplement the identical `_minmax`/`_filters_ok`/0.5-0.5-blend helper code nearly verbatim (DRY violation, not a behavioral conflict).
- **Minor, undocumented:** a `Store` instance passed by mistake as `connector=` to `brain.reason` would silently "work" via duck-typing (harmless today, coincidental, untested).
- `paged.py`'s `Notebook`/`WorkingSet` (NOT reachable) looks like an earlier prototype of `working_memory.py`'s bounded-working-set idea -- flagged for the misc-cluster fork; zero callers found anywhere by this fork's own grep.

### Cluster: Extraction & Rule-Application (9 files read fully + real_models.py, ~2,083+82 lines)

- `rules.py`'s import of `real_models.ner_pipeline` is a genuine, non-stale dependency -- it's used purely as a generic spaCy dependency-parser object (`.pos_`/`.dep_`), never for NER, despite the misleading name. Not swappable to `real_encoders` (no equivalent generic-parser function exists there).
- **Naming collision, confirmed real risk:** `real_models.real_entities` (spaCy OntoNotes NER) and `real_encoders.real_entities` (dslim/bert-base-NER) are two different functions with the identical name, in two different modules, both technically reachable from brain.py's dependency graph. Only the second is ever actually called live. No live bug today, but a future `from lab.common.real_models import real_entities` typo-import would silently swap in the weaker model with no error.
- `detect_primary`'s rule-based person tagger requires 2+ consecutive Title-Case words (`FULL_PERSON` regex) or an honorific+name or an initial+name -- a bare single first name never matches, confirmed exactly from the regex itself. When this causes `graph_expand`/`identity_extraction` to find nothing, brain.py records no specific `abstain_reason` for it (unlike every other abstain path, which does carry a specific reason) -- a diagnostic-transparency gap, not a wrong-answer bug.
- **Confirmed bug in this session's own new dependency_tree feature:** `forward_chain`'s derived facts beyond the first step always get `depends_on: ["conclusion"]` in brain.py's tree, hardcoded to the single primary-conclusion node -- omitting the actual SECOND rule (and the intermediate derived fact) that really produced a 2nd-step derivation. `inference.py`'s own `forward_chain` already tracks exact per-fact provenance (`derived_fact["derivation"] = {"rule": ..., "fact": ...}`, inference.py:423) -- brain.py simply doesn't surface it. Root cause: `_find_verb_rules` discards passage identity entirely (its returned rule dicts carry no passage-id field), so even if brain.py wanted to cite the real second rule's passage, it currently has no way to. Concrete counterexample built from this session's own EXP-084 fixture (Rohan/kill/jail/license-suspension, two rules) -- see commit history for the full derivation.
- Condition-exception gates vs. temporal-bound gates are confirmed mutually exclusive by construction (disjoint connective-word sets in `connectives.CONNECTIVE_TABLE`) -- `_check_rule_gate`'s "exception first" ordering is a deliberate, safe precedence rule, not a coin-flip. Untested by any existing fixture for the case where both appear in one consequence, but not broken.
- **Real, separate risk found in passing:** `check_temporal_bound` decides absolute-date-vs-event-relative routing by running `dateparser.parse(..., STRICT_PARSING=False)` over the entire bound-clause text; a number-containing event-relative clause could plausibly be misparsed as a date, silently routing to the wrong (overconfident) path. Not reproduced on any existing fixture; recommend a targeted regression case.
- **Confirmed two-modules-disagree finding:** `textutil.MODAL_RE` (`r"\b(not|no|shall|may|must|unless|except|only|provided)\b"`) conflates true deontic modals (shall/may/must) with condition/exception connectives (unless/except/provided) that `connectives.py` -- the module built specifically to replace ad-hoc keyword regexes for exactly these words -- classifies as a completely different category (`Operator.CONDITION_NEGATIVE`/`POSITIVE`). Concrete failure: rewriting "unless the tenant pays" to "except the tenant pays" (a paraphrase `connectives.py` itself would call logically identical, same `Operator`) makes `verify.py`'s `modals()`-based fidelity check see `{'unless'}` vs `{'except'}` and flag a mismatch. Bounded impact (only ever causes an over-cautious rewriter fallback, never a wrong final answer), but a real instance of exactly the "silently drifting duplicate logic" this audit was asked to find.
- `deontic.py` (EXP-087, 62 lines) is fully built, working, and self-contained, but not wired into `brain.reason()` -- a natural fit for distinguishing obligation/permission/prohibition in a rule's reported consequence, never connected.

### Cluster: Verification & Intent-Signal Detection (12 files, incl. real_encoders.py/qa.py/real_ner.py/real_models.py re-read with this lens)

(The QA/NLI/NER findings are folded into the "TOP CROSS-CLUSTER FINDING" above; not repeated here.)

- **`ask.classify_task` (keyword/regex) vs. `intent_signals.wants_*` (bge-exemplar)** are two independently-maintained task-classification mechanisms. Confirmed safe today only because `brain.reason()` checks `wants_document` first and dispatches exclusively (so `classify_task`'s output for a document-wanting ask is simply never consulted in that branch) -- but flagged as a maintainability risk: any future stage consulting both without a defined precedence would be a latent conflict.
- **None of the four `intent_signals.py` bge thresholds (IDENTITY_TAU=0.5971, TOTAL_TAU=0.6084, DOCUMENT_TAU=0.75, RULE_TAU=0.62) have any version guard tying them to the exact bge checkpoint (`BAAI/bge-small-en-v1.5`) they were calibrated against.** If `real_encoders.BGE_MODEL_NAME` were ever changed, all four would silently miscalibrate with zero warning, catchable only by manually rerunning EXP-069/078/084's fixtures. Same root cause applies to `MIN_DENSE_SCORE`/`MIN_SEMANTIC_MARGIN` (retrieval cluster) -- no model-version guard exists anywhere in this codebase for any calibrated threshold.
- **`quote_check` coverage confirmed complete:** exactly two places in brain.py extract a free-text span via best-match search and assert it into the final answer (`graph_expand_lookup`, `lookup_fallback`) -- both gated by `quote_check` with zero exceptions. Every other `answer_parts.append` builds text from already-cited, directly-captured substrings (regex/dependency-parse extraction), not a free best-match search, so no second verification pass is needed there. **No citation-integrity gap found.**
- **`open_domain.py`'s FORBIDDEN.md exception confirmed fully and correctly enforced:** `decision` is hardcoded to `"ungrounded"` on both return paths, never `"supported"`; any citation marker in generated text forces a hard "Insufficient evidence." fallback rather than being sanitized and shown; the disclaimer is unconditional. `prompt_contract.py` is pure string formatting, cannot inflate confidence.
- **`lab/common/engine.py` (283 lines) is an entire second, dead verification/answer pipeline** unreachable from `brain.reason()` -- an older, parallel "answer this ask" control loop (imports `ask`, `budget`, `index`, `nli`, `qa`, `schemas`, `textutil`, `verify` directly). Its existence is why `verify.support_check`/`conflict_across`/`output_validator` (entailment check, cross-passage conflict check, a broader qualifier/number/modal/caveat output gate) are themselves entirely dead from the live brain's perspective -- `brain.reason()` only ever uses `quote_check`, a narrower check, on its own answer text, and never runs `output_validator`'s number-preservation/modality-preservation checks against its final `answer_parts` text at all. Open question for the project owner: intentional (because brain.py builds text by concatenation, not generation, so some of `output_validator`'s checks are inapplicable) or a genuine coverage gap (the number/modality checks are NOT obviously inapplicable to concatenated text and are simply never run) -- flagged for misc cluster to confirm `engine.py`'s status and for the project owner to decide.
- `coherence.py` (EXP-050, genuinely bge-backed) is correct, working, unused -- `longform.py`'s leaf ordering never calls it.

### Cluster: Document Generation (14 files, ~1,896+152 lines)

(The rewriter-repair-bypass headline finding is folded into "TOP CROSS-CLUSTER FINDING" above; not repeated here.)

- **Two unrelated `chunk_document` functions share a name, no shared caller, confirmed no active collision:** `ingest.py:26` (live, paragraph-then-sentence split, zero overlap between chunks) vs. `chunking.py:110` (NOT reachable from brain.py; heading/page-aware block splitting + 12%-overlap windows + `version_hash`/`chunk_type`/`extractive_summary`, used only by 6 standalone EXP-003/009/021/025/034/045 scripts). Real maintenance trap: anyone judging "does the live pipeline preserve heading structure" from those six explorations' names alone would wrongly conclude yes.
- **`template_rewriter.py` is reachable in the module-import graph but dead relative to the actual call path:** `assemble.assemble()` (its only caller) is never invoked by `longform.write_long_document` (which only imports `build_outline` from `assemble.py`) or anywhere else in `brain.reason()`'s path. Three "leaf to prose" strategies exist in total (bare join / connective-spliced join / generative+fidelity-gated); only the third is live, with bare-join reused *inside* it as the deterministic fallback.
- **Confirmed no bug (the dangling-edge question from this session's own new dependency_tree code):** every `contradiction_flag` node's `depends_on` references leaf ids that are guaranteed, by `check_and_remember_page`'s own ordering (append current leaf to `self.pages` unconditionally, after reading only prior pages), to already exist as `leaf:` nodes. No dangling edge possible by construction.
- Default checkpoint (flan-t5-small) is consistent between `longform.write_long_document`'s own default and `rewriter_backends.rewrite_unit`'s own default. Fidelity gate is uniformly identical across all 4 rewriter backends (same `fidelity_gate` function, same call site). FORBIDDEN.md's "joining and grammar-correcting already-verified text" wording is honored identically by all 4 backends at the prompt level (`build_prompt` shared by all four) -- no backend does anything more generative/open-ended than the others.

### word_relevance.py (72 lines, read in full by main session 2026-11-03)

Confirmed orphaned (only caller: `lab/exp_049_word_relevance/run.py`), same "measured but never wired in" pattern as `deontic.py` and `coherence.py`. Internally correct and non-duplicative: reuses `rules._parser()` (the shared spaCy parser) and `textutil._token_close`/`content_tokens` rather than reimplementing fuzzy matching or grammaticality checking itself. No overlap/conflict found within the file. A natural EXP-057-adjacent "is this sentence even a well-formed, on-topic clause" pre-filter that nothing in `brain.py`'s signal chain currently calls.

### Cluster: Misc/Orphaned (11 files, ~1,183 lines)

(`engine.py`'s headline finding is promoted to "TOP CROSS-CLUSTER FINDING #2" above; not repeated here.)

- **`provenance.py` vs. this session's new `dependency_tree` mechanism -- resolved, not a duplicate, but a real redundancy-by-divergent-design.** `provenance.py` is a single-statement grounding classifier (is THIS ONE claim `"inference"`/`"evidence"`/`"background"` -- a binary "is this claim grounded in the given text or is it unverified background noise" gate). `dependency_tree` is a multi-node derivation graph (how MULTIPLE already-computed facts/rules/gates chain into a conclusion). Genuinely different jobs -- the new work did not reinvent an existing wheel. But `provenance.py`'s actual safety property (never let a background/common-sense fact pass as a supported, cited claim) is completely unreachable from `brain.reason()` (zero importers besides its own two closed explorations, EXP-013/038) -- and yet that same safety property is still fully guaranteed in the live brain, by a different, more general mechanism that predates this session: every `answer_parts` addition is gated by `quote_check` against a given passage, and the one path with no given passage (`no_context_fallback`) is hardcoded to `decision="ungrounded"`, never `"supported"`. So: two different eras of this codebase independently solved "never let an ungrounded claim pass as supported," and the older, narrower one (`provenance.py`) was simply never deleted, generalized into, or referenced by the newer, more general mechanism once that mechanism took over the job for real. Not a conflict, not a safety gap -- a dead module whose purpose was quietly subsumed.
- **`real_squad.py` confirmed NOT a duplicate of `real_encoders.real_qa`** -- it is a real SQuAD2 *dataset* fetcher (EXP-047), not a model; its own docstring states explicitly it still scores with the old lexical extractor from `qa.py`, no checkpoint involved. Same for `real_corpus.py` (EXP-025, real 1987 Reuters corpus fetcher) -- pure data-prep, no model, no overlap with anything in `real_encoders.py`.
- **`schemas.validate_note` is fully dead code** -- defined, zero callers anywhere in the repo, including `memory.py` (whose note shape it was clearly meant to validate, but `memory.py` never actually imports it).
- **Three more "measured once, never wired into the live brain" capabilities**, same pattern as `deontic.py`/`coherence.py`/`word_relevance.py` above: `memory.py`'s SQLite-backed persistent cross-call recall with revalidation (EXP-016) -- genuinely different from `working_memory.py` (disk-persistent and cross-session vs. in-process and single-call-ephemeral; complementary by design, confirmed not a duplicate, but neither ever calls the other and `brain.reason()` has access to neither's persistence); `proposals.py`'s query-proposal grounding filter (EXP-019, moot today since `brain.reason()` has no query-expansion step to filter candidates for in the first place); `budget.py`'s depth-capped retrieval-round budgeting (used only by `engine.py`, see Top Finding #2).
- **Confirmed correct-by-design, no action needed:** `harness.py` (pure timing/scoring infra, no reasoning decisions, used by essentially every exploration), `lora_finetune.py`/`synthetic_fusion_data.py` (FORBIDDEN.md's offline-training-only carve-out for the one permitted rewriter exception, correctly never touched during live answering).

## Summary for the project owner

**Coverage: 100% -- all 57 non-trivial files in `lab/common/` (8,569 lines) read line-by-line, plus `brain.py` (793 lines) itself, across one main-session pass and 5 parallel cluster audits, 2026-11-03.** Nothing in `lab/common/` was skimmed from memory of earlier sessions; every claim above cites an exact file and line range (see each cluster's section and the full per-cluster scratch reports referenced in this session's commit history for complete detail -- this file holds the synthesized/condensed version of each).

**Overall verdict: no correctness bug was found that produces a wrong, ungrounded, or fabricated answer.** Every citation-bearing span in the live path is gated by `quote_check` with zero exceptions (verification cluster, Q3); the one no-context path is hardcoded to never claim "supported" (verification cluster, Q4); fidelity gates are uniformly applied across every generative backend (document-gen cluster, Q3b). The things that work, work correctly and consistently.

**What's actually wrong, ranked by how much it matters:**
1. **`engine.py` is a live, undocumented second brain** (Top Finding #2) -- the clearest violation of "work in sync like one brain," because it's not a drifted duplicate, it's a second entry point nothing retires.
2. **Real-model capability repeatedly measured, never connected to the live path** (Top Finding #1) -- real QA, half of real NLI, and every generation-repair mechanism this project built and specifically measured (EXP-029 through EXP-063+) sit unused while the live brain uses the weaker classical/bare-generation alternative, silently, with no code comment anywhere flagging the gap.
3. **A confirmed bug in this session's OWN new work**: forward-chained dependency-tree edges beyond step 1 cite the wrong node (`"conclusion"` instead of the real second rule), because `_find_verb_rules` structurally discards passage identity (extraction cluster, Q3). Worth fixing directly, unlike the larger architectural findings above.
4. **A genuine conflict between `plan_stages()`'s own documented invariant and actual execution** (brain.py Finding 1) -- narrow (requires a passage set mixing both rule kinds), not yet reproduced on a real fixture beyond this audit's own constructed example, but a real, confirmed contradiction worth a small fix or an explicit documented caveat.
5. **A cluster of smaller, lower-severity findings**, each individually bounded in impact but all instances of the exact pattern the project owner asked about: `textutil.MODAL_RE` vs. `connectives.py` disagreeing on what counts as a "modal" (can cause an over-cautious rewriter fallback); two unrelated same-named `real_entities` functions (naming-collision risk, not a live bug); two unrelated same-named `chunk_document` functions (maintenance trap, not a live bug); `ask.classify_task` vs. `intent_signals.wants_*` as two parallel, never-reconciled task classifiers (safe today, latent risk); no model-version guard anywhere tying a calibrated bge threshold to the checkpoint it was calibrated against; three DRY-violated near-identical retrieval-helper implementations (`Index`/`RealIndex`/`RealBgeIndex`).
6. **A real, growing list of capabilities that were built, measured, and closed as explorations, but never actually wired into `brain.reason()`**: `deontic.py` (obligation/permission/prohibition classification), `coherence.py` (bge-based page-ordering coherence), `word_relevance.py` (per-word relevance+grammaticality admission gate), `memory.py` (persistent cross-call recall), `proposals.py` (query-proposal grounding filter). None of these are bugs -- they're finished, working capability sitting unconnected, which is squarely within what "do all these layers work in sync" should also mean.

**What this audit did NOT do:** fix anything. Per the project's own append-only-findings convention, this file records what was found; deciding which of the above to fix, document, or formally retire is the project owner's call, not something applied unilaterally during the audit itself. This file stays open for that next phase -- extend it, don't replace it, as each finding above gets addressed (or deliberately left as a documented, accepted tradeoff).

## Open questions to resolve during the audit

1. `real_qa`/`real_nli`/`real_entities` (real_encoders.py) vs `qa.py`'s
   lexical extractor / `nli.py`'s lexical judge / `real_ner.py`'s
   dslim NER pipeline / `entities.py`'s rule tagger -- for each pair,
   which one does `brain.reason()` actually call at runtime, and does
   the other one ever get called from inside the live path (not just
   from a standalone EXP-0NN script)?
2. `real_models.py` vs `real_encoders.py` -- is `real_models.py` truly
   superseded, or does `rules.py` (live) still depend on something in
   `real_models.py` that `real_encoders.py` doesn't provide?
3. `graph.py` vs `graph_index.py` -- confirm `graph.py` is genuinely
   unused dead code (or find where it's still used) and record a
   recommendation (delete vs document-as-historical).
4. Every numeric threshold/margin constant scattered across the live
   modules (MIN_DENSE_SCORE, MIN_LEXICAL_MARGIN, MIN_SEMANTIC_MARGIN,
   wants_document's 0.75, lookup_fallback's tau=0.34, graph_expand's
   tau=0.1, real_bidirectional_nli's tau=0.55, ...) -- listed in one
   place, checked for consistency of what each actually gates.
5. Whether any two signal-chain stages in `plan_stages()`/`reason()`
   could fire in a way that contradicts each other's output for the
   same ask (not just "run in sequence without crashing").

## LLM gap-fill experiment (2026-11-09): empirically tested, not yet safe to wire in

Project owner asked for a generic "LLM fills the gap when deterministic logic
doesn't know how to answer an ask" mechanism (today's timeline capability is
task-specific glue -- `entities.DATE_RE` + `textutil.sentences` -- not general
reasoning), explicitly **without fine-tuning**, with instructions to empirically
validate it across different asks before trusting it. Built `lab/common/
gapfill.py`: prompts an already-approved bounded checkpoint
(`rewriter_backends.generate`) to propose `[passage_id] verbatim span`
candidates, then keeps only candidates whose span passes `verify.quote_check`
(a verbatim substring of the named passage) -- same "accept only if grounded,
empty result over a guess" principle as CaseMap's agreed gap-fill design,
generalized to this project.

**Tested live against gemma3:270m and Qwen2.5-0.5B-Instruct (both already
FORBIDDEN.md-approved bounded checkpoints) across 4 prompt variants: plain
few-shot, few-shot with a worked NONE example, per-passage yes/no framing,
and Ollama JSON-schema hard-constrained `{found: bool, span: str}` decoding.**
Findings, with evidence:

1. **The grounding gate is load-bearing, not a formality -- it already caught
   two real hallucinations in this test session alone.** Asked "What is the
   tenant's phone number?" against passages containing no phone number,
   Qwen2.5-0.5B-Instruct fabricated `987-654-3210` outright; `quote_check`
   correctly rejected it (not a substring of any passage) and the call
   returned no answer. Asked "Why did the dispute arise?", Qwen gave a
   plausible paraphrased causal sentence (not a verbatim quote); grounding
   correctly rejected that too. Both are exactly the "confidently wrong"
   failure mode FORBIDDEN.md rule 15 (CaseMap) warns about, caught by design,
   not by luck.
2. **Precise single-fact extraction, when the fact is genuinely present,
   mostly works on both checkpoints** (e.g. "When was the lease agreement
   signed?" -> correctly extracted the minimal span `"March 4, 2021"`,
   grounded) -- but this capability already exists today via `lookup_fallback`
   + classical QA, so gap-fill adds no new coverage here on its own.
3. **Relevance/abstention judgment (does ANY passage actually answer this, or
   should the system honestly decline) is unreliable, on both checkpoints,
   under all 4 prompting strategies tried.** gemma3:270m defaulted to "found"
   on every single JSON-schema-constrained call across 4 asks x 2 passages --
   it never once said `found: false`, including for the unanswerable
   phone-number ask, and twice produced garbled non-English token soup as the
   "span" while still marking `found: true`. A deterministic bge-embedding
   similarity pre-filter (tried as a cheaper alternative to asking the LLM to
   self-judge) also failed to separate them: the phone-number ask scored
   *higher* topical similarity (0.666) against a passage than a genuinely
   on-topic, correctly-answerable ask ("Why did the dispute arise?", 0.493) --
   embedding similarity measures topical overlap, not presence of the specific
   requested fact, so it is the wrong tool for this gate.
4. **Multi-span/list-style asks (the actual timeline use case) are not reliably
   decomposed by either checkpoint via prompting alone.** Both models
   sometimes returned only one of several events, and in one run literally
   copied the few-shot example's placeholder passage ids (`x1`/`x2`) instead
   of the real ones -- every candidate was correctly dropped by the grounding
   gate for citing a nonexistent passage id, but for the wrong reason (a
   format-copying bug, not a content failure).
5. **Same exact question, same passages, flipped between correct and
   incorrect across two prompt-wording variants** (Qwen: "When was the lease
   signed" answered correctly in one run, incorrectly as `NONE` after only a
   trailing-instruction wording change in the next) -- these checkpoints are
   too prompt-sensitive at this size for the behavior to be trusted as stable.

**Conclusion: grounding alone makes gap-fill safe against fabrication, but not
yet useful.** The one sub-task it reliably adds (single fact extraction) is
already covered by existing deterministic code; the two sub-tasks it was
actually wanted for (timeline/multi-span aggregation, and honest abstention on
genuinely unanswerable asks) are not reliably solved by either bounded
checkpoint via prompting alone, with or without decoding-level constraints.
**`gapfill.py` is NOT wired into `brain.reason()`** -- it exists as a tested,
documented, opt-in-only module; wiring it into the live decision path is
explicitly deferred pending a project-owner decision on how to close the
relevance/abstention gap (candidates discussed: fine-tuning the checkpoint
specifically on the abstain/no-abstain decision; scoping gap-fill to only
run on ask-types where an expected-answer-type check like `entities.DATE_RE`
can validate the span's *category* even when presence can't be judged; or
accepting the narrower, already-working single-fact case as the only
production use for now).

## Method-teaching experiment (2026-11-09, same day): LLM names a tool, never a fact -- partially validated

Project owner's own reframing, after seeing the gap-fill finding above:
the LLM should never produce content at all, even to fail safely -- it
should only "teach" the deterministic layer WHICH of its own existing
primitives to run for an ask type it doesn't recognize, then hand the
actual work back to that layer entirely; if the taught method or its
result is garbage, detect that and stop right there rather than let it
through, even indirectly. Built `lab/common/method_teaching.py`: a closed
`PRIMITIVE_REGISTRY` of 7 named, already-deterministic functions
(`extract_dates`/`extract_persons`/`extract_organizations`/
`extract_amounts` over `entities.detect_primary`; `group_by_sentence` over
`textutil.sentences`; `sort_chronological` over `calc.parse_date`; `count`).
The checkpoint (gemma3:270m) is asked, via Ollama's JSON-schema
enum-constrained decoding, to name 1-4 primitives in order -- the schema's
`enum` makes it structurally impossible to emit a name outside the
registry, so the model literally cannot state a fact; it can only point at
a tool. `validate_plan` re-checks registry membership unconditionally
anyway (never trust the constraint alone), and `execute_method` runs the
named primitives deterministically, threading one step's output into the
next.

**Tested live, 4 ask types (one direct repeat of the timeline case, two
genuinely new types -- "list organizations", "how many people" -- plus one
deliberately unanswerable "phone number" ask), gemma3:270m:**

1. **Zero fabricated facts across every test, including every wrong tool
   choice** -- a structural improvement over the gap-fill experiment above,
   where the same checkpoint fabricated a phone number outright. The worst
   observed failure mode here was either an empty result or a caught
   exception, never invented content. This is the containment property the
   project owner asked for, and it held under live testing, not just in
   design.
2. **Tool *selection* is still frequently wrong.** "List the organizations
   mentioned" got `[sort_chronological, count]` -- nothing resembling
   `extract_organizations` -- and "How many people are named" got the same
   generic 4-extractor plan as the timeline ask, never `count`. Shifting the
   LLM's job from "state a fact" to "name a tool" made failures safe, but
   did not make tool-picking itself reliable at this model size.
3. **A real bug of this session's own code, caught by the first live run
   and fixed in the same pass:** `execute_method` originally overwrote
   `result` on each step instead of accumulating it, so a 4-step
   all-`extract_*` plan silently degenerated to only its last step's
   output. Fixed by having each `_extract_*` primitive fold `prior` in.
   A second bug, also caught live: a structurally valid plan can still be a
   nonsensical *sequence* (`count` producing a dict fed into
   `extract_persons`, which expects a list) that a membership check can't
   catch -- this crashed the first post-fix run. Fixed by wrapping
   execution in a `try/except` that reports it the same way an invalid plan
   is reported (`ok: False`), never lets it propagate as an uncaught error.
4. **The "ok" success signal itself needed a second fix mid-test:**
   `bool(result)` alone called `{"count": 0}` a success (a non-empty dict
   whose actual count is zero) -- caught by the "list organizations" case
   actually running that exact path. Fixed to check the dict's own count
   value, not just Python truthiness.
5. **Remaining known gap, not yet fixed:** "How many people are named"
   still reports `ok: True` with a raw extraction-list result instead of a
   count -- a non-empty, real, *grounded* result that nonetheless doesn't
   answer what was asked, because the chosen plan's output shape doesn't
   match what the ask implies ("how many" implies a count, not a list).
   `teach_and_execute`'s current contract only checks "did the plan produce
   something non-trivially empty," not "does the result's shape match the
   ask" -- the same category of gap `relevance.ask_relevance` was built to
   catch for rewritten prose, not yet built for structured plan output.

**Also unaddressed as of this writeup:** a pre-existing `entities.AMOUNT_RE`
false positive ("2022 over" tagged as an amount, from "...15 June 2022 over
unpaid rent...") leaked into both successful-looking results -- a bug in
already-existing code this experiment exposed rather than introduced,
not yet filed as its own finding.

**Status: not wired into `brain.reason()`.** The core safety property (no
fabricated content, ever, because the LLM's output space is a closed tool
registry rather than free text) is validated. The core usefulness property
(does the taught method actually fit the ask) is not yet reliable enough,
and the one gap identified in finding 5 above (shape-of-result vs.
shape-implied-by-ask) would need to close before this could run live.

### Follow-up, same day: a deterministic gate closes the "always picks something" gap

Project owner asked directly what happens for a genuinely NEW ask type the
7 primitives don't cover at all. Added an explicit `"no_matching_tool"`
escape value to the plan schema's enum and re-tested against 3 asks
chosen to be genuinely outside the registry's capability (sentiment/tone,
argument strength, one-sentence summarization -- none of these are
expressible as any combination of "find entities of type X" / "attach
sentence" / "sort" / "count", because none of the 7 primitives performs
any evaluative or synthesizing judgment at all). **Result: offering the
escape option did not help.** gemma3:270m defaulted to the same generic
4-extractor plan for 2 of 3 out-of-scope asks anyway, marked `ok: True`
with a non-empty, grounded-but-irrelevant result -- the same
"always-confident, never self-aware of not-knowing" bias `gapfill.py`
already found, now shown at the planning level, confirming the model
cannot be trusted to use its own escape hatch.

**Fix: a second, deterministic gate, not another prompting attempt.**
Reused `lab.common.intent_signals._best_similarity` (bge cosine similarity
against a few exemplar phrasings per capability, the same mechanism
`wants_identity`/`wants_total`/etc. already use for brain.py's own stages)
to independently check whether the ask's own question FORM actually
resembles any of the plan's chosen primitives' intent -- `plan_
matches_intent` in `method_teaching.py`, `INTENT_TAU=0.75` (provisional,
one test batch, not yet calibrated the way `IDENTITY_TAU`/`TOTAL_TAU` were
against a dedicated cross-domain exploration). Retested: timeline (0.954),
"list organizations" (0.926), "how many people" (0.844 via
extract_persons) all clear 0.75 easily; "strongest argument" (max 0.582),
"summarize in one sentence" (max 0.626) and the earlier "tenant's phone
number" case (max 0.594) all fall well below it and are now correctly
overridden to `no_matching_tool`, regardless of what the LLM itself
claimed. This is a genuinely different judgment than the embedding
pre-filter that failed in the `gapfill.py` experiment above: that compared
an ask against PASSAGE CONTENT to guess fact-presence (topical overlap
isn't presence-of-fact, and failed); this compares an ask against
CAPABILITY-DESCRIPTION exemplars to guess question-form fit, the exact
comparison `intent_signals.py` already relies on successfully elsewhere in
this codebase.

**Still open:** this closes "wrong category entirely," not "right category,
wrong shape" -- "how many people are named" still passes the intent check
(extract_persons legitimately matches) but returns a raw list instead of a
count, because no step of the chosen plan ends in `count`. Finding 5's gap
(shape-of-result vs. shape-implied-by-ask) is unchanged by this fix and
still open.

### Follow-up, same day: the ask itself becomes logic -- removes the checkpoint from the primary path entirely

Project owner's own reframing, after seeing both the tool-count-growth
problem (every new ask-shape got a new hand-written primitive,
`list_grounded_arguments` included) and the checkpoint's unreliable
picking: the ask is itself natural language, and this project already has
a natural-language-to-logic converter (`lab.common.rules.
parse_conditional_rule`/`extract_fact_triple`, built for rule/fact
sentences) -- so parse the ASK the same structural way, instead of asking
the checkpoint to guess or scoring bge similarity against hand-authored
exemplars.

Built `parse_ask_intent()`/`plan_for_ask()`: a WH-word (when/who/where) or
"how many"/"how much" names an OPERATION directly; otherwise the ask's own
head noun (dependency-parsed the same way `rules._main_verb` already
parses rule sentences -- ROOT's object, or subject of a copula/ccomp/relcl
chain) names it via a small, fixed, domain-agnostic noun->label table (not
growing per ask type, same discipline as `entities.py`'s own fixed label
set). Two genuinely new capabilities fell out of this for free: "how many
people" now correctly resolves to `count` (every earlier test in this
module, checkpoint-proposed, never once chose `count` for a counting
question), and multi-step composition ("timeline" = extract_dates +
group_by_sentence + sort_chronological, not a bare span list) is now a
fixed, named, human-reviewed entry in `_INTENT_TO_PLAN` rather than
something the checkpoint had to improvise into a 4-step sequence.

**`teach_and_execute` now tries this FIRST, with zero checkpoint/embedding
calls, and falls back to the checkpoint-proposed path only when
`parse_ask_intent` returns `None`.** Retested the full 7-ask battery used
throughout this file: all 5 in-scope asks (timeline, list-organizations,
how-many-people, list-arguments-each-side, when-was-X-signed) resolved
correctly via the new deterministic path alone; both out-of-scope asks
(tone/sentiment, phone number) correctly fell through to the checkpoint
path and were correctly rejected there (one by a malformed-plan response,
one by the existing `plan_matches_intent` override) -- no regression in
the fallback's own already-validated behavior.

This also directly closes the "how many tools will we create" concern:
the fixed vocabulary (`_NOUN_TO_LABEL`, `_WH_TO_LABEL`) does not grow one
entry per ask-shape -- it grows one entry per genuinely new LABEL (a new
kind of thing to extract), the same rate `entities.py`'s own label set
already grows at, while `_INTENT_TO_PLAN` composes those labels with the
existing operations. The checkpoint's role shrinks to "things this fixed
vocabulary doesn't recognize at all" -- which, per every test in this file
so far, has yet to produce a single reliably useful result on its own.

## Open-ended "article from messy notes + sources" experiment (2026-11-09, same day): free-form long-form generation is unsafe in a new, worse way than single-fact extraction

Different question from the gap-fill/method-teaching experiments above:
those ask the LLM to extract/locate a single fact or name a tool. This
asked it to do open-ended synthesis -- take a genuinely messy, non-legal,
badly-written user input (misspellings, disconnected reasoning, "peopel
who wrk from home...") plus 2-3 short named sources (`[SRC-1]`/`SRC-2`/
`SRC-3`), and write one coherent article citing sources for sourced claims
and marking the user's own uncited observations as such. Tested live
against gemma3:270m and Qwen2.5-0.5B-Instruct, free-form generation first:

- **Both checkpoints ignored the citation instruction completely** --
  zero `[SRC-n]` markers in either output, despite the prompt explicitly
  requiring one on every factual claim. Not a formatting slip fixable by
  a post-hoc splice (like EXP-063's citation-splice repair) -- the model
  never attempted a citation at all, free-form.
- **gemma3:270m was non-deterministic across two separate runs of the
  byte-identical prompt**, despite `temperature=0, seed=0` pinned the same
  way `real_rewriter_ollama.generate`'s own docstring says this fixes
  reproducibility for the narrow leaf-rewriting role. One run dropped the
  13% figure entirely; the other kept it. Not yet root-caused (not
  reproduced via Ollama's own harness independent of this project); noted
  here because it directly contradicts an existing comment's claim and
  needs re-checking before being relied on anywhere else in this project.
- **Qwen2.5-0.5B-Instruct fabricated a named source organization**
  ("a 2023 survey conducted by Remote Workers Association") that exists
  in neither SOURCES nor USER NOTES -- invented wholesale to sound
  properly attributed. This is the same confident-fabrication failure
  mode as EXP's earlier phone-number fabrication, now at the
  institution-name level instead of the fact level.
- Both checkpoints defaulted to generic boilerplate ("double-edged
  sword", "offers flexibility and autonomy") over the specific content in
  either the sources or the user's notes -- the messy notes' actual
  content (commute time saved, kids/noise, meetings moving online, trust
  eroding) was vaguely paraphrased or dropped, never clearly surfaced.

**Then tested whether this project's own established fix -- a closed
output space via Ollama's JSON-schema `format` constrained decoding, the
same mechanism `method_teaching.py` and `generate_constrained` already
rely on -- closes this gap, the way it did for tool-naming.** Built a
schema forcing a list of `{claim, source_id}` objects with `source_id`
`enum`-constrained to the 3 real ids or `null` (no other string is
structurally decodable). Result: **it made the failure worse, not
better.** Every one of 5 generated claims carried a syntactically valid
`source_id` -- but a deterministic check for literal source-specific terms
(the 13% figure, "5,000", "20-30%", "onboarding", "senior staff") in the
matching claim text found **zero of 3 distinct cited claims carried over
any term actually present in their cited source.** Example: a claim about
"improved employee well-being and reduced stress" was tagged `SRC-3`,
whose actual content is a 20-30% real-estate cost reduction -- completely
unrelated. The model produced confident, generic, properly-shaped
citations attached to content the source never said.

**Why this matters, and how it's different from the earlier findings
above:** constraining the STRUCTURE of a field (which source_id is a
valid enum value) does not constrain, or even correlate with, whether the
CONTENT in the adjacent free-text field is actually grounded in that
source. This is a sharper version of the "containment vs. usefulness"
distinction already documented above -- here, the unconstrained field
(claim text) isn't just unreliable, it looks MORE trustworthy than
free-form prose did, because every claim wears a real citation, while
being equally fabricated underneath. A reader (or a downstream pipeline)
checking only "is this source_id real" would see 100% pass and miss that
0% of claims are actually grounded in their cited source's content.

**Open, not fixed**: the same remedy this file already established for
leaf-level rewriting (`real_rewriter.fidelity_gate`'s NLI/number checks)
has never been applied to this open-ended multi-claim synthesis shape.
The concrete next step, if this capability is wanted, is a second,
independent gate per claim -- content-grounding (NLI entailment or
keyword/number overlap) between `claim` text and the specific source
text named by its own `source_id` -- not more schema constraints on the
citation slot, which this experiment showed does not touch this failure
at all.

## Follow-up, same day (commit pending): the deterministic mechanism can write the article -- `notes_to_findings.py` closes the gap the LLM experiment above could not

Direct response to the open question the previous section left: "assemble.py
already writes documents with zero hallucination risk -- why did the LLM
need to do this at all?" It didn't. The LLM test asked a 270M-500M model to
do THREE jobs at once: split messy prose into claims, decide which source
(if any) backs each claim, and write the final cited prose. `assemble.py`
already does job 3 perfectly (deterministic, docstring: "Code writes the
document; nothing is generated") -- it was simply never fed input that
wasn't already pre-structured. Jobs 1 and 2 are the only real gap, and both
are mechanical, not generative.

Built `lab/common/notes_to_findings.py`: splits messy text into sentences
(`textutil.sentences`) and attributes each one to whichever source shares
the most distinctive content words with it (`textutil.content_tokens` +
`coverage`, the same primitive `relevance.ask_relevance` already relies on
for a different check), or tags it `USER-NOTE` if none qualifies. No LLM,
no embedding call anywhere in this path.

**First attempt, tested live on the identical messy input + sources from
the article experiment above, found two real bugs, not hypothetical ones:**
1. The raw text's hard-wrapped line breaks got treated as sentence
   boundaries by `textutil.sentences`'s `\n+` split, tearing one sentence
   ("productivity go up ... why for sure.") into two fragments that then
   coincidentally matched two DIFFERENT sources. Fixed by joining
   whitespace before splitting -- a line break in a messy paragraph is not
   a sentence boundary.
2. A single short-token prefix match produced a false positive:
   `textutil`'s own `_token_close` matched "realy" (a typo for "really")
   against "real" (from "real-estate") on substring-prefix alone, at 0.50
   coverage -- enough to wrongly attribute an unrelated fragment to SRC-3.
   Fixed in `notes_to_findings.py` only (the shared `textutil.coverage`
   other callers rely on was left untouched) by requiring at least 2
   distinct shared tokens of length >=5 before trusting an attribution,
   not just a coverage ratio off one coincidental hit.

**After both fixes, rerun on the same input end-to-end (raw messy text in,
cited document out, zero manual claim-splitting, zero LLM calls):** every
sentence attributed correctly -- the productivity sentence to SRC-1, the
"senior staff / overhear conversations" sentence to SRC-2, and every
sentence with no real lexical connection (including "company save money on
office space", which IS about the same real-world fact as SRC-3's
real-estate-cost reduction but shares no matching vocabulary) correctly
and honestly left as `USER-NOTE` rather than guessed. `assemble()`'s own
`coverage_report` showed 100% of findings present, `citation_integrity`
showed zero broken markers and zero units without a citation -- both
checks are mechanical, so this is a structural guarantee, not a measured
pass rate. Misspellings/bad grammar in the user's notes are preserved
verbatim in the output (nothing paraphrases), which is the direct tradeoff
against the LLM path: zero fabrication risk, but also zero of the
cosmetic cleanup a bounded paraphrase step (the existing
`real_rewriter`/`method_teaching` leaf-rewriting role) could add on top, if ever applied
AFTER attribution, to one already-decided, already-cited claim at a time
-- never to decide structure or attribution itself, which is exactly the
job this module and `assemble.py` were shown here to already do
correctly without it.

**Still open**: `notes_to_findings`'s lexical-overlap attribution is
conservative by design (favors leaving a claim uncited over guessing), so
some real but loosely-worded connections (the office-space example above)
will be missed, not just hallucinated ones caught. Not measured yet at
scale across inputs genuinely more varied than this one worked example.

## Follow-up, same day: does the project's OWN validated rewriter actually write anything here? Tested directly -- no, every attempt fabricated a connection and was correctly discarded

Direct test, not a restatement of the finding above: ran `rewriter_backends.
rewrite_unit` with checkpoint `gemma3:270m` and `use_repair=True` (the
citation-splice repair that recovered 11/13 otherwise-failed rewrites in
EXP-063) on the exact outline `build_outline` produced from
`notes_to_findings`'s output (3 sources + 7 messy-note sentences, grouped
into 3 leaves of 2-4 findings each). This is not the open-ended synthesis
prompt from the two sections above -- it is the project's own narrow,
already-measured-safe "combine these verified findings into one flowing
paragraph" role (`real_rewriter.build_prompt`/`fidelity_gate`), the one
EXP-063 validated on clean, single-source findings.

**All 3 leaves failed the gate and fell back to the deterministic
concatenation.** The raw generated text, inspected directly, shows why --
every single leaf fabricated a relationship between facts that were never
actually linked:
- Leaf 1 (SRC-1 productivity + SRC-2 onboarding + SRC-3 real-estate +
  1 user note): wrote "This trend was followed by a decline towards
  baseline over the following year, with a 20-30% reduction in
  real-estate costs" -- fusing SRC-1's productivity trend and SRC-3's
  unrelated cost figure into one invented causal/temporal relationship.
  Also added "experiencing limited attention from their colleagues",
  present in neither source. Caught: `nli_ok=False`; also dropped every
  citation marker.
- Leaf 2 (1 sourced + 3 user-note findings, the source text itself hedged
  with "nobody really knows why"): wrote "The increase in productivity is
  attributed to the temporary reduction in commute time, as other
  reasons...are not considered" -- collapsed a stated, genuine two-sided
  uncertainty into one confidently asserted cause. Caught: `modal_ok=False`.
- Leaf 3 (1 sourced + 1 user-note finding, about two different things --
  general team trust, and junior/senior mentorship specifically): wrote
  "The relationship between young workers and senior staff has declined
  over time, with a decrease in trust" -- merged two separate, unrelated
  observations into one invented relationship. Caught: `modal_ok=False`,
  `nli_ok=False`.

**Why this is a different finding from the sections above, not a
repeat:** those sections tested free-form, open-ended article synthesis
with no structure/attribution decided yet. This tests the narrowest,
already-safest role this project has -- phrasing ALREADY-decided,
ALREADY-cited findings into one paragraph, with the fidelity gate active
exactly as EXP-063 measured it. It still fails, every time, on this input
shape specifically because the findings are heterogeneous: precise,
numeric, third-party facts sitting next to vague, hedged, first-person
notes. "Combine into flowing prose" implicitly requires deciding HOW
these facts relate to each other, and that relational judgment is exactly
the kind of thing this project's whole LLM-safety trail has shown small
checkpoints fake confidently (a plausible-sounding causal link) rather
than either doing correctly or declining to do. The existing gate
(entity/number check, modality check, bidirectional NLI, citation
presence) caught every one of these fabrications live, with zero
exceptions in this run -- the safety net held. But the practical result
is: for this kind of mixed-register, multi-source-plus-user-note input,
the only thing currently reaching final output is the safe
`notes_to_findings` + `assemble()` concatenation from the section above --
genuine composed prose is not currently achievable without either (a)
a much stronger model, or (b) narrowing the rewrite unit further so it
never has to relate two DIFFERENT findings to each other at all (one
finding per leaf, never combined -- untested here, since `build_outline`
groups up to 4 per leaf by default).
