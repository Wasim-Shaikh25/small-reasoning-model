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

## Follow-up, same day (commit pending): `write_article.py` -- the full pipeline, confirmed end-to-end, zero fabrication

Closes the thread started by "why rewriting is not working" and "is it now
able to write or rewrite." The fabrication found in the section above
("does the project's OWN validated rewriter actually write anything
here?") was traced to one specific thing: `assemble.build_outline`
groups up to 4 findings into one leaf, and `real_rewriter.build_prompt`
instructs the model to "combine these verified facts into one flowing
paragraph" whenever a leaf has more than one finding -- that instruction
is what invited the model to invent a relationship between facts that
were never connected. It was NOT a missing language-to-logic/tree-
reasoning step: `rules.parse_conditional_rule`/`extract_fact_triple` were
tested directly against this exact content and found inapplicable (zero
conditional-rule structure present; the fact-triple extractor discards
the actual claim inside "a survey found..."-style reporting sentences).
That mechanism is built for conditional legal/policy rules, a narrower
shape than general declarative reporting -- not a stronger version of
the same tool, a different one.

Verified directly: restricting the rewrite unit to exactly ONE finding at
a time (never combining) removes the invitation to invent a relationship
entirely. Re-ran the same 10 findings this way: 8 passed the fidelity
gate with zero fabrication (every pass a faithful paraphrase, at most
trivial grammar smoothing); the 2 that fell back did so for ordinary,
already-understood reasons -- one empty generation, one that dropped a
hedge word ("not all") -- not invented relationships. This is the same
failure class EXP-048/054/056/062 already measured and built this gate
for, not a new one.

Built `lab/common/write_article.py`, composing three independently-tested
pieces in the order that keeps them safe together:
1. `notes_to_findings` (language-to-structure: sentence-split + lexical
   attribution, no LLM) -- the system cannot reason over raw strings, so
   this step is the actual answer to "where does language-to-logic come
   into the picture," just a lexical-token version of it rather than
   `rules.py`'s SVO/conditional-rule version, which this content doesn't fit.
2. `rewrite_findings_individually` -- one finding per call, fidelity-gated,
   falls back to the original statement per-finding on failure.
3. `assemble.assemble` -- unchanged, deterministic, with its own
   coverage/citation-integrity checks.

Ran the full pipeline end-to-end on the original messy paragraph + 3
sources, zero manual claim-splitting: 100% finding coverage, zero broken
citation markers, zero units without a citation, 8/10 findings
individually rewritten with no fabrication, 2/10 safely using the
original text. Grouping findings into sections for readability (still
`assemble`'s groups-of-4) is kept fully separate from the one-at-a-time
rewrite step, so a smarter, topic-aware grouping (an actual tree over
shared entities/tokens, not yet built) could replace that chunking later
without ever touching the part proven safe here.

**Still open**: the section grouping itself is still arbitrary
(chunks of 4), not topic-aware -- a genuine tree/clustering step over
findings (grouping by shared tokens/entities across ALL findings, not
just note-to-source attribution) would be a legitimate way to realize
the "writing is tree reasoning" instinct that prompted this follow-up,
but it has not been built or tested yet.

## Follow-up, same day (commit pending): directed relationship graph + cycle detection, built and verified on the X-gave-Y-gave-Z-gave-X example

User's direct challenge: "if it's not able to [connect facts like X gave Y
money, Y gave Z money, Z gave X money, and find the relationship between
X and Z], it's not built properly." Tested the two relevant existing
primitives separately first, live:
- `lab.common.graph_index.build_entity_graph` (undirected entity
  co-occurrence graph, built for cross-referencing retrieval, not for
  this): correctly found a closed triangle when every pair also directly
  co-occurs, AND correctly performed genuine 2-hop traversal (Alice ->
  Carol via Bob) in a variant where Alice and Carol are NEVER mentioned
  in the same sentence at all -- confirms this project's multi-hop
  fact-connecting machinery already works, tested, not assumed.
- `lab.common.rules.extract_fact_triple` (subject/verb/object via
  dependency parse): correctly recovered directed subject->object for
  all three "X gave Y $N" sentences, and the three directed edges
  (Alice->Bob, Bob->Carol, Carol->Alice) correctly chain back into a
  real cycle.

Neither primitive alone does what the user described (undirected
co-occurrence has no notion of direction; the fact triple has direction
but no cycle detection, and drops the amount -- "$500" never appears in
`extract_fact_triple`'s output, a second complement the parser isn't
built to carry).

Built `lab/common/relationship_graph.py`, combining them: `extract_fact_triple`
gives direction; the amount gap is fixed additively (pulled separately via
`entities.detect_primary`'s already-measured "amount" label and attached
to the edge, without changing `extract_fact_triple`'s own return shape,
since `rules.apply_rule`/`answer_rule_question` already depend on it
unchanged). `find_cycles` is a bounded DFS over the resulting directed
graph, deduped across rotations of the same cycle.

Verified live, three cases:
1. The exact cycle (Alice->Bob $500, Bob->Carol $300, Carol->Alice $200):
   found exactly 1 cycle, with every edge's amount correctly attached.
2. The same two edges with the closing one removed (a plain chain, not a
   cycle): 0 cycles found -- no false positive.
3. Two completely unrelated gave-sentences (different people): 0 cycles
   found -- no false positive.

**Answer to "is this just not built properly": it already existed in two
separate, independently-tested pieces, and combining them (not inventing
new judgment) closes the gap.** No LLM anywhere in this path -- entirely
dependency-parse + regex + bounded DFS, same safety profile as every
other primitive in this file's trail.

**Still open**: nodes are keyed on normalized exact span text (same
substitute for "understanding" `graph_index.py` already uses) -- "Alice
Smith" and "A. Smith" would not be recognized as the same node; no
spelling/alias resolution is attempted here, by design, matching this
project's existing stance. `find_cycles` is brute-force DFS, bounded by
`max_len`, appropriate for the small one-edge-per-passage graphs this
builds, not a general large-graph cycle finder.

## Follow-up, same day (commit pending): pronoun/coreference gap in relationship_graph.py -- found, fixed, limit made visible not hidden

User's direct challenge: "Smith can also refer as she... what are we
gonna do about that?" Confirmed live this was a real, currently-total
gap: a pronoun subject/object ("He gave Carol Lee $300") normalizes to
its own disconnected node ("he"), breaking cycle detection completely --
re-ran the exact 3-party cycle from the section above with the 2nd and
3rd mentions replaced by "He"/"She" and got 0 cycles found instead of 1.
Checked whether `entities.resolve_mentions`/`apply_ambiguity_rules`
already covered this: no -- that mechanism resolves SURNAME ambiguity
("Smith" vs. which full "___ Smith"), not pronouns; there was no
pronoun/coreference handling anywhere in this codebase before this.

Fixed with a nearest-antecedent heuristic in `relationship_graph.py`
only (no shared primitive touched): a bare pronoun resolves to whichever
real person/organization span was most recently seen in passage order.
Tested on two cases built specifically to find where this breaks:
- Straightforward (name, then pronoun, then pronoun, in order): resolved
  correctly, cycle found, exactly as before.
- Adversarial (the true antecedent was the previous CLAUSE's subject,
  not its most recently named entity -- an incidental mention sits in
  between): resolved INCORRECTLY. Confirmed this is not a patchable bug
  but the actual hard problem -- "prefer most recent mention" and "prefer
  previous subject" each fix one of these two cases and break the other;
  resolving both needs gender/number agreement or real discourse
  modeling, neither of which this project uses anywhere else.

Asked the user directly: best-effort guess (confirmed sometimes wrong)
vs. abstain whenever more than one candidate exists (confirmed would
also lose the straightforward case, since "X gave Y" sentences always
name two people). User chose best-effort guessing, then asked for the
better engineering answer rather than a blind binary choice --
implemented BOTH: every edge now carries `antecedent_ambiguous` (True
when the resolution picked among >1 real candidate) and
`antecedent_alternatives` (what it passed over). Re-verified: the
straightforward case's "He" resolution is correctly flagged ambiguous
(2 candidates were present) even though the guess happened to be right;
the adversarial case's wrong guess is flagged ambiguous too (visible,
not hidden); a genuinely single-candidate case resolves with
`antecedent_ambiguous: False`. This mirrors `entities.
apply_ambiguity_rules`'s existing pattern of marking a conflict
"ambiguous" with alternatives rather than either silently merging or
silently dropping it -- the same principle, applied to a different
(pronoun, not surname) ambiguity source.

**Still open, stated as a limit, not hidden**: this is a recency
heuristic, not coreference resolution. It will still guess wrong on
cases shaped like the adversarial example above; the `antecedent_ambiguous`
flag only tells a caller WHEN to distrust a resolution, not what the
correct one actually is.

## Follow-up, same day (commit pending): `article_tool.py` -- everything today combined into one named, schema-checked tool

User: "now let's make it write one article, give it format as tool."
Wraps today's three pieces (`notes_to_findings`, `write_article`,
`relationship_graph`) into one callable with the same shape as this
project's other named tools (`rewriter_backends.BACKENDS`,
`method_teaching.PRIMITIVE_REGISTRY`): a fixed input contract
(`{"notes": str, "sources": [{"id","text"}, ...]}`), a fixed output
contract, validated before anything runs. Malformed input (empty notes,
sources not a list) returns `ok: False` with specific errors and runs
nothing -- never a guess at what a bad call meant, same discipline as
every other primitive in this file.

Renders the final output as one markdown article: sections with inline
citations, a Sources appendix, and (new) a "Relationships detected"
section listing any directed cycle `relationship_graph.find_cycles`
found across the combined sources + notes, explicitly labeling any cycle
that relied on a guessed (ambiguous) pronoun resolution rather than
silently presenting it as certain.

Verified two ways: (1) as a plain Python call on the original messy
remote-work input -- correct 3-section article, 100% coverage, zero
broken citations, zero relationship cycles found (correctly, since
there are none in that input); (2) as the actual CLI
(`python -m lab.common.article_tool payload.json`) on a fresh
notes-only input with no sources at all, containing the pronoun-chain
payment cycle from the relationship_graph work above -- correctly wrote
the article AND correctly surfaced the cycle with its ambiguous-pronoun
warning, end-to-end from a JSON file on disk through to printed output.

## Follow-up, same day (commit pending): the fix is embedding-based disambiguation, zero generative model calls

User's direct challenge after five failed generative attempts (isolated-
word pick x2 checkpoints x2 prompts, joint-sentence pick, whole-sentence
free rewrite, a worked few-shot example with the answer shown): "Why do
we need a model? Can't our system make sense of it with the model's
VOCAB?" Tested directly rather than assumed: resolve ambiguity via
bge-embedding similarity between each candidate word and its sentence
context (word removed) -- the same non-generative signal
`intent_signals._best_similarity` already relies on for ask-vs-
capability-exemplar matching, applied here to word-vs-context instead.

**Result: 4/4 on every case every generative attempt got wrong or
unreliable on** -- "herd"->heard, "realy"->really, "lonly"->lonely,
"peopel"->people. Re-ran the full 7-sentence paragraph end-to-end:
6 of 7 distinct typo types now resolve correctly with zero generative
model calls (peopel x2, wrk, herd, lonly, realy all correct; "thats"
loses its apostrophe, a vocabulary-construction artifact, not a wrong
pick). The one true miss, "cos"->"cons" (expected "because"), is a
DIFFERENT class of problem from everything else in this file: "because"
is not within edit distance 1 of "cos" at all, so no candidate-based
method -- generative or embedding -- can ever find it; this is a
vocabulary-coverage gap (informal abbreviation, not a misspelling), not
a disambiguation failure.

**Why embeddings succeeded where five generative attempts, two
checkpoints, and one worked few-shot example all failed**: picking which
real word fits a context is a SEMANTIC RELATEDNESS judgment -- the same
kind of judgment this project already measured bge embeddings as
reliable for (ask-vs-capability-exemplar matching, `intent_signals.py`).
It is a different use case from ask-vs-passage-content similarity for
guessing fact presence, measured UNRELIABLE the same day in gapfill.py --
the project's standing lesson that different embedding use cases have
different reliability held again, now in the opposite, favorable
direction: this was genuinely safe to trust, once tested, not assumed
either way. A 270M-500M generative model, by contrast, has to perform
several implicit reasoning steps (read the sentence, understand what
each candidate means, judge fit) to answer the same question, and this
file's own history shows that repeatedly fails even when a worked
example with the literal answer is placed one line above the real
question -- not a prompting gap, a genuine capacity ceiling.

`lab/common/spellfix.py` rewritten: `fix_sentence_joint` now resolves via
`_pick_by_context_embedding`, no model-backend parameter, no checkpoint
dependency. `resolve()` and `fix_sentence()` (the generative approaches)
are kept in the file, unused by the new primary path, as the documented,
tested, inferior alternatives -- not deleted, per this project's practice
of keeping a failed design's evidence visible rather than erasing it.

## Follow-up, same day (commit pending): informal-register normalization closes the "cos" gap

The one miss left in spellfix.py's tally ("cos"->"cons", expected
"because") was already correctly diagnosed as a different problem class:
"because" isn't within edit distance 1 of "cos" at all, so no candidate-
based method, generative or embedding, could ever reach it -- it's an
informal WORD, not a misspelling.

Added `lab/common/informal_register.py`: a small, hardcoded table of
unambiguous English informal contractions (cos/coz/cuz->because,
gonna->going to, wanna->want to, gotta->got to, etc.), applied as a
literal whole-word substitution before typo detection runs -- same
grounding this project already uses for `connectives.py` (a small,
closed, catalogued linguistic class is legitimately hardcoded; guessing
open-ended vocabulary is not). Wired into `spellfix.fix_sentence_joint`
as a normalization pass before candidate detection.

Re-ran the full 7-sentence paragraph: "cos" -> "because", correctly.
All 7 distinct typo/informal-word instances in this file's running test
case now resolve correctly with zero generative model calls.

## Follow-up, same day (commit pending): structural attribution gate fixes the rule-source mis-attribution found testing a full petition

Direct test of "can a full petition be written from raw material with
zero LLM calls": built one end-to-end, zero generative model anywhere
(spellfix + informal_register to clean raw petitioner notes,
notes_to_findings to attribute them, rules.apply_rule to derive Grounds
from the petitioner's own fact against a rule source, assemble to render
the document). It worked structurally -- 100% coverage, zero broken
citations, a genuinely rule-derived Grounds section -- but surfaced a
real mis-attribution: the petitioner's prayer ("I want the rent increase
stopped and my deposit back") was wrongly tagged to the RULE-1 source,
purely because it shares two generic words ("rent", "increase") with it.
With only one narrowly-topical source, nearly every sentence in the
document naturally shares enough vocabulary to clear
`notes_to_findings`'s lexical threshold -- a real limitation of lexical
attribution alone when sources aren't topically distinct from each
other, not previously exercised since every earlier test used 3
topically-separated sources.

User's proposed fix, tested directly: run one more round through tree
reasoning + the language-to-logic converter. Confirmed live: the
genuinely-grounded sentence ("my landlord raised my rent...") structurally
matches the rule's trigger verb lemma ("raise") via `extract_fact_triple`
+ `apply_rule`; the wrongly-attributed prayer sentence doesn't even parse
as a fact triple at all (`extract_fact_triple` returns `None`). Added a
second, STRUCTURAL gate to `notes_to_findings`, firing ONLY when the
matched source itself parses as a conditional rule
(`rules.parse_conditional_rule`): the candidate note must also parse as
a fact whose verb lemma matches the rule's trigger (`rules.apply_rule`)
before the lexical attribution is trusted; if not, falls back to
USER-NOTE rather than keep a coincidental-vocabulary-only match. Re-ran
the petition test: the prayer sentence now correctly tags USER-NOTE.
Re-ran the original 3-source remote-work regression test (AUDIT.md,
2026-11-09 earlier): byte-identical result -- none of those sources
parse as conditional rules, so the new gate never fires for them,
exactly as scoped.

This directly answers "is writing content going through language logic
converter and tree reasoning" from earlier the same day, in the one
place it was actually missing: attribution against a RULE-shaped source
now does, through the exact mechanism (`extract_fact_triple`/
`apply_rule`) already validated for Grounds sections in
`method_teaching.py`'s `list_grounded_arguments` -- reused, not
reinvented, and scoped to only the case it was shown to be needed for.

## Follow-up, same day: does fluency require a generative model, and does `template_splice` actually beat what's live today?

User asked why fluency can't come from NLI/embeddings and whether only
a generative checkpoint (gemma3:270m) can supply it. Both halves tested
rather than argued:

**Why NLI/embeddings can't supply fluency, structurally:** both are
comparison tools over text that already exists (NLI: 3-way label for a
given pair; embeddings: one similarity float for a given pair). Neither
has an operation that emits a new token sequence. `spellfix.py`'s
embedding win worked because the candidate set was small and already
enumerable (real words at edit-distance 1); sentence-level fluency
(merging findings, varying phrasing) has no equivalent small enumerable
set, so there is nothing for a comparison tool to pick between. This is
the same lesson as spellfix's own, one level up: comparison is only
safe when the candidate set is already closed.

**But `lab/common/template_rewriter.py`'s `splice_unit` already proves
*some* fluency doesn't need a model at all** -- a fixed, 4-connective
closed vocabulary ("", "Also,", "However,", "In addition,") chosen by
plain classical signals (`modals`, `polarity_flipped`, leading-subject
match), built in EXP-054 specifically because generative rewriting was
measured dropping content. It is wired into `assemble()`'s
`rewriter="template_splice"` mode but NOT into `longform.
write_long_document`/`rewriter_backends.rewrite_unit` (the live
long-document path), so it had never been run against a real multi-
finding long-document fixture before this check.

**Tested against EXP-081's real fixture (19 leaves, 69 findings from a
2,368-word GDPR excerpt), with a result sharper than expected:**
`data/exp_081_real_document_pipeline/results.json` already shows BOTH
checkpoints that exist for this live path -- flan-t5-small AND
Qwen2.5-0.5B-Instruct -- scored `fidelity_pass_rate: 0.0`, 0/18 leaves
each. Every leaf on this real document already falls back to the
deterministic `render_unit` text today; the committed `gdpr_rewritten.md`
/`gdpr_rewritten_qwen.md` files contain zero generative-model output,
even though a generative call is attempted on all 18 leaves currently.
Running `splice_unit` on the identical 19-leaf outline (reproduced from
EXP-081's own embedded fixture, `_entity_outline`/`build_outline`)
gets the same `coverage: 1.0`/`citations: {broken: []}` (expected --
it cannot drop or invent anything) while actually inserting connective
text between findings where today's live output has none. On this one
real document, `template_splice` is a strict, measured improvement over
what the live pipeline actually produces today, at zero model cost and
zero latency.

**But testing it, not just running it once, surfaced a real bug in the
deterministic mechanism too** -- `choose_connective` picked "However,"
between two GDPR definitions ('personal data' then 'processing') that
are not actually in contrast. Root cause: `textutil.MODAL_RE`/`NEG_RE`
match the bare word "not" inside "whether or not by automated means" --
a fixed idiom meaning "regardless," not a real negation/modal -- so
`modals()` wrongly reports a modal shift and `choose_connective` reads
it as contrast. This is the same `MODAL_RE` looseness the 2026-11-03
audit already flagged (Finding #5, "can cause an over-cautious
rewriter fallback, never a wrong answer") -- but applied to a
connective-choice mechanism that didn't exist at the time of that
finding, its consequence is new: a wrong connective, not just an
over-cautious fallback. Not yet fixed. Confirmed directly:
`polarity_flipped(def_a, def_b)` returns `True` and `modals(def_b)`
returns `['not']` purely from "whether or not."

**Where this leaves the generative-model question:** flan-t5-small is
confirmed dead weight on two separate real fixtures now (EXP-048's
original 0/4, and this one's 0/18). `template_splice` already closes
the connective-joining slice of fluency gemma3/Qwen were meant to cover,
with a measured win on the one real document tested, zero model calls,
zero fabrication risk -- but it is not bug-free either, and is not
wired into the live `write_long_document` path. Gemma3:270m's own
measured value (EXP-063, 11/13 repair-recovered) was on a leaf-size-1
fixture where there is nothing to splice between -- that specific
measured win is about single-sentence citation-repair, a different
capability `template_splice` does not attempt and cannot replace.

## Follow-up, same day: a deterministic pre-check that removes the single-sentence case too, not just measures it

User then asked for a genuinely novel mechanism, using only existing
systems, to close the one remaining gap above -- single-sentence
"rewrite as one grammatically correct sentence" (`real_rewriter.
build_prompt`'s own literal instruction for a size-1 leaf). Reframed the
question structurally: that instruction only has work to do if the
source statement ISN'T already one grammatically correct sentence. If it
already is, generation is a detour that can only end at the deterministic
text it started from (confirmed twice already -- EXP-048 and this same
day's EXP-081 re-run both measured 0% generative success on real
fixtures). So the question became: can the project detect "already
complete" BEFORE calling a model, deterministically, cheaply?

Built `lab/common/sentence_completeness.py`'s `is_complete_sentence`:
reuses `real_models`' already-loaded `en_core_web_sm` spaCy pipeline (an
existing dependency, already used for NER elsewhere) for its dependency
parse only. Checks two things, both zero-generation: the sentence has a
finite verbal ROOT, and it doesn't end on a dangling conjunction/
preposition/determiner (a clause cut off mid-way).

**Tested against both real fixtures, verified individually rather than
trusted from a summary flag:** EXP-063's 13 handwritten statements are
13/13 `ok`. EXP-081's 69 real GDPR findings are 56/69 `ok`, plus 13
flagged `no_verbal_root` -- printed every one of those 13 rather than
assume what they were: 12 are verbatim article headings ("Art. 83 GDPR /
General conditions for imposing administrative fines") and 1 is a genuine
lead-in fragment ("For the purposes of this Regulation:"). Neither kind
is a sentence a rewrite could legitimately fix -- forcing a heading into
"one grammatical sentence" fabricates structure the source never had; the
lead-in fragment is correctly incomplete by design, already handled
correctly by `template_splice`'s sequencing, not by rewriting it. **69/69
of this real document needs zero generative rewriting, provably in
advance, for two different, individually-confirmed reasons -- not
assumed from one convenient flag.** (The module's own first-draft
`heading_like` sub-flag, token-count-only, matched just 1 of those 13 on
re-check -- caught by re-verifying against the actual flagged text
instead of trusting the flag, kept in the module only as a documented
weak hint.)

**Adversarially tested before trusting it, same discipline as every other
mechanism this session:** correctly flags "The cat sat on the mat and"
(dangling conjunction) and "Payment due on the 1st, subject to" (dangling
preposition). But has two confirmed, undocumented-no-longer blind spots:
"Running quickly down the street." (a gerund-only fragment) and "Because
the tenant did not pay." (a subordinate clause alone, no independent
clause) both parse with a verbal ROOT and wrongly pass as `complete`.
Neither blind spot was hit by either real fixture tested; neither is
fixed. This module does not claim to be a general grammaticality
checker, and is explicitly not a grammar/spelling corrector (a sentence
full of typos still parses with a verbal root and passes -- that is
`spellfix.py`/`informal_register.py`'s scope, not duplicated here).

**Net effect on the generative-model question:** flan-t5-small and
Qwen2.5-0.5B-Instruct are now confirmed structurally unnecessary for
every single-sentence leaf in both fixtures tested -- not just measured
to fail after the fact, but detectable as unneeded before ever calling
them. Not wired into `rewrite_unit`/`rewriter_backends.py` yet (a
pre-check gate there would skip `generate()` entirely when this function
returns `complete: True`, same spirit as the existing fallback but
running BEFORE the model call instead of after). Still open: whether the
`no_verbal_root` case ever needs anything beyond "leave it verbatim and
let `template_splice`/`render_unit` sequence it" -- neither real fixture
tested contained a case where that wasn't already sufficient.

## Follow-up, same day: the pre-check gate wired into the live default path, verified byte-identical output

User said to actually wire the gate in rather than leave it standalone.
Added the check to `rewriter_backends.rewrite_unit` itself (the shared
dispatcher `longform.write_long_document` always calls at `use_repair=
False`, its default): for a single-finding leaf, `sentence_completeness.
is_complete_sentence` runs BEFORE `build_prompt`/`generate()`; if the
statement is already complete, returns the deterministic text directly
with a new `fallback_reason` value, `"already_complete"`, and never calls
the model. Multi-finding leaves are untouched -- the gate was only ever
tested against single-statement completeness.

**Verified with a monkeypatched `generate()`** (so model calls are
countable without needing the real checkpoints loaded): a complete-
sentence single-finding leaf now makes 0 calls to `generate()` (previously
1); a `no_verbal_root` single-finding leaf (a heading/fragment) still
calls it once, unchanged -- the gate does not claim to handle that case
live yet, exactly as scoped; a multi-finding leaf still calls it,
unchanged.

**Verified for real by re-running EXP-081** (the one real-document
fixture this gate was built and measured against), both checkpoints:
`gdpr_rewritten.md`'s sha256 is byte-identical to the pre-change
committed version (`3d13701fb...`) -- same document, same 2,469 words,
same `fidelity_pass_rate: 0.0` for both flan-t5-small and
Qwen2.5-0.5B-Instruct (unchanged, as expected -- `already_complete` is
also `used_generative: False`, same outcome the old failing generate()
call already fell back to). The ONLY change in `results.json`:
`fallback_reason_counts` now carries `"already_complete": 1` for each
checkpoint (1 of 18 leaves on this fixture happens to be a single-finding
leaf whose statement is already complete -- most of the 56 individually-
complete findings measured earlier are grouped into multi-finding leaves
by entity-outlining, which this gate does not touch), and one fewer real
`generate()` call was made per checkpoint. `elapsed_sec` dropped from
3096.0 to 815.7 on this run -- reported as observed on one run, not a
timing benchmark (EXP-045 already noted timing varies with machine load),
but directionally consistent with removing wasted model calls.

**Not re-verified, scope limitation stated plainly:** four other
explorations touch this same dispatcher (`lab/exp_052_ask_driven_outline`,
`lab/exp_076_legal_gemma_rewriter`, `lab/exp_078_longform_consistency`,
`lab/exp_082_document_tool_templates`) and were NOT re-run this session --
their committed `results.json` may now be stale in the same narrow sense
EXP-081's was (a `fallback_reason_counts` label, never the actual output
text, which this change cannot alter for any leaf it doesn't skip).
Re-run and refresh each the next time it's touched, per this file's own
append-only/measure-before-claiming convention -- not assumed fixed here.

## Follow-up, same day: template_splice wired into multi-finding leaves too, and its connective bug turned out far worse than one example suggested

User asked to wire `template_splice` into the multi-finding path the same
way the completeness gate now covers single-finding leaves, then asked
why fluency can't come from grammar/tree-reasoning enumeration plus
NLI/embeddings -- correctly pointing out this is safe specifically
because it assembles existing content rather than inventing any.

**Wiring:** `rewriter_backends.rewrite_unit` now computes
`template_rewriter.splice_unit(leaf, glossary)` as `deterministic_text`
(byte-identical to the old `render_unit` output for a single-finding leaf,
confirmed by inspection of `choose_connective`'s "first" case -- a strict
superset, not a behavior change for leaves it can't improve) and, for any
multi-finding leaf, returns it directly WITHOUT calling `generate()` at
all -- same logic as the single-finding completeness gate, one level up.
Verified with a monkeypatched `generate()`: 0 calls for both a complete
single-finding leaf and a multi-finding leaf; a fragment/heading
single-finding leaf still calls it once, unchanged.

**Re-ran EXP-081 for real:** `fallback_reason_counts` is now exactly
`{"deterministic_splice_preferred": 17, "already_complete": 1}` for BOTH
checkpoints -- 18/18 leaves, zero `generate()` calls anywhere in this
pipeline run. `elapsed_sec` dropped 815.7 -> 63.5 (~13x), `peak_rss_mb`
3682 -> 998 (no transformer weights held for generation). Decision/
citations/fidelity outcome unchanged (`supported_with_flags`, 69
citations, 0.0 fidelity pass rate either way -- `already_complete` and
`deterministic_splice_preferred` are both `used_generative: False`, the
same outcome the old always-failing generate() call already fell back
to). Document content legitimately changed (word count 2469->2546, +77
words of real connective text; sha256 changed accordingly) -- the
measured improvement, not a regression.

**But reading the actual rendered document surfaced the earlier
connective bug at a severity one hand-picked example never showed:** 21
of 51 connectives chosen were "However," -- on a document that is
overwhelmingly a LIST of parallel, non-contrasting legal obligations and
definitions. Root cause confirmed at scale: `choose_connective`'s
`modals()`/`polarity_flipped()` checks fire on bare presence of
"not"/"no"/"shall"/"unless" ANYWHERE in the sentence -- which is nearly
every sentence in dense legal prose, not evidence of contrast with the
specific previous sentence. This is far more pervasive than the single
"whether or not" idiom case found two turns ago; it's the dominant
behavior on this entire document class.

**Fixed, not just documented, per standing project policy**
([[feedback_no_hardcoded_connectives]]: always detect connectives via
`find_connectives`, never regex): `choose_connective`'s contrast check
now reuses `lab.common.connectives.find_connectives` -- this project's
own already-validated, dependency-parse-based discourse-connective
detector -- and fires only when the current statement's own text
structurally contains a genuine `Operator.CONCESSION`-class marker
(however/although/though/despite/while/whereas/nevertheless), i.e.
textual evidence of an actual contrast, never an inference from
negation's mere presence. Verified: the exact idiom false-positive case
("whether or not") now resolves to "In addition,"; a genuine contrast
case ("The tenant paid... However, the landlord still...") still
correctly resolves to "However,"; re-running EXP-081 end to end dropped
"However," from 21/51 to 0/51, with fidelity numbers, leaf counts, and
`fallback_reason_counts` otherwise unchanged (confirmed, not assumed).

**Where this leaves the generative-model question, concretely:** on the
one real document fixture tested, the live default pipeline now makes
zero generative-model calls, with a verified byte-level before/after
comparison at every step, not an assumption. The three theoretical gaps
named in earlier entries (gerund/subordinate-clause fragments in
`sentence_completeness`; the `no_verbal_root` single-finding case still
calling `generate()`; the four untouched explorations sharing this
dispatcher) remain exactly as stated -- none of them were hit by this
fixture, none are claimed fixed.

## Follow-up, same day: four big end-to-end tests, run in parallel, to see whether all this actually scales past one-paragraph examples

User asked for one big combined experiment: (1) a ~10-page petition for
the Bombay High Court from a fabricated case plus raw notes, (2) rewriting
a real ~10-page document into simple English, (3) extracting "findings"
from a research/decision document, (4) applying a company policy to
customer case scenarios, including fetching real data from the web. All
four run with zero generative-model calls, each independently, each
reporting failures honestly, not just successes.

**(1) Bombay HC petition, 2,543 words, zero generative calls (confirmed:
`spellfix.fix_sentence_joint`, `notes_to_findings.notes_to_findings`,
`rules.parse_conditional_rule`/`extract_fact_triple`/`apply_rule`,
`assemble.assemble(rewriter="template_splice")` -- no model anywhere).
Clearly labeled "SAMPLE/FICTIONAL... NOT A REAL FILING," invented parties.
41 findings, coverage 1.0, zero broken citations.

Surfaced and FIXED a real, previously-undiscovered bug in `spellfix.py`:
with no proper-noun protection, "Sagar" -> "sugar", "Mehta" -> "meta",
"Pvt" -> "pot" -- real close-by English words corrupting correctly-spelled
capitalized input. First fix only skipped MID-sentence capitalized words
(`i > 0`); direct adversarial testing of the fix itself caught that a
SENTENCE-INITIAL proper noun ("Sagar Mehta of Oceanic Pvt Ltd filed...")
was still corrupted, since position 0 was never checked. Fixed properly:
the skip is now unconditional on position, accepting the same already-
established trade-off (missing a rare typo in a capitalized word is
cheaper than corrupting a real name) for every position, not just some.
Verified zero regression on existing cases (peopel->people, overhear
preserved, the pre-existing lonly->only limitation unchanged).

Found, NOT fixed: "colony"->"colon" and "dated"->"date" (same vocabulary-
coverage-gap class as the already-documented "overhear" case, but the
compound-rescue check doesn't apply since the remaining piece isn't a
real word). Found, NOT fixed, a genuine parser limit: spaCy mis-tags
"discharges" as NOUN in "an industrial unit discharges effluent into...",
so `parse_conditional_rule` picked the wrong trigger verb for one of three
rules -- a real tagger error on this phrasing, not a mechanism bug.

**(2) Simplify a real ~3,043-word GDPR excerpt (the embedded fixture plus
3 more real articles fetched live from gdpr-info.eu) into plain English.**
Built `lab/common/plain_language.py` (closed 50+ term formal->plain
vocabulary table, same mechanism as `informal_register.py`). 61/88
sentences (69.3%) got at least one substitution, zero generative calls,
no meaning-changing substitution found on inspection.

**Honest conclusion: this achieves "simpler vocabulary," not "simple
English."** The document's longest, most convoluted sentences (Art. 49's
nested conditions) read almost as densely after substitution -- same
structure, friendlier words. This module has no mechanism to split a
sentence, flip passive to active, or reorder a subordinate clause, so it
cannot touch the actual source of complexity in a document like this one.
Predicted before testing, confirmed by testing, not assumed either way.

**(3) Extract "findings"/decisions from a fictional research/decision
memo.** Combined `deontic.py` (built for EXP-087, never wired into
anything until now) with a small new closed `DECISION_VERBS` table
(decide/conclude/approve/recommend/resolve/agree/reject/authorize/
determine), checked against the sentence's structural ROOT verb lemma,
promoted into `lab/common/decision_findings.py`. On a 45-sentence
synthetic memo: 14 flagged, checked by hand against the source --
precision ~93% (13/14), recall ~93% (13/14 of the memo's real decisions).

Two confirmed, unfixed failure modes, found by hand-checking rather than
trusting the count: a reported/embedded modal inside a described research
question ("studying whether the company SHOULD expand...") reads as a
real directive -- one false positive; a passive, non-modal decision ("A
follow-up review IS SCHEDULED...") is missed entirely since its ROOT verb
isn't in the closed table -- one false negative. A third, non-blocking
ordering artifact: a sentence with both a decision verb and an embedded
modal gets labeled by the modal, not the decision verb -- still correctly
flagged as a finding, just a less precise type tag.

**(4) Fetch a real company policy, apply it to fictional customer
cases.** Fetched Steam's real refund policy (store.steampowered.com/
steam_refunds/) via WebFetch, paraphrased for copyright. Tested
`rules.parse_conditional_rule`/`apply_rule` -- the exact mechanism already
validated for the rent-petition's Grounds section -- against a brand-new
domain.

**Honest conclusion: `lab.common.rules` does NOT generalize to a new
domain without modification -- the clearest negative finding of the
four.** Only 3 of 8 real-policy-derived sentences parsed, and all 3 were
ones deliberately rewritten into the canonical "If X, Y" shape first --
every sentence phrased the way the real policy actually reads (plain
declarative statements) failed outright, a structural mismatch against
`RULE_RE`, not a judgment call. A second, independent failure mode hit in
the same 8 sentences: an "if"-initial sentence with the right comma shape
still failed because its condition clause is a copula+adjective ("is
unused"), not a true VERB -- `_main_verb` requires `pos_=="VERB"`.

Case application got 4/4 right by OUTCOME, but one (Priya, denied for
requesting after the window closed) was right for the WRONG REASON: the
mechanism rejected her because her sentence's verb was "email" not
"request" (lemma-match brittleness), never because it evaluated the
actual "two weeks" time condition -- `apply_rule` carries
`condition_text` as inert text and never compares it against any
quantitative/temporal value. A case like "requested a refund one month
after purchase" would incorrectly match=True today. This is a real,
structural gap (no temporal/numeric condition checker exists at all),
not a phrasing quirk fixable by a bigger rule table.

**Net assessment across all four:** the zero-LLM architecture scales to
a genuinely long, real-structure document (1) without new fabrication
risk, and a real latent bug was found and fixed doing it. It also has
real, now-precisely-located limits that weren't visible in the smaller
examples tested earlier: vocabulary substitution alone cannot simplify
sentence STRUCTURE (2); the deontic/decision-verb combination is a good
first-pass flagger, not an unsupervised-accurate one (3); and the rule-
application mechanism that worked well on one hand-written legal-rule
shape does NOT transfer to real-world policy prose or to any condition
that depends on a quantity or a date, which is most of what real policies
actually turn on (4). All four reported as measured, not softened.

**Addendum, same day: independently reproducing experiment (4) found an
even sharper version of its own conclusion, and regenerating (1) found
one more vocabulary-coverage bug in `spellfix.py`, same class as
"overhear"/"colony", not yet fixed.** The fork-produced output files
above were cleaned up before they could be handed off, so each experiment
was independently re-run (not copy-pasted from the fork's own report) to
produce real deliverable files -- this re-run, done separately, is itself
a second, independent confirmation of each finding above, not a repeat
of the same run.

Policy-rule re-run (fresh fictional cases, fresh fetch of the same live
page): the rewritten canonical rule applied to 4 new fictional cases
(Amit/Priya/Rohan/Kavya) got 2 of 4 flatly WRONG, not just "right for the
wrong reason" -- Priya (10 hours of playtime) and Rohan (refund requested
a month after purchase) both wrongly `matched=True`, because every case's
extracted verb lemma is "play" and `apply_rule` never compares
`condition_text`'s "less than two hours"/"within two weeks" against the
case's actual numbers at all. A sharper demonstration of the same
structural gap, not a new one.

Petition re-run surfaced one more vocabulary-coverage bug while
regenerating: `candidates_for('commissioned')` returns only
`['commissioner']` -- "commissioned" (a correctly-spelled past-participle
verb form) isn't itself a single token in the flan-t5 vocabulary (same
subword-splitting root cause as "overhear"/"colony"), so spellfix wrongly
"corrects" it to "commissioner" (a different, real word, wrong part of
speech, wrong meaning) wherever it appears -- confirmed with a direct,
isolated test (`fix_sentence_joint('The unit was commissioned in mid
2025.')` -> "The unit was commissioner in mid 2025."). Common verb
inflections (-ed/-ing forms) splitting into subword pieces is likely a
much more pervasive instance of this bug class than the two single-word
anecdotes found before it, since English inflection is far more frequent
than compound nouns. Not fixed here -- flagged as a real, now-confirmed-
broader version of an already-known limitation, worth a real fix (e.g.
lemmatizing before the vocabulary check) before trusting this on
production text at any real volume.

## Follow-up, next day: the teach-tool concept registry -- "timeline"/"respondent addresses"/"acts and sections" built and proven with zero hardcoded, task-specific Python

Per the product-redesign request in `HANDOFF.md` ("Product redesign
proposal"): a new `lab.common.concept_tools` module extends
`lab.common.doc_tools`'s own "a template is DATA" rule to capabilities --
a new task ("give me a timeline", "give me the respondent's address",
"give me every act and section cited") is taught by adding one YAML file
under `lab/common/concepts/`, never by writing a new Python function named
after that task. Only 8 generic, data-parameterized primitives are Python
(`extract_by_label`, `extract_by_pattern`, `group_by_sentence`,
`sort_chronological`, `filter_records`, `select_fields`,
`resolve_addresses`, `count`); every concept YAML only composes them.

Also built: `lab.common.connector_config` (a YAML-declared data source --
`inline`/`records`/`file` fully implemented and tested below; `qdrant`/
`graph` wired to the already-built `lab.common.connectors` classes but
NOT live-tested this session, no server running), `lab.common.render`
(JSON/Markdown/.docx output), and `lab.common.engine.run` as the one
public entry point tying all three together.

**Tested end-to-end against one fictional fixture** (3 passages -- a
purchase date, a notice date with a statute citation, a filing date with
a second statute citation -- plus 2 party records, complainant and
respondent, each with a role and address):

| Ask | Concept matched | Result |
|---|---|---|
| "what is the emotional tone of this document" | none (embedding score 0.579, below the 0.6 threshold) | `ok=False`, `reason="unknown_concept"`, a "teach me" message -- no crash, no guess, no generative fallback |
| "give me a timeline of events" | `timeline` (alias match) | all 3 dated events, each with its sentence, correctly sorted chronologically |
| "what acts and sections are used in this petition" | `acts_and_sections` (alias match) | both statute citations found via the YAML-supplied regex pattern, rendered to Markdown |
| "give me the respondent addresses" | `respondent_addresses` (alias match) | exactly the one respondent record, projected to `{name, address}` -- the complainant correctly excluded |
| "give me parties name and address" | `parties_name_address` (alias match) | both records, projected to `{name, address}`, rendered to a real `.docx` file (`python-docx`, confirmed written to disk) |

All 5 asserted outcomes passed on the first clean run after fixing two
wrong-API-signature bugs caught by running it, not by inspection:
`lab.common.ingest.chunk_document`'s real signature is
`(raw_text, max_words_per_chunk=120)`, not `(text, doc_id=...)`, and
`QdrantConnector`/`GraphConnector` take `collection` (and an on-disk
`base_dir`), not a `url`, and `QdrantConnector.search` returns
`[{"passage": {...}, "score"}]`, not a flat passage list -- all three
assumptions were wrong on the first draft, corrected by reading
`lab/common/connectors.py` and `lab/common/ingest.py` directly before
re-running, not by guessing.

**What this does and does not prove.** It proves the core claim -- a new
capability is addable as data, with a graceful, non-hallucinating failure
for anything not yet taught -- on one small, controlled fixture with
unambiguous aliases. It does NOT yet prove: embedding-fallback matching
on an ask that uses none of a concept's literal aliases (every ask in
this test happened to contain an exact alias, so `match_concept`'s
alias-substring path fired every time; the embedding path only fired for
the one deliberately-unmatched ask, correctly, but that is one data point,
not a calibration); `CONCEPT_TAU=0.6` is provisional, same status as
`method_teaching.INTENT_TAU` before it; the `qdrant`/`graph` connector
branches (code written, not run against a live store); and nothing here
is wired into `brain.reason` or `longform.write_long_document` yet -- it
is a new, separate entry point (`lab.common.engine.run`), not a
replacement for the existing pipeline.

`requirements.txt` updated to list `PyYAML` (new, for the concept/
connector YAML files) and `python-docx` (already a real runtime
dependency of `lab/common/docx_writer.py`, just never pinned -- a fresh
clone following `requirements.txt` alone would not have had it either).

## Follow-up, same week: making the teach-tool layer actually industry-blank, and testing it against every open HANDOFF.md issue

The project owner's explicit objection to the first version above: the
four worked concepts (timeline/acts_and_sections/respondent_addresses/
parties_name_address) shipped inside `lab/common/concepts/`, the
directory `concept_tools.load_concepts()` scans by default -- so a fresh
install of this "product" would have come with legal-petition vocabulary
baked in, exactly the kind of hardcoding the teach-tool layer was built
to eliminate. Two changes, both verified, not just asserted:

1. **The four proof concepts moved to `lab/common/concepts/examples/`**,
   a subdirectory `load_concepts()` never scans (it globs `CONCEPTS_DIR`
   non-recursively). Verified directly: `concept_tools.load_concepts()`
   now returns `[]` on this exact codebase. A fresh install, any
   industry, starts with **zero** registered concepts and teaches its
   own the same way these four examples were taught -- there is no
   longer a legal-domain default to un-teach.
2. **`resolve_addresses` (a primitive literally named after one field)
   retired in favor of `structure_field(field, parser)`** -- `parser` is
   now YAML data (today: only `"address"` is registered in
   `STRUCTURE_PARSERS`, but a new parser is a registry entry, not a new
   primitive signature), matching the discipline `extract_by_label`
   already set with its `label` argument. No shipped example used the
   old primitive, so this was a pure generalization, not a behavior
   change for any existing concept.

**A fifth, deliberately non-legal example was added to test genericity
directly: `examples/refund_eligible_cases.yaml`**, plus a new primitive,
`filter_by_condition(field, operator, value)` -- a generic numeric/
duration comparison (`less_than`/`at_most`/`greater_than`/`at_least`/
`equal_to`, backed by `lab.common.calc.compare_numbers`, with duration
units hours/days/weeks/months normalized to a common base so "14 days"
and "2 weeks" compare correctly against each other). This directly
targets HANDOFF.md's own sharpest named finding: **`lab.common.
rules.apply_rule` matches a policy rule on its trigger verb lemma only
and never evaluates the rule's quantitative/temporal condition at all**
-- on the real Steam refund policy ("played less than two hours and
refunded within two weeks"), that gap got a 10-hour-playtime case and a
refunded-a-month-late case both wrongly `matched=True`.

Reconstructed that exact scenario as a 4-case fixture and ran it through
`engine.run` with only `filter_by_condition` steps (no new domain-named
Python): the correct single eligible case was returned, and **both of
HANDOFF's named wrong cases were correctly excluded** -- a direct,
reproducible fix for that bug, achieved through the generic design
layer rather than by patching `rules.py` in place. A bug was found and
fixed while building this test, not hidden: the first version of
`filter_by_condition` converted a bare, unitless record value (`30`, no
unit) by leaving it unconverted while converting the YAML threshold
("14 days") to hours, so `30 < 336` passed when it should have failed on
`days_since_purchase`. Fixed by having a bare record value inherit the
threshold's own unit (a "30" compared against "14 days" is 30 days, not
30 of nothing) before any conversion -- caught by the test asserting the
exact expected case-id set, not by eyeballing the output.

**Honest scope of that fix -- what it does NOT solve.** HANDOFF.md names
two distinct failures for `rules.py`: (a) the quantitative/temporal
condition is never checked (fixed above, by the generic design), and
(b) `parse_conditional_rule`/`RULE_RE` fail to parse real policy prose
at all (0 of 8 real sentences in the independent re-run). This fix
**sidesteps (b) rather than solving it** -- the policy is declared
directly as a YAML recipe of `filter_by_condition` steps, never parsed
from English prose. That is a legitimate product shape (a person or a
future bounded proposer encodes a policy once, as data), but it is not
"rules.py now parses arbitrary policy text," and claiming otherwise
would overstate this.

**Every other open issue named in HANDOFF.md's "four big scale-tests"
and redesign sections was checked against this design, not just listed
-- most are NOT solved by it, and here is why, specifically:**

| HANDOFF issue | Verdict | Why |
|---|---|---|
| `rules.py` never checks quantitative/temporal conditions | **Solved** (generically) | `filter_by_condition`, proven above |
| `rules.py` doesn't parse real policy prose (0/8) | **Sidestepped, not solved** | policy is declared as YAML, never parsed from prose |
| `decision_findings.py` reported-question false positive | Not solved | needs syntactic (ccomp/xcomp) awareness; no such primitive exists in `GENERIC_REGISTRY` |
| `decision_findings.py` passive-decision false negative | Not solved | needs embedding-neighbor verb widening; different subsystem, untouched |
| `spellfix.py` verb-inflection gap | Not solved | token-level typo correction; unrelated to concept/recipe matching entirely |
| `plain_language.py` can't split/reorder sentences | Not solved | would need a new sentence-restructuring primitive (e.g. splitting on `connectives.find_connectives`); not built |
| `sentence_completeness.py` blind spots + `no_verbal_root` | Not solved | pre-generation completeness gate; different subsystem |
| Reference resolution is pronoun-only (`relationship_graph._resolve_antecedent`) | Not solved | this layer never resolves references; that work is still unstarted (point 2 of the redesign proposal) |
| `store.py` streaming upsert / always-hybrid search | Not solved | data layer; untouched by this session |
| Self-expanding reasoning core (point 3 of the redesign) | Not solved | this teach-tool layer is the *tools* layer, not the reasoning core; no budget/cycle/coverage loop exists yet |
| `doc_tools.py` per-section template contracts | Not solved | not built |
| Keep/delete pass on the 8 dormant modules | Not solved | not attempted this session |

**What this does prove, honestly:** the genericity objection itself is
fixed and verified (empty shipped registry, no primitive named after a
field or a task), and the single sharpest, most architecturally-relevant
open bug (rules.py's structural blindness to quantitative/temporal
conditions) is fixed through this same generic design, on a
deliberately different industry than the four original examples. It does
NOT prove the teach-tool layer is a general fix for every open issue in
HANDOFF.md -- nine of eleven other named issues live in subsystems
(language-brain normalization, the reasoning core, the data layer,
template contracts, dormant-module cleanup) this layer was never scoped
to touch, and none of them moved as a side effect of this work.

## Follow-up, same day: three of the nine untouched issues fixed directly in their own module (not via the concept layer), one attempted and confirmed NOT to work

The project owner asked for the remaining nine issues to be attempted
directly, one at a time, and to be told plainly which ones don't have a
confident fix rather than have one guessed. Four attempted so far, each
measured against the exact example HANDOFF.md itself named, not a
simplified stand-in:

**1. Fixed -- `decision_findings.py`'s reported-question false positive.**
"The research team ... studying WHETHER the company should expand" was
wrongly flagged `obligation` because `classify_deontic` only checked a
modal's own negation, never whether the modal's clause is itself a
reported/hypothetical question. Fix, in `lab.common.deontic
._is_reported_question`: a modal's governing verb with a sentence-
structural `mark` child lemma "whether"/"if" is an embedded question,
not a direct assertion -- purely structural, no closed list of
"reporting verbs" (study/wonder/debate/...) to maintain. Caught live
while testing: spaCy's parser realizes this identical shape as `ccomp`
for one governing verb and `advcl` for another on an otherwise
structurally identical sentence ("studying whether..." vs "debated
if...") -- checking `ccomp` alone silently missed the second until a
second test sentence exposed it; both are now accepted. Verified on 7
cases: the two reported-question shapes are correctly suppressed; a real
conditional directive ("IF a claim is filed within 30 days, the vendor
MUST respond"), a "that"-complement directive, and three ordinary modal
sentences are all unaffected. The existing EXP-087 fixture (6 hand-built
cases + the real 103-sentence GDPR document) was rerun end to end:
6/6 hand-built still correct, and the GDPR document's modal
classification is byte-identical (56/103 sentences, `{permission: 7,
obligation: 43, prohibition: 6}` -- exactly `data/
exp_087_deontic_classification/results.json`'s own committed numbers) --
this fix changes nothing on the one real document already validated,
only the specific reported-question pattern neither real fixture
happened to contain.

**2. Attempted, measured, does NOT work -- `decision_findings.py`'s
passive-decision false negative.** HANDOFF.md's own suggested fix was
"widen past the closed `DECISION_VERBS` lemma list using embedding
nearest-neighbors, not another hardcoded entry." Tried exactly that,
against `bge_embed` (the same encoder this project already uses
elsewhere): measured the cosine similarity between the missed verb
("schedule") and the existing `DECISION_VERBS` set, and between several
genuinely unrelated verbs ("eat", "walk", "write", "describe") and that
same set. Result: NO clean separation exists. "schedule" scored 0.629;
"describe" (a verb this check must NOT fire on) scored HIGHER at 0.777;
"eat" scored 0.671, also higher than "schedule". Tried a second encoding
(short templated phrases, "a follow-up review is scheduled" vs "the
committee decided this matter") in case bare single-word embeddings were
the problem -- same result, "schedule" at 0.662 vs "eat" at 0.659,
statistically indistinguishable. This is the same kind of negative
finding this project has measured before (EXP-029: real embeddings lost
to TF-IDF on a harder retrieval test) -- embeddings are not a universal
hammer, and this is not the place they hold up. **Not fixed; no
confident deterministic alternative identified either.** Flagged back to
the project owner rather than shipping an unsupported fix.

**3. Fixed -- `spellfix.py`'s verb-inflection gap.** `candidates_for(
"commissioned")` returned only `["commissioner"]` (one true edit away),
silently swapping a correctly-spelled past participle for a different,
wrong-part-of-speech word, because "commission" is a single flan-t5-
small vocabulary token but "commissioned" is not. Fix, `_lemma_known`:
lemmatize the word first (`lab.common.rules._parser`, already a project
dependency) and check the LEMMA against vocabulary before falling
through to edit-distance candidate generation -- exactly the fix
HANDOFF.md named ("lemmatize before the vocabulary check"). Verified
directly on both regular inflections ("walked"->"walk", "studies"
->"study") and irregular ones ("ran"->"run", "children"->"child"), with
every real typo in this file's own test set (herd/realy/lonly/peopel)
confirmed still caught with the correct word still among the candidates
(heard/really/lonely/people respectively) -- a pure precision gain, not
a trade-off against recall on the typos this module was already
measured against.

**4. Fixed -- `sentence_completeness.py`'s two named blind spots, plus
the still-generating `no_verbal_root` case.** Both new checks were
designed from real spaCy parses, not assumed:
- Gerund fragment ("Running quickly down the street.") -- the ROOT is
  tagged `VBG` (non-finite) with no finite `aux` child to anchor it;
  "He IS running..." has a finite `aux` ("is", tag `VBZ`) and correctly
  stays `complete`. An imperative ("Submit the form.") is unaffected --
  its ROOT is tagged `VB`, the ordinary base form English imperatives
  always use, never `VBG`.
- Lone subordinate clause ("Because the tenant did not pay.") -- the
  ROOT has a sentence-INITIAL `mark` child (the subordinator itself).
  Checked on both shapes before trusting this: in a real two-clause
  sentence ("Because X, Y."), spaCy's ROOT is always the independent
  clause's own verb, with the subordinate clause one level down as an
  `advcl` -- never at ROOT -- so this never misfires on a genuine
  multi-clause sentence that happens to use "because" correctly.
- `rewriter_backends.rewrite_unit` now also skips `generate()` for the
  `no_verbal_root` reason specifically (a heading or lead-in fragment,
  "correctly incomplete BY DESIGN" per this module's own docstring),
  the same way it already skips it for `already_complete` -- verified
  directly on both of this project's own real examples ("Art. 83 GDPR"
  and "For the purposes of this Regulation:") without invoking
  `generate()` at all. The other two new reasons (`gerund_fragment`,
  `lone_subordinate_clause`) deliberately still fall through to
  `generate()` -- unlike a heading, those ARE broken fragments a
  rewrite could legitimately try to fix, so they are not given the same
  skip.

13 hand-built regression cases run across both new checks (gerund/
imperative/subordinate/multi-clause/heading/typo-laden-but-structurally-
complete), all correct; no existing committed `results.json` for this
module exists to diff against (it was built and measured ad hoc during
the four big scale-tests, not as a numbered EXP), so the EXP-087 rerun
above is the only available before/after regression evidence this
session, and it shows zero change on the one real document tested.

## Follow-up, same day: an environment mismatch found and fixed, then a project-wide parser upgrade (en_core_web_sm -> en_core_web_trf), measured, not assumed

**Environment finding.** Every command run this entire session (this
conversation's earlier turns included) used the shared `C:\Python311`
install, not this project's own isolated `.venv` (created 2026-11-01,
per this project's own standing rule that new/risky dependencies belong
there). Checked directly: the two have different package versions
(`.venv`: torch 2.15.0, spacy 3.8.18, transformers 4.46.3; shared
install: torch 2.4.1). Both are CPU-only (`torch.cuda.is_available()` is
`False` in both). All work from this point on in this session ran
against the `.venv`; the shared install was left untouched, not cleaned
up, since the project owner hasn't said what to do with it yet.

**Research, before touching code -- what actually helps "language logic
conversion" get more robust, not hardcoding more rules:**
1. A stronger parser is itself part of the fix. The ccomp/advcl
   inconsistency found earlier this session (the identical "studying
   WHETHER X should Y" clause shape parsed two different ways depending
   on the governing verb) is parser noise, not a gap more hand-written
   rules close. `en_core_web_sm`'s own published unlabeled attachment
   score is ~0.918; `en_core_web_trf` (spaCy's RoBERTa-based transformer
   pipeline)'s is ~0.953 -- a real accuracy gain, same `.dep_`/`.tag_`/
   `.lemma_` API, zero new hardcoding.
2. A real pretrained grammaticality classifier exists and is NOT
   generative: CoLA-trained RoBERTa sequence classifiers (e.g.
   `textattack/roberta-base-CoLA`), ~85% reported accuracy, trained on
   10,657 real labeled sentences -- the same category of model this
   project already trusts (bge-small, DeBERTa-MNLI), not a FORBIDDEN.md
   violation. Not yet wired in; identified as the right tool for
   catching grammar problems this project hasn't hand-found yet, rather
   than hand-writing a rule for every one discovered by accident.
3. Bidirectional NLI entailment (original<=>rewrite, both directions,
   no contradiction) is the established pattern for verifying any
   sentence transformation preserves meaning -- this project already
   has the model (`real_nli`, used by `rules.semantic_apply_rule`).
   Identified as the gate any future sentence-splitting/passive-active
   transform must pass before being trusted; not yet built.
4. Passive-to-active voice conversion has no mature deterministic tool
   -- the one rule-based academic attempt found caps at ~50% accuracy.
   Confirmed, not assumed. Any future attempt here needs the NLI gate
   above, not confidence in the rules alone.
5. Sentence-splitting on subordinate/coordinate clauses has a real
   published rule set (DisSim, Niklaus et al., INLG 2019 -- 35 hand-
   crafted English rules over dependency structure); the reference tool
   is Java-only, not importable here, but the rule set itself is
   legitimate grammar methodology, the same category as `connectives.py`'s
   own PDTB-based rules, not domain-vocabulary hardcoding. Not yet
   ported.

**Parser upgrade, implemented and measured.** `lab.common.real_models`
now has `PARSER_MODEL_NAME = "en_core_web_trf"`, loaded by a NEW, separate
cache (`_parser_pipeline`) from `ner_pipeline()`'s own cache -- the two
were split apart specifically so this upgrade never silently changes
`lab/exp_032_real_multihop/run.py`/`lab/exp_033_real_entities/run.py`'s
closed, already-measured `.ents`-based output; `ner_pipeline()` still
loads plain `en_core_web_sm`, byte-for-byte as before. `sentence_
completeness.py`'s own separate, duplicate `en_core_web_sm` load was
also found and fixed to go through this same shared pipeline (it
previously claimed to reuse `real_models`' loaded pipeline but actually
loaded a second, independent copy of the same model).

CPU latency measured directly on this machine (no GPU) before
committing to the swap, not estimated from spaCy's own published figure
(different hardware): a representative ~3,000-word sample parsed in
0.98s on `en_core_web_sm` (3,132 words/s) vs 4.20s on `en_core_web_trf`
(733 words/s) -- about 4x slower in absolute terms, negligible against
`longform.write_long_document`'s own already-measured ~63.5s/document
(AUDIT.md, EXP-081).

**A real accuracy win found immediately, not theoretical:** rerunning
EXP-087 (6 hand-built cases + the real 103-sentence GDPR document) with
the new parser changed the real-document result from 56/103 sentences
with a recognized modal (`{permission: 7, obligation: 43, prohibition:
6}`, the previously-committed number) to 57/103 (`{permission: 7,
obligation: 44, prohibition: 6}`). Diffed sentence-by-sentence (both
parsers run side by side) to find exactly which one changed, not just
accepted the aggregate delta: sentence 56, GDPR Article 33's breach-
notification clause -- "the controller SHALL without undue delay and,
where feasible, not later than 72 hours after having become aware of
it, notify the personal data breach to the supervisory authority..." --
a genuine, legally load-bearing obligation that `en_core_web_sm`
completely missed (likely losing the long-range "shall"-to-"notify"
attachment across the interposed adverbial clause), which
`en_core_web_trf` correctly catches. `data/exp_087_deontic_
classification/results.json` updated to this new, re-verified number
(its `models_used` field corrected to name `en_core_web_trf`); the 6/6
hand-built cases are unchanged. Per `AGENT.md`'s own rule for a new
real-model substitute, both numbers are disclosed here, not just the
new one.

All of this session's other regression tests (the `deontic`/`spellfix`/
`sentence_completeness` cases, the concept-registry `engine.run` proof)
were rerun in the `.venv` after this swap and pass unchanged.

`requirements.txt` updated: `spacy-transformers>=1.3` added, and
`en_core_web_trf` download instructions added alongside the existing
`sm`/`md` ones.

**Not yet done**: the CoLA-classifier signal, the NLI bidirectional-
entailment transform gate, sentence-splitting, and passive-to-active
conversion are all identified above but not built. Removing the
hardcoded domain-vocabulary tables (`entities.py`'s live ones;
`method_teaching.py`/`proposals.py`/`provenance.py`/`decision_findings.py`'s
dormant ones) and wiring `plain_language.py` (plus whatever sentence-
restructuring layer gets built) into `brain.reason` -- both explicitly
asked for this same turn -- have not been started either.

## Follow-up, same day: the hardcoded tables moved to data, a gated grammar-structure layer built, both wired into brain.reason

**Hardcoded vocabulary moved to `lab/common/lexicons/*.yaml`** (loaded by
the new, tiny `lab.common.lexicon.load_lexicon`, cached per process --
NOT the same mechanism as `concept_tools.load_concepts`, which teaches a
capability; this loads a closed VOCABULARY an existing primitive already
needs): `entities.py`'s `ORG_SUFFIXES`/`PLACE_LAST`/`NOT_PERSON` (all
LIVE, used by every `detect_primary` call), `plain_language.py`'s
`PLAIN_TABLE`, `decision_findings.py`'s `DECISION_VERBS`. A real overlap
bug fixed along the way, not just relocated: `entities.py` used to hand-
type the business-suffix vocabulary TWICE (once for `ORG_SUFFIXES`'s
membership check, once inside `ORG_RE`'s regex alternation) -- exactly
the "two modules/structures independently implementing the same
decision" failure class this project's own audit discipline looks for.
Both are now built from one file (`lexicons/org_suffixes.yaml`); the
regex is rebuilt from the file's own `regex` field per entry, verified
byte-identical to the original hand-written pattern before trusting it.
`NOT_PERSON`'s own comment is explicit that this is a RELOCATION, not a
fix -- it is still a denylist of this project's own fixture phrases, not
a generalizable rule; the proven, more general fix (`detect_primary(...,
use_real_ner=True)`, EXP-080) already exists in the same module and
still defaults to off, unchanged.

**`method_teaching.py` is NOT promoted** -- its own `_NOUN_TO_LABEL`/
`_WH_TO_LABEL`/`_INTENT_TO_PLAN`/`_INTENT_EXEMPLARS` are exactly the
hardcoded ask-vocabulary pattern `concept_tools.py` was built to retire,
and that replacement is now proven, not just proposed. Flagged in its
own docstring as a delete candidate rather than half-genericized in
place, which would just build a second, parallel copy of what
`concept_tools.py` already does. `proposals.py`'s `GENERIC` set and
`provenance.py`'s `BACKGROUND_FACTS` (literal trivia, "capital of
france": "Paris") were deliberately left untouched: both are confined to
old, closed experiments (EXP-019, EXP-013/038) that import them by
name, same discipline as not silently changing EXP-032/033's `.ents`
output when the shared parser was upgraded.

**New module, `lab/common/grammar_logic.py`**: a bidirectional-NLI
`preserves_meaning` gate (the pattern researched and cited in this
file's earlier entry), `passive_to_active` (modal passive + explicit
"by"-agent only -- "the notice shall be given by the Lessor" -> "the
Lessor shall give the notice"), and `split_on_connective` (splits at a
`connectives.find_connectives` match for the two supported dependency
shapes, `mark+advcl` and `cc`). Two real bugs found and fixed by
testing against real sentences, not assumed correct from the design:
(1) `find_connectives`'s own `anchor_text`/`clause_text` fields serve
its original discourse-classification purpose, not splitting -- using
them directly produced a sentence that repeated the entire original
text with a bare connective word prefixed ("And. The product was found
defective and the complainant sent a notice..."), which the NLI gate
did NOT catch (the degenerate candidate still trivially entails the
original); fixed by computing both clause spans directly from the
dependency tree instead, and adding a cheap `sentence_completeness.
is_complete_sentence` check on each half BEFORE the NLI call, specifically
to catch this class of degenerate split structurally. (2) The first
version of `passive_to_active` always appended every remaining child
after the new object in original token order, which is only correct for
a TRAILING modifier ("to the Lessee") -- a sentence-initial adverbial
("Despite this, the notice shall be given...") landed mid-sentence
instead ("...give the notice despite this to the Lessee"); fixed by
partitioning a verb's other children on whether they appeared before or
after the passive subject in the original sentence, keeping that
ordering on the rebuild.

Also measured, not hidden: `because`-clause splitting sometimes fails
the NLI gate even on a seemingly clean example -- splitting "Because X,
Y" into "X. Y." measurably weakens the backward entailment (0.7366,
just under the 0.75 threshold) since the split loses the explicit
causal link the original sentence carries. This is the gate correctly
being cautious, not a bug to work around.

**Wired into `brain.reason` via a new opt-in `plain_english` parameter**
(default `False`, same shape as `use_real_ner`/`use_real_nli`/
`use_repair`), threaded through `reason() -> _reason_once() ->
longform.write_long_document() -> plain_language.simplify_document`
(the new combined entry point: vocabulary substitution, then per-
sentence `passive_to_active` then `split_on_connective`, both gated).
Verified end to end through `brain.reason` itself (not just the
individual functions in isolation): with `plain_english=True`, a real
ask correctly threads all the way through and the rendered leaf shows
both a vocabulary substitution and a passive-to-active conversion, with
full per-sentence diagnostics recorded in `rewrite_diagnostics`. With
the flag left at its default, `rewrite_diagnostics` is confirmed
unchanged except for one new, always-`None` `plain_english_result` key
-- zero behavior change for any existing caller.

**EXP-081 (the real GDPR document pipeline) was rerun as a broader
integration check** (not just this new code in isolation) -- it
completed with no errors and the same 0/18 fidelity-pass story already
on record, but `consistency_flags` changed from 13 to 16, a real,
measured side effect of the earlier parser upgrade (the cross-page
consistency checker also runs on the shared, now-upgraded dependency
parser). Disclosed, not silently absorbed into the committed
`results.json`: this project's own existing follow-up note on that same
checker ("false-positive rate... not measured here, only observed
qualitatively") already flags it as unverified for precision, and this
session does not change that -- the new count is reported as measured,
not claimed as an improvement.

## Follow-up, next day: four of the five remaining open items fixed and measured; the fifth (the self-expanding reasoning core) deliberately not attempted, with reasoning

User's direct challenge, given the four previously-"genuinely untouched"
items plus the EXP-081 side effect: "these can be fixed now... check why
these are not getting fix? and fix that side effect too." Investigated
each on its own merits rather than assuming the newly-built grammar/NLI
infrastructure would automatically cover them -- two were, two needed
their own real design work, one is reported as deliberately not
attempted.

**1. Pronoun/coreference gap (`relationship_graph.py`) -- fixed, with a
real correction found mid-design.** First attempt: "role-parallelism"
(a pronoun prefers an antecedent that played the SAME grammatical role
it itself plays -- a subject pronoun prefers a previous subject), the
standard centering-theory heuristic. Tested directly against this
project's own two named cases (AUDIT.md, "pronoun/coreference gap") and
found WRONG on the first one: this project's own motivating example is a
payment CHAIN ("X gave Y money, Y gave Z money..."), where the correct
antecedent is deliberately the PREVIOUS OBJECT, not a same-role match --
parallelism gets this backwards. Replaced with SALIENCE (was the
candidate a stated argument -- subject OR object -- of the immediately
preceding fact at all, vs. merely named inside an incidental/subordinate
clause the triple extractor never bound), tiebroken by recency, with a
soft pronoun-type-compatibility filter and an optional bge-embedding
tiebreak. Re-verified directly: the payment-chain case still resolves
exactly as before (salience ties between subject and object, recency
breaks it the same way the old heuristic did); the adversarial
subordinate-clause case ("Alice Smith confirmed that Bob Jones had
missed the deadline. She gave Carol Lee $500." -- old heuristic
resolves "She" to Bob Jones, wrong) now resolves correctly to Alice
Smith, because Bob Jones was never a real argument of the extracted
fact, only an incidental mention. `build_relationship_graph`'s new
`use_reference_binder` (default False) and `use_embedding_tiebreak`
(default False) keep every existing caller (`article_tool.py`, the only
one) on the exact old heuristic unless it opts in.

**2. Data layer -- streaming upsert and always-hybrid search
(`store.py`) -- fixed, honestly scoped per leg.** `Store.upsert` appends
new passages without the caller re-supplying every earlier one, but the
cost is reported per-leg, not claimed uniform: `RealBgeIndex`'s dense
leg is genuinely incremental (`bge_embed` only ever runs on the NEW
passages -- one passage's embedding never depends on the rest of the
corpus); the lexical `Index`'s TF-IDF vectorizer and the entity graph
have no such property (no online-vocabulary update in scikit-learn;
`build_entity_graph`'s own docstring already calls rebuilding "the
cheap part") and are refit over the full passage set. `Store.search` now
fuses both legs by Reciprocal Rank Fusion whenever both exist, instead
of `prefer_bge` picking exactly one and discarding the other -- the
direct structural fix for EXP-029's own finding that real bge embeddings
can lose to plain TF-IDF on a harder retrieval test. Verified live: a
3-passage store, upserted with a 4th, correctly re-ranks a query toward
the new passage; `expand_entity` after the upsert correctly reaches the
new passage through the rebuilt graph; `ingest_and_store` +
`ingest_and_upsert` round-trip from raw text with no hand-built
passages. `Store` had zero fan-in before this change and still does --
zero regression risk, by construction.

**3. Per-section template contracts (`doc_tools.py`) -- fixed, wired
into both `write_long_document` and `brain.reason`.** `check_section_
contract`/`check_template_contracts` check an OPTIONAL, per-section
`contract` key (`required_labels` -- AND, `required_labels_any` -- OR,
`min_findings`, `max_findings`) against `entities.detect_primary`'s
labels over the findings actually routed to that section -- no new
model, no new hardcoded keyword table, and a section with no `contract`
key is simply never checked. Added real contracts to both shipped
templates (`legal_notice.json`: Notice Header needs a person AND a
date; Deadline and Consequence needs a date OR an amount -- checked
directly, since a duration deadline like "within 15 days" is caught by
this project's own AMOUNT_RE, not DATE_RE, so an AND here would have
been a false-flag risk; `college_notes.json`: every section needs at
least one finding). Wired into `write_long_document`'s new
`contract_violations` return field (`None` when no `template_id`, `[]`
when checked and all passed, else the failing sections), and threaded a
new `template_id` parameter all the way through `brain.reason`/
`_reason_once` so this is reachable from the one real entry point, not
just a direct `write_long_document` call. Verified end to end via
`brain.reason(ask, passages, template_id="legal_notice")`: a findings
set missing a date in the header and missing any Demand finding
produces exactly those two violations; the default (`template_id=None`)
path is confirmed byte-identical to before this change.

**4. EXP-081's consistency_flags side effect -- actually fixed, not
just disclosed, and the fix is bigger than the one experiment.**
Reproduced the real GDPR fixture directly and printed every one of the
16 flagged pairs' full source sentences, then ran real bidirectional
NLI (`real_encoders.real_nli`) between each pair: 15 of 16 score under
0.02 contradiction probability -- a generic legal actor ("the
controller"/"the data subject") stating a DIFFERENT, non-conflicting
obligation under a different GDPR article, sharing only a subject+verb
lemma. Exactly the failure mode EXP-081's own follow-up already named
("false-positive rate on repetitive legal text... not measured here")
and exactly what the parser upgrade made WORSE (more triples extracted
= more coincidental subject+verb matches = more flags), not better --
the parser upgrade didn't cause a new kind of bug, it amplified an
existing, already-named precision gap. Fix: `WorkingMemory.check_and_
remember_page`'s new `use_real_nli` parameter (default False) requires
the two underlying sentences to clear a real NLI contradiction
threshold (either direction) before keeping a candidate flag, reusing
exactly the sentence text already carried in each triple's own `raw`
field (no new storage, no violation of this module's "never the page's
full text" rule). Measured on the identical fixture: 16 flags -> 1,
keeping precisely the one pair (a fee-charging clause under two
different articles) that plausibly deserved a second look. Threaded
through `write_long_document`'s existing `use_real_nli` flag (the same
flag that already gates the rewriter's own real-NLI fidelity check, not
a new one) -- default False confirmed to reproduce the original 16
flags exactly; `use_real_nli=True` confirmed to produce the 1.

**5. The self-expanding reasoning core -- deliberately NOT attempted
this pass, reported rather than rushed.** HANDOFF.md's own redesign
proposal names this as generalizing `inference.forward_chain`'s
rule-only fixpoint loop into the PRIMARY mechanism replacing `brain.
_reason_once`'s fixed, `plan_stages`-computed stage order -- admitting
`qa.answer_with_real_qa`, `nli.judge`, the new reference-binder, and
`rules.apply_rule` as interchangeable expansion moves against a growing
node set, with `budget.cap_depth`, `relationship_graph.find_cycles`,
and `verify.coverage_check` as the required safety controls. This is
not a wiring task like the four above -- it is a different CONTROL
PHILOSOPHY for the single most load-bearing function in this project.
`plan_stages`'s own docstring records the project owner's explicit
reasoning for the CURRENT design ("give one simple prompt and system
have to perform... first create full plan and than execute... it will
keep it in control") -- a fixed plan computed once, before anything
runs, is the deliberate opposite of a loop that re-derives which
operator fires each round. Every one of this project's ~90 experiments
that calls `reason()` depends on today's stage-dispatch order; rewiring
it without a dedicated labeled set to verify no dispatch regression
would be exactly the kind of change this project's own discipline
exists to prevent (measure before trusting, never guess). HANDOFF.md's
own proposal already scopes this as "its own phase after the four-layer
core is validated," not a same-session wiring change -- left genuinely
undone, not quietly skipped.

## Follow-up, next day: tested the self-expanding core's own motivating
scenario directly before designing anything -- no dynamic loop needed,
two unrelated latent bugs found and fixed instead

Before building any generalization of `plan_stages`'s fixed order, the
project owner asked to first find a way to CONTROL dynamic reasoning,
then build it. Rather than design the control mechanism in the
abstract, the actual scenario motivating it was tested directly: does
today's single fixed pass already handle a derived fact feeding an
identity-style answer (Rohan kills Arun -> crime+jail -> license
suspended; ask "who will have their license suspended?")? Measured: it
already does, correctly, with no new code -- `forward_chain`'s own
bounded (`max_steps=10`), deduplicated, fully-traced fixpoint loop
already runs inside the `rule_application` stage, and `plan_stages`
already computes EVERY relevant stage's signal from the ask text up
front (not from passages), so `identity_extraction` and `rule_
application` both fire in the same pass and their `answer_parts`
concatenate -- `reason()` already returns "Furthermore, Rohan suspend
their license." with zero dynamic re-planning. There is no capability
gap here for a dynamic core to close.

Pushed one step further looking for a genuinely harder case -- a
derived rule consequence (a threshold rule's fee) feeding back into a
DIFFERENT stage (`total_computation`) within the same pass -- and the
attempt surfaced two unrelated, pre-existing bugs instead of a control
problem:

1. `_find_rule` ([brain.py](lab/common/brain.py)) tried `parse_
   conditional_rule` (verb shape) before `parse_threshold_rule`
   (threshold shape). `THRESHOLD_RULE_RE` requires a possessive
   subject + comparison keyword + number -- strictly more specific
   than `RULE_RE`'s generic `^if <anything>, <anything>.` -- but every
   existing threshold-rule fixture in this repo (EXP-057/058/059/060/
   066/068/069/070/094) prefixes the sentence with a label ("Company
   policy:", "Hospital policy:", ...) that `RULE_RE`'s `^\s*if\s+`
   anchor already rejects, so the collision was never exercised. A
   bare "If a customer's total exceeds $500, a $50 fee applies."
   sentence (no label prefix) got misclassified as a verb rule and
   silently produced no answer. Fixed by trying the more specific
   pattern first -- zero regression risk, since a verb-rule sentence
   never matches `THRESHOLD_RULE_RE`'s shape anyway.
2. `total_computation`'s money-scan summed `AMOUNT_RE` matches from
   EVERY passage in `scoped`, including rule-shaped passages
   themselves -- a threshold rule's own stated threshold/fee amounts
   got counted as if they were additional invoice line items. Every
   existing fixture avoided this by accident (disambiguation's group
   filter excludes the ungrouped policy passage from `scoped` before
   the sum runs), not because of any deliberate exclusion -- an
   ungrouped rule sitting alongside ungrouped facts (no disambiguation
   group to filter it out) had its own numbers summed in, inflating a
   $550 total to $1,100. Fixed the same way `_reason_once`'s own
   fact_passage lookup already excludes rule-shaped passages (same
   precedent, same reasoning) -- skip any passage that parses as
   either rule shape before scanning it for amounts.

Both fixes are narrow, measured, zero-regression (confirmed by rerunning
17 existing experiments touching rule-dispatch, totals, or both --
EXP-026/053/058/060/066/068/069/070/078/081/082/084/085/089/091/094/097
-- all still `all_correct: true`, identical to their prior recorded
results). Neither fix is a dynamic-control mechanism; they are exactly
the kind of latent edge-case bugs the project's own discipline expects
to surface only once a case outside the existing fixtures' phrasing is
actually tried, not something a generic loop would have caught or
needed.

**Conclusion on the self-expanding core, now with direct evidence
rather than only architectural caution: there is no concrete capability
gap left that justifies building it.** The multi-hop scenario that
motivated it already works, bounded and traced, through the existing
fixed-plan + forward_chain combination. The one adjacent case that
looked like it might need cross-stage dynamic feedback (a derived fee
updating a total) turned out to be blocked by ordinary parsing bugs,
now fixed, not by the control-flow architecture. The deliberately-not-
attempted decision above stands -- not as a postponed task, but as a
closed question: nothing found in this session's direct testing asks
for it.

## Second follow-up, same day: a bounded tool router, built after the
project owner pushed back on scope -- not fact-chaining, the ability to
invoke any existing tool (reasoning, related-case retrieval, document
writing) in whatever sequence a given ask needs

The conclusion above ("nothing found asks for a dynamic core") answered
a narrower question than what the project owner actually wanted: not
"does multi-hop fact-chaining need a loop" (it doesn't, measured), but
"can the controller invoke any of this project's tools -- not just
rules -- in whatever sequence a given ask needs, instead of always
running the same fixed, ask-derived subset." That IS a real, currently-
missing capability, and most of the actual tools for it already exist
as separate, measured, deterministic primitives: rule/NLI/QA reasoning,
hybrid retrieval for related cases (`store.py`'s RRF-fused search, this
same session's earlier follow-up), document writing with template
contracts. What was missing was a controller that could reach for any
of them adaptively, per sub-need, rather than today's one fixed pass.

Built `brain.reason_dynamic` (new function, `reason()` itself completely
unchanged): a bounded loop around `reason()` that re-runs the SAME fixed
pipeline each round over a passage set that can grow in exactly two
closed, named ways -- never a free-form planner inventing a step:

1. **`derived_fact`**: a fact `forward_chain` derived this round (already
   bounded/deduplicated/traced inside `inference.py`) is textified into
   one new pseudo-passage (deterministic template, no generative model)
   so a later round's identity/total/graph stages -- which only scan
   passage TEXT today -- can see it too.
2. **`related_case`**: when a `Store` is given and the round's decision
   is `"inconclusive"`/`"ungrounded"`, `store.search(ask)` runs once and
   any real passages not already present get added -- the "find related
   cases automatically" capability named explicitly.

Stops at fixpoint (a round adds nothing) or `max_rounds` (default 5,
same cap discipline as `forward_chain`'s own `max_steps`), with every
round recorded in a new `"rounds"` field -- nothing silent.

Measured, not assumed:
- **Zero-expansion parity**: on a plain lookup with nothing to add,
  `reason_dynamic` produces an identical decision and text to `reason()`
  -- one round, immediate fixpoint.
- **Derived-fact reentry exercised without changing the answer**: on the
  Rohan/jail/license-suspension fixture, round 1 derives the fact (as
  it already did before this change) and round 2 genuinely reenters it
  as a pseudo-passage (`derived:1:0`) before reaching fixpoint -- proving
  the mechanism runs, not just that it's inert, while confirming no
  regression (text is unchanged from `reason()` alone, since round 1's
  own answer already stated it).
- **Related-case retrieval is a genuine capability win, not just
  parity**: `reason(ask, [])` with no passages returns `decision=
  "ungrounded"` and a FABRICATED answer ("Meera Iyer lives in Mumbai" --
  wrong). `reason_dynamic(ask, [], store=store)` against a 3-passage
  store pulls the real passage in round 2 and returns `decision=
  "supported"`, `"Meera Iyer lives at 22 Lake View Road, Chennai 600028.
  [s1]"` -- correct, grounded, citing a real passage id.

Named limits, honestly: a `derived_fact` pseudo-passage's citation id
is not a literal source quote (its own `derivation` field names the
real rule/fact it came from, the same non-literal-citation idiom
`_add_dependency`'s existing `"derived_fact"` dependency-tree nodes
already use); `document_write` stays its own exclusive pipeline exactly
as `plan_stages` already has it (not interleaved into the round loop --
a separate, larger change); grouped/disambiguated passage sets exclude
ungrouped pseudo-passages from `scoped` the same way they already
exclude an ungrouped policy passage, inherited behavior, not new.
Regression-checked against `reason()`'s existing call sites (EXP-060/
084/089/097) -- `reason_dynamic` is purely additive, no existing
function's code path changed.
