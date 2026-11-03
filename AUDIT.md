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
| brain.py | 793 | - (root) | **done** (3 findings, see below) |
| ask.py | 176 | yes | not started |
| assemble.py | 184 | yes | not started |
| calc.py | 85 | yes | not started |
| connectives.py | 306 | yes | not started |
| connectors.py | 197 | yes | not started |
| doc_tools.py | 157 | yes | not started |
| document_writer.py | 86 | yes | not started |
| docx_writer.py | 71 | yes | not started |
| entities.py | 507 | yes | not started |
| graph_index.py | 128 | yes | not started |
| index.py | 202 | yes | not started |
| inference.py | 429 | yes | not started |
| ingest.py | 96 | yes | not started |
| intent_signals.py | 178 | yes | not started |
| longform.py | 255 | yes | not started |
| nested_index.py | 155 | yes | not started |
| nli.py | 62 | yes | not started |
| open_domain.py | 60 | yes | not started |
| prompt_contract.py | 44 | yes | not started |
| qa.py | 153 | yes | not started |
| real_encoders.py | 176 | yes | not started |
| real_models.py | 82 | yes | not started |
| real_ner.py | 48 | yes | not started |
| real_rewriter.py | 214 | yes | not started |
| real_rewriter_legal_gemma.py | 75 | yes | not started |
| real_rewriter_ollama.py | 241 | yes | not started |
| real_rewriter_qwen.py | 66 | yes | not started |
| relevance.py | 37 | yes | not started |
| rewriter_backends.py | 107 | yes | not started |
| rules.py | 317 | yes | not started |
| semantic_index.py | 292 | yes | not started |
| template_rewriter.py | 78 | yes | not started |
| temporal.py | 103 | yes | not started |
| textutil.py | 113 | yes | not started |
| verify.py | 154 | yes | not started |
| working_memory.py | 114 | yes | not started |
| budget.py | 24 | no | not started |
| chunking.py | 152 | no | not started |
| coherence.py | 72 | no | not started |
| deontic.py | 62 | no | not started |
| engine.py | 283 | no | not started |
| graph.py | 35 | no | not started |
| harness.py | 119 | no | not started |
| lora_finetune.py | 115 | no | not started |
| memory.py | 126 | no | not started |
| paged.py | 69 | no | not started |
| proposals.py | 66 | no | not started |
| provenance.py | 44 | no | not started |
| real_bge_index.py | 104 | no | not started |
| real_corpus.py | 107 | no | not started |
| real_index.py | 85 | no | not started |
| real_squad.py | 95 | no | not started |
| schemas.py | 84 | no | not started |
| store.py | 166 | no | not started |
| synthetic_fusion_data.py | 148 | no | not started |
| word_relevance.py | 72 | no | not started |

**Progress: 1 / 59 files marked done, 793 / 8,570 lines confirmed read this pass (brain.py). 5 cluster audits in progress covering the remaining 58 files.**
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

5 parallel sub-audits launched 2026-11-03, each covering one cluster of the remaining 58 files with explicit file:line citations. Results pending -- will be merged into this section as each one reports back.

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
