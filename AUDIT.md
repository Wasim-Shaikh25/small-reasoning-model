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
