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
| brain.py | 793 | - (root) | not started |
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

**Progress: 0 / 59 files marked done, 0 / 8,570 lines confirmed read this pass.**
(The reachability map above and the module list itself IS the first real
output of this audit -- it already answers "does anything obviously
duplicate anything else" at the module-graph level, ahead of the
line-by-line pass.)

## Findings

_(populated as each cluster is audited; empty until the first cluster reports back)_

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
