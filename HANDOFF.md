# Handoff: where this project actually stands

Rewritten 2026-11-09, superseding the 2026-10-14 version below the line
("Handoff: continuing on your laptop"), which is now historical -- its
"next step" (EXP-048, the bounded rewriter) and the policy change it
describes were both completed long ago. Read this section first; the old
one is kept below for the record, per this project's own append-only
findings discipline, not because it's current.

## Net result as of today

On the one real document fixture tested (EXP-081, a real 2,368-word GDPR
excerpt), the live default pipeline (`brain.reason` ->
`lab.common.longform.write_long_document` -> `lab.common.
rewriter_backends.rewrite_unit`) now makes **zero generative-model
calls** -- verified at every step, not assumed: byte-identical decision/
citations, the same 0.0 "fidelity pass rate" either way (because the new
deterministic path and the old always-failing generate()-then-fallback
path land on the same safety outcome), ~13x faster (815.7s -> 63.5s on
one run), correct connectives (a severe real-scale bug -- 21 of 51
connectives on this document were a wrong "However," -- found and fixed
along the way, not just documented).

The honest remaining gaps are narrow and named, not hidden:
- `sentence_completeness.py`'s two adversarial blind spots (a gerund-only
  fragment, a lone subordinate clause) -- found by deliberately adversarial
  testing, never hit by either real fixture tested so far, not fixed.
- The `no_verbal_root` single-finding case (a heading or lead-in fragment
  with no main verb) still attempts `generate()` today -- the skip was
  only ever extended to the "already complete" and "multi-finding" cases.
- Four other explorations share this same dispatcher
  (`exp_052_ask_driven_outline`, `exp_076_legal_gemma_rewriter`,
  `exp_078_longform_consistency`, `exp_082_document_tool_templates`) and
  were not re-run this session -- their committed `results.json` may be
  narrowly stale in the same diagnostic-label sense (never in actual
  output text).

Full trail, in order, with every number and every failed attempt kept
(not just the wins): `AUDIT.md`, search for "fluency does not require a
generative model", "a deterministic pre-check", and "template_splice
wired into multi-finding leaves". Nothing here is wired into a one-call
`brain.reason()` default end-to-end document-writing path by itself --
it's reached today only through `longform.write_long_document`'s own
default checkpoint argument, same as before.

## Findings and failures from the four big scale-tests (2026-11-09/10)

Four end-to-end tests were run at real document scale (a ~2,500-word
fictional Bombay HC petition, a real ~3,000-word GDPR excerpt rewritten
into plain English, decision-extraction from a fictional research memo,
and a real company policy -- Steam's refund policy -- applied to
fictional customer cases), each zero-generative-model. Three real bugs
were found and fixed along the way (spellfix's capitalized-word
corruption, spellfix's position-0 variant of the same bug, and
template_rewriter's MODAL_RE-driven false "However," connective) -- all
three are already fixed and covered above and in `AUDIT.md`; not
repeated here. Everything below is still open, not fixed, reported as
measured:

- **Vocabulary substitution cannot simplify sentence structure.**
  `plain_language.py` (new, closed 50+ term formal->plain table) got
  real substitutions on ~70% of sentences in both runs, with no
  meaning-changing substitution found -- but the document's longest,
  most convoluted sentences (deeply nested conditions, cross-references)
  still read almost as densely afterward. This module has no mechanism
  to split a sentence, flip passive to active, or reorder a clause, so
  it cannot touch the actual source of complexity in dense legal/
  regulatory text. "Simpler vocabulary" was achieved; "simple English"
  was not.

- **`decision_findings.py` has two confirmed, reproduced-twice failure
  modes**, independently hit on two different fictional memos: (1) a
  reported/embedded modal inside a described research question
  ("studying whether the company SHOULD expand...") is misread as a real
  directive -- a false positive; (2) a passive, non-modal decision ("a
  follow-up review IS SCHEDULED...") is missed entirely, since its ROOT
  verb isn't in the closed `DECISION_VERBS` table -- a false negative.
  ~93% precision/recall on both test runs; good enough as a first-pass
  flagger a person still reviews, not for unsupervised use.

- **`spellfix.py` still has an unfixed, likely-pervasive vocabulary-
  coverage gap for ordinary verb inflection.** `candidates_for(
  "commissioned")` returns only `["commissioner"]` -- the past-participle
  form isn't a single token in the flan-t5 vocabulary (same subword-
  splitting root cause as the already-known "overhear"/"colony" bugs),
  so a correctly-spelled verb gets silently swapped for a different,
  wrong-part-of-speech word. Common `-ed`/`-ing` inflection is far more
  frequent than compound nouns, so this is likely a bigger, more
  pervasive instance of the same bug class than either prior example --
  not fixed; a real fix needs lemmatizing before the vocabulary check,
  not another hardcoded exception.

- **`rules.py`'s conditional-rule mechanism does not generalize to a new
  domain or to real-world prose -- the sharpest finding of the four, and
  the one most relevant before pitching this architecture for anything
  beyond hand-written legal-rule shapes.** Tested twice (the original
  fork run and an independent re-run against a freshly fetched copy of
  Steam's real refund policy): 0 of 8 real-policy sentences parsed as a
  conditional rule unmodified in either run -- only a sentence
  deliberately hand-rewritten into the canonical "If X, Y" shape parsed.
  Two distinct structural failure modes, not one: real declarative
  policy prose doesn't match `RULE_RE` at all, and a copula+adjective
  condition ("is unused") isn't recognized since `_main_verb` requires
  `pos_=="VERB"`.

  Worse, and structural rather than a parsing-coverage gap: **`apply_rule`
  never evaluates any quantitative or temporal condition at all** -- it
  only compares the fact's verb lemma against the rule's trigger lemma.
  In the independent re-run, applying the one rule that DID parse ("if a
  game has been played for less than two hours and refunded within two
  weeks...") to 4 fresh fictional cases got **2 of 4 flatly wrong**: a
  case with 10 hours of playtime and a case refunded a month late both
  wrongly came back `matched=True`, because `condition_text` carries
  "less than two hours"/"within two weeks" as inert text, never compared
  against the case's actual numbers. This means the rule-application
  mechanism is not safe to point at any real policy whose outcome turns
  on a number or a date (most of them) without first building a real
  quantitative/temporal condition checker -- a gap that doesn't show up
  at all on the hand-written legal-rule examples this mechanism was
  originally validated against, because those examples never happened to
  test it.

Source documents and extracted-output files for all four tests were sent
to the user directly (`SendUserFile`), not committed to this repo --
regenerate them from `AUDIT.md`'s own entries (search "four big end-to-
end tests") if needed again; the original scratch scripts were cleaned
up when their background sessions closed.

## What's new in `lab/common/` since the 2026-10-14 version below

Not in the old plan at all -- built and measured since:
- `spellfix.py` + `informal_register.py` -- typo correction and informal-
  register normalization, zero generative calls (embedding-based
  disambiguation after 5 failed generative attempts across 2 checkpoints).
- `notes_to_findings.py` -- turns messy prose into assemble.py's
  `{statement, citation}` shape; has a structural attribution gate reusing
  `rules.extract_fact_triple`/`apply_rule` for rule-shaped sources.
- `relationship_graph.py` -- directed fact graph + cycle detection (the
  X-gave-Y-gave-Z-gave-X case), with pronoun-antecedent resolution that
  flags ambiguity rather than guessing silently.
- `write_article.py` / `article_tool.py` -- the full messy-notes-to-
  article pipeline as one named, schema-checked tool.
- `sentence_completeness.py` -- the pre-generation completeness gate
  described above.
- `template_rewriter.py` -- connective-splicing, now using
  `lab.common.connectives.find_connectives` (not regex) for its contrast
  check.
- `rewriter_backends.rewrite_unit` -- now skips `generate()` entirely for
  both already-complete single-finding leaves and all multi-finding
  leaves.
- `plain_language.py` / `decision_findings.py` -- built and tested during
  the four big scale-tests above; see that section for their honest,
  measured limits before reusing either.

## Product redesign proposal (2026-11-10): one `Engine`, a unified language brain, a self-expanding reasoning core, a teach/template tool layer -- status: proposed, not yet implemented

Driven by a request to turn this from a research lab into a product other
systems can integrate. Every open issue above shares one root cause worth
naming before any redesign: closed, hand-written pattern tables and fixed
pipelines that don't generalize past the shapes they were validated on
(`rules.RULE_RE`'s "If X, Y" phrasing, `decision_findings.DECISION_VERBS`'
closed lemma list, `spellfix`'s single-token vocabulary, the lexical QA
extractor's 0.0 SQuAD2 exact match, real embeddings losing to TF-IDF on a
harder retrieval test). The redesign below is organized around fixing that
root cause structurally, not patching each symptom again.

**Four layers, replacing today's single `brain.reason` signal chain:**

1. **Data layer -- promote `store.py` (currently zero fan-in, dormant) to
   the one place data enters the system.** `Store.build/load/search/
   expand_entity` already wraps `index.Index`, `real_bge_index.RealBgeIndex`
   and `graph_index`; `connectors.QdrantConnector`/`GraphConnector` already
   give it a remote/persistent backend. Missing and needed: an incremental/
   streaming upsert path (today `Store.build` is one-shot batch-fit only),
   and always-hybrid search (never dense-only -- the EXP-029 finding that
   real embeddings lost to TF-IDF on a harder retrieval test is exactly the
   failure mode hybrid search exists to avoid).

2. **Language brain -- one entry point merging what's scattered across
   `rules.py`/`inference.py`/`connectives.py`/`deontic.py`/`temporal.py`/
   `spellfix.py`/`plain_language.py`/`informal_register.py`/`word_relevance.py`
   today.** Normalizes vocabulary, parses structure, and emits one logic
   graph (facts, rule shapes, temporal/quantitative conditions, discourse
   relations, unresolved references) for both the ask and the data -- this
   is literally the "data logic" / "ask logic" split asked for. The one
   real design change here, not just consolidation: **reference resolution
   stops being a special case.** `relationship_graph._resolve_antecedent`
   today is a one-off nearest-antecedent heuristic for pronouns only.
   `ARCHITECTURE.md` section 6.0 already specifies the right shape --
   "ambiguous reference" is one of seven generic gap types, resolved by the
   same mechanism as entity identity, defined-term linking, and vague
   criteria -- but the code never actually built it that way. Fix: retire
   the pronoun-only heuristic in favor of one generic "bind this unresolved
   reference to the best-supported node" operation, scored by the same
   features already used elsewhere (recency, embedding similarity, role
   compatibility), usable for "it"/"the said premises" exactly as it's used
   for "the Lessee". Keep the old heuristic as a fallback until the generic
   version is measured to beat it on a labeled set -- don't rip it out same-day.

3. **Reasoning core -- make the self-expanding tree the primary mechanism,
   not a buried helper.** `inference.forward_chain` already does exactly
   this for rules: repeatedly matches every rule against every known fact,
   derives new facts, until nothing new fires. The fix is to generalize the
   *same loop* to admit every other operation (`qa.answer_with_real_qa`,
   `nli.judge`, the new reference-binder, `rules.apply_rule`) as an
   expansion move against a growing node set, instead of `brain._reason_once`'s
   fixed stage order. Required safety controls, non-optional: `budget.
   cap_depth` as a hard node/round cap, `relationship_graph.find_cycles` as
   a loop guard, and `verify.coverage_check` as the stop condition once
   every required fact is found/missing/conflicted. This is still zero new
   generative capability -- every expansion step is one of the existing
   deterministic/encoder operations; what changes is that they fire
   generically to a stop condition instead of in a hard-coded sequence.
   This also structurally fixes the sharpest open bug above: in the new
   design, the rule-expansion operator is required to call `calc.
   compare_numbers`/`temporal.check_temporal_bound` before it's allowed to
   fire, so `apply_rule` can no longer match on verb lemma alone while
   ignoring "within two weeks"/"less than two hours" as inert text.

4. **Tools -- teach tool, template contracts, domain tools.**
   `method_teaching.py` (482 lines, currently zero fan-in, dormant) already
   is the "teach it how to do a task" mechanism asked for (propose a short
   plan of primitives, validate the plan against the ask's intent, execute
   deterministically) -- promote it to the sanctioned way any new
   capability (a timeline, a policy application) gets added, instead of
   hand-writing a new one-off function per task. `doc_tools.py`'s template
   registry already selects templates and routes findings to sections by
   similarity; extend it so each template section carries an explicit
   contract (required fact types, ordering, min/max findings) the
   reasoning core can check per-section, not just globally. `gapfill.py`
   (the FLAN-T5 "untrusted proposer" from section 3.2.1, also dormant)
   becomes the one sanctioned fallback for anything the deterministic tools
   can't cover, gated the same way `FORBIDDEN.md`'s bounded-rewriter
   exception already gates generation elsewhere.

**Per-issue fix mapping (every open item above, now with a concrete fix
instead of just a measurement):**
- `rules.py` never checks quantitative/temporal conditions -> structural
  fix in the reasoning core's rule operator (point 3).
- `rules.py` doesn't parse real policy prose (0/8) -> widen
  `parse_conditional_rule` to use `connectives.find_connectives`'s already-
  generic operator detection instead of `RULE_RE`'s canonical-phrasing regex.
- `decision_findings.py`'s reported-question false positive -> check
  whether the modal sits inside a `ccomp`/`xcomp` of a cognition verb
  before accepting it as a directive.
- `decision_findings.py`'s passive-decision false negative -> widen past
  the closed `DECISION_VERBS` lemma list using embedding nearest-neighbors,
  not another hardcoded entry.
- `spellfix.py`'s verb-inflection gap -> lemmatize before the vocabulary
  lookup.
- `plain_language.py`'s structural ceiling -> explicitly not plain_
  language's job; sentence restructuring becomes a reasoning-core operation
  (split on the connectives `find_connectives` already detects), not a
  vocabulary-substitution patch.
- `sentence_completeness.py`'s two blind spots and the still-generating
  `no_verbal_root` case -> extend the gate's classifier for gerund/lone-
  subordinate fragments; route headings to deterministic formatting
  instead of ever calling `generate()` on them.

**Keep / promote / delete, once each replacement is wired and verified
(never delete before the replacement is measured, per this project's own
discipline of not removing a working path until its successor is proven)**:
- Promote to core: `store.py` (done, 2026-11-10 -- `Store.upsert` +
  fused `search`), `plain_language.py` (done, same week -- wired into
  `brain.reason` via `plain_english`). Still dormant, not yet promoted:
  `gapfill.py` (needs its own FORBIDDEN.md-gated review before it brings
  a new generative fallback live), `decision_findings.py`, `spellfix.py`,
  `informal_register.py` -- each tested and correct standalone, each
  still needing its own dedicated wiring decision, not done yet.
- Deleted (2026-11-10), not merely flagged: `method_teaching.py` -- zero
  fan-in confirmed, its replacement (`concept_tools.py`'s YAML-defined
  registry) measured and proven for weeks, per this project's own "never
  delete before the replacement is proven" rule being satisfied, not
  skipped.
- Keep, narrow the scope: `relationship_graph.py`'s graph/cycle-detection
  parts stay; its `_resolve_antecedent` one-off is kept as the default,
  with a measured, opt-in replacement (`use_reference_binder`) added
  alongside it (2026-11-10) -- not yet made the default, since HANDOFF's
  own instruction was to keep the old heuristic until the new one is
  measured against a real labeled set, not just two hand-built cases.
- Candidate delete (one-off, task-specific, superseded by the template/
  tool layer once it's wired): `article_tool.py` (a bespoke single-purpose
  wrapper), `write_article.py` (folds into a registered template instead).
- Move out of the shipped package, keep for research: `synthetic_fusion_data.py`,
  `lora_finetune.py`, `real_corpus.py`, `real_squad.py` -- offline
  training/benchmark plumbing, not part of a product's runtime path.
- Not touched: the 91 `lab/exp_*` scripts stay as the append-only research
  trail (`AGENT.md`'s own discipline); productization means a new clean
  public surface on top of `lab/common`, not deleting the evidence base.

**Framework/API surface asked for ("any system can integrate this")**: one
public entry point, e.g. an `Engine` class wrapping the four layers
(`Engine(data_source=..., templates=[...]).teach(...)`/`.ask(...)`/
`.write(...)`), so external callers import one stable surface instead of
reaching into `lab.common.*` internals. Scope this as its own phase after
the four-layer core is validated -- versioning and a stable public API are
a real commitment, not something to bolt on mid-redesign.

**Update, next day: the tool layer's teach/template half is now built and
tested** (`AUDIT.md`, search "the teach-tool concept registry"). New:
`lab.common.concept_tools` (a YAML-defined concept registry -- 8 generic
primitives in Python, every task-specific capability a YAML file under
`lab/common/concepts/`), `lab.common.connector_config` (YAML-declared
data sources: `inline`/`records`/`file` tested, `qdrant`/`graph` wired to
the existing connector classes but not live-tested), `lab.common.render`
(JSON/Markdown/.docx output), and `lab.common.engine.run` as one public
entry point. Proven end-to-end on a fictional fixture: "timeline",
"acts and sections", "respondent addresses" and "parties name and
address" all work with zero hardcoded, task-named Python; an untaught ask
("emotional tone") correctly returns a graceful "teach me" response
instead of a guess. `CONCEPT_TAU` (0.6) is provisional, not calibrated.

**Update, same week: made the teach-tool layer genuinely industry-blank,
and tested it against every other open issue below** (`AUDIT.md`, search
"making the teach-tool layer actually industry-blank"). The four
legal-petition concepts moved to `lab/common/concepts/examples/`
(`load_concepts()` never scans it) -- the shipped registry is now
verified empty, so a fresh install of any industry starts from nothing.
`resolve_addresses` (named after one field) was retired for
`structure_field(field, parser)`, parameterized the same way
`extract_by_label`'s `label` already is. A new primitive,
`filter_by_condition(field, operator, value)`, directly fixes this
project's sharpest named structural bug: `rules.py`'s verb-lemma-only
`apply_rule` never checks a rule's quantitative/temporal condition at
all, which wrongly matched a 10-hour-playtime case and a
refunded-a-month-late case against the real Steam refund policy.
Reconstructed that exact scenario on a deliberately non-legal fixture
and got both wrong cases correctly excluded, via the generic design, not
a `rules.py` patch -- proof it generalizes past the original four
examples' one industry. Honest limit: this sidesteps `rules.py`'s other
named bug (parsing real policy prose, 0/8) rather than solving it -- the
policy is declared as YAML, never parsed from English. Checked, not just
listed: nine of the eleven other issues named below (`decision_findings.py`'s
two bugs, `spellfix.py`'s inflection gap, `plain_language.py`'s
structural ceiling, `sentence_completeness.py`'s blind spots, reference
resolution, the data layer, the reasoning core, template contracts, the
dormant-module pass) are **not** solved by this layer -- each lives in a
different subsystem this teach-tool layer was never scoped to touch, and
none moved as a side effect of this work.

**Update, same day: three of the nine untouched issues fixed directly,
one attempted and confirmed NOT to work** (`AUDIT.md`, search "three of
the nine untouched issues fixed directly"). Fixed, each measured against
HANDOFF's own named example: `decision_findings.py`'s reported-question
false positive (`deontic.classify_deontic` now structurally skips a
modal inside a "whether"/"if"-marked embedded clause); `spellfix.py`'s
verb-inflection gap (lemmatize via the already-used spaCy parser before
the vocabulary check, exactly as this file suggested); `sentence_
completeness.py`'s gerund-fragment and lone-subordinate-clause blind
spots, plus wiring its `no_verbal_root` reason into `rewriter_backends.
rewrite_unit`'s existing `generate()`-skip so a heading/lead-in fragment
is never sent to a generative model. The existing EXP-087 fixture
(6 hand-built cases + the real 103-sentence GDPR document) was rerun and
is byte-identical to its committed `results.json` -- zero regression.

Attempted and measured, NOT fixed: `decision_findings.py`'s passive-
decision false negative. This file's own suggested fix (embedding
nearest-neighbor verb widening against `DECISION_VERBS`) was tried
exactly as written and does not work -- "schedule" (the verb that should
be caught) scored LOWER against the decision-verb set than "describe"
and "eat" (verbs that must NOT be caught), with no threshold that
separates them. No confident deterministic alternative identified yet;
this is an open design question, not a fix in progress.

**Update, same day: `plain_language.py` is wired into `brain.reason`,
and the hardcoded vocabulary tables are moved to data** (`AUDIT.md`,
search "the hardcoded tables moved to data"). New `lab.common.
grammar_logic` (`passive_to_active`, `split_on_connective`, both gated
by bidirectional NLI entailment) plus `plain_language.simplify_document`
closes `plain_language.py`'s own named structural ceiling -- a new
`plain_english` flag (default `False`, same opt-in shape as `use_real_
ner`) threads through `brain.reason -> _reason_once ->
write_long_document -> simplify_document`, verified end to end, zero
change to the default path. `entities.py`'s live `ORG_SUFFIXES`/
`PLACE_LAST`/`NOT_PERSON` and `decision_findings.py`'s `DECISION_VERBS`
are now `lab/common/lexicons/*.yaml`, not Python literals; a real
duplicate-vocabulary bug (`ORG_SUFFIXES` and `ORG_RE`'s regex used to be
two separately hand-typed copies of the same suffix list) was found and
fixed while doing this, not just relocated. `method_teaching.py` is
explicitly flagged as a delete candidate (superseded by `concept_tools.py`,
which does the same job generically) rather than promoted or fixed in
place. `proposals.py`/`provenance.py` were deliberately left untouched
-- both are confined to old, closed experiments.

**Still not done**: `lab.common.engine.run` is a new, separate entry
point -- it is not wired into `brain.reason` or `longform.
write_long_document` (that pipeline is now reached through `plain_
english`/other existing flags, a separate path from the teach-tool
concept registry). The passive-decision false negative is still open
with no known fix, not merely unattempted. A non-generative CoLA
grammaticality classifier was identified as the right tool for catching
grammar problems beyond the ones hand-found this session, but is not yet
downloaded or wired in. `gapfill.py` (the FLAN-T5 "untrusted proposer")
and `informal_register.py`/`decision_findings.py`/`spellfix.py` stay
dormant/partially-dormant -- `gapfill.py` brings in a NEW generative
fallback capability, which needs its own FORBIDDEN.md-gated review, not
a same-pass wiring decision; `decision_findings.py`/`spellfix.py` are
each tested and correct standalone but wiring either into `brain.
reason`'s live pipeline is its own design decision (where in the
pipeline, what the flag's output surfaces as) that deserves the same
dedicated testing every other flag in this project got, not a rushed
addition under this pass's own time pressure.

**Update, next day: four of the five remaining items fixed and
measured; the fifth (the self-expanding reasoning core) deliberately
not attempted** (`AUDIT.md`, search "four of the five remaining open
items fixed"). Fixed: pronoun/coreference resolution
(`relationship_graph.build_relationship_graph`'s new `use_reference_
binder`, salience + recency + soft type-compatibility, NOT role-
parallelism -- tried first, found to break this project's own
payment-chain motivating example, replaced); the data layer's streaming
upsert and always-hybrid search (`store.py`'s new `Store.upsert` +
Reciprocal-Rank-Fusion `search`, honestly scoped per leg -- bge's dense
leg is genuinely incremental, TF-IDF/the graph are cheap refits, not
literal incremental updates); per-section template contracts
(`doc_tools.check_section_contract`, wired into `write_long_document`'s
new `contract_violations` and a new `template_id` parameter threaded
through `brain.reason` itself); and the EXP-081 `consistency_flags`
13->16 side effect (not just disclosed this time -- actually measured
with real NLI and fixed: 15 of the 16 flags score under 0.02
contradiction probability between their own source sentences, confirming
EXP-081's own prior guess that this was a false-positive-prone checker
on repetitive legal text; `working_memory.check_and_remember_page`'s new
`use_real_nli` flag cuts 16 flags to 1 on the identical fixture, default
False keeps the original recall-first behavior for every existing
caller). Not attempted: the self-expanding reasoning core -- this is a
different CONTROL PHILOSOPHY for `brain.reason` itself (a dynamic
fixpoint loop replacing today's `plan_stages`-computed, deliberately
fixed, inspectable stage order, which the project owner's own words in
`plan_stages`'s docstring explicitly chose for controllability), not a
same-shape wiring change like the four above -- rewiring the single most
load-bearing function in this project without a dedicated labeled set to
catch a dispatch regression across the ~90 experiments that call
`reason()` would be exactly the kind of unmeasured change this project's
own discipline exists to prevent. Left genuinely undone; HANDOFF's own
proposal already scoped it as "its own phase," not a same-pass fix.

**Update, next day: tested the self-expanding core's own motivating
scenario directly -- found no dynamic-control gap, fixed two unrelated
latent bugs instead** (`AUDIT.md`, search "tested the self-expanding
core's own motivating scenario directly"). The project owner asked to
find a way to control dynamic reasoning before building it; rather than
design controls in the abstract, the actual scenario was run first.
Measured: `reason()` already answers a multi-hop identity question
("who will have their license suspended?" after kill->crime+jail->
license_suspended) correctly in ONE pass, no dynamic re-planning --
`forward_chain`'s existing bounded/traced fixpoint loop runs inside the
`rule_application` stage, and `plan_stages` already computes every
relevant stage from the ask text up front, so `identity_extraction` and
`rule_application` both fire together and their text concatenates. No
capability gap. Looking for a harder case (a derived fee updating
`total_computation` in the same pass) surfaced two real but unrelated
bugs instead of a control problem: `_find_rule` tried verb-shape rule
parsing before threshold-shape (every existing fixture avoided the
collision by prefixing the sentence with a policy label that the verb
parser's anchor rejects; a bare "If X's total exceeds $N, ..." sentence
did not); and `total_computation`'s money-scan summed dollar amounts
from rule-shaped passages too (every existing fixture avoided this by
accident, via disambiguation filtering the ungrouped policy passage out
of scope). Both fixed narrowly in `brain.py` (`_find_rule` tries the
more specific pattern first; the money-scan now excludes rule-shaped
passages, same precedent `_reason_once`'s own fact-passage lookup
already uses) -- confirmed zero regression on 17 existing experiments.
**The self-expanding reasoning core stays not-attempted, now as a
closed question rather than a postponed one: direct testing of its own
motivating case found nothing left for a dynamic loop to fix.**

## House rules to keep following (unchanged, from `AGENT.md`)

- Add a `todo` entry before implementing a new exploration, close it only
  after a real run writes `results.json`.
- `EXPLORATIONS.md` is generated, not hand-edited -- change
  `lab/render_explorations.py` or a `data/exp_*/results.json`, then re-run
  `python3 lab/render_explorations.py`.
- `ARCHITECTURE.md` itself is never edited. `AUDIT.md` is append-only --
  extend it, never rewrite past entries away.
- Any new real-model substitute (or removal) gets the same honest
  labeling this project has used throughout: what was proposed, what
  actually ran, what was measured, and why they differ.

---

# Handoff: continuing on your laptop (2026-10-14, historical)

Written 2026-10-14, end of a cloud session, to continue this work locally. Read
this first, then `AGENT.md` for the exploration workflow, then `EXPLORATIONS.md`
for the full measured record.

## Where things are

- Repo: `small-reasoning-model` (owner `Wasim-Shaikh25`)
- Branch: `ccr-8086d212-77q3w0`, pushed to `origin`. No pull request open yet.
- This branch already contains the original classical POC (PR #1,
  `cursor/research-poc-explorations-2557`, merged in) plus everything below.

```bash
git clone https://github.com/Wasim-Shaikh25/small-reasoning-model.git
cd small-reasoning-model
git checkout ccr-8086d212-77q3w0
python3 -m pip install -r requirements.txt
python3 -m spacy download en_core_web_sm
python3 -m spacy download en_core_web_md
python3 lab/run_all.py
python3 lab/render_explorations.py
```

## What's in this branch already (don't redo this)

**Classical POC (EXP-001 to EXP-021, closed).** Lease-fixture synthetic data,
every model slot filled by a classical substitute (TF-IDF, rule taggers,
logistic regression). This is the original PR's work.

**Real-document, real-model reruns (EXP-025, EXP-029, EXP-032, EXP-033,
closed).** Built this session. huggingface.co was blocked by *this cloud
sandbox's* egress policy (403 on every attempt), so bge/DeBERTa/GLiNER could
not be loaded there. Worked around it with the closest reachable real,
non-generative substitutes:
- Real documents: 25 real 1987 Reuters news articles (`lab/common/real_corpus.py`,
  fetched from `raw.githubusercontent.com/nltk/nltk_data`, not from nltk's own
  downloader, which refuses to run behind a proxy).
- Real dense embeddings: spaCy `en_core_web_md` static vectors
  (`lab/common/real_index.py`), compared against classical TF-IDF. Result was
  mixed -- lost to TF-IDF on a harder real-headline retrieval test, a genuine
  negative finding, reported as measured.
- Real NER: spaCy `en_core_web_sm` (OntoNotes), beat the rule tagger clearly
  (F1 0.76 vs 0.59) on real sentences (`lab/common/real_models.py`).
- Real multi-hop reasoning (EXP-032, the centerpiece): a genuine 2-hop
  evidence chain across real documents, using a real cross-document bridge
  entity (e.g. "Brazil" appearing in 12 different real articles), real
  retrieval, real NER for the bridge, real verification. Chain accuracy 0.5
  (real stack) vs 0.2 (classical stack).

**Real benchmark data (EXP-047, closed).** Separate from the model question:
fetched the real SQuAD2 dev set (`lab/common/real_squad.py`, from
`rajpurkar/SQuAD-explorer` on GitHub) and reran EXP-005's *unmodified* lexical
extractor on 300 real questions. Exact match collapsed to 0.0 (vs 0.54 on the
hand-written items) -- the span rules are keyed to narrow patterns (who/when/
amount) that don't cover SQuAD2's open-ended questions. Reported as measured,
not softened.

**Policy change: a narrow FLAN-T5 exception (this session, by your explicit
request).** `FORBIDDEN.md` now permits a small (`flan-t5-small`-class, under
~300M params) local T5 checkpoint, **only** as the section 3.7 rewriter --
joining and grammar-correcting findings that the existing extractor and NLI
judge have already verified. It is explicitly still forbidden as a proposer,
extractor, or judge, and every rewrite must pass the fidelity check (numbers/
dates/names preserved, modals unchanged, bidirectional entailment, citations
preserved) or fall back to the current deterministic assembly
(`lab/common/assemble.py`, unchanged). Read `FORBIDDEN.md`'s "bounded
rewriter exception" section in full before building this -- it's the contract
whatever you write has to satisfy.

**This section is now historical: EXP-048 was implemented and closed long
ago** (see `AUDIT.md`/`EXPLORATIONS.md`), and the whole "Net result" section
at the top of this file is the current state of that same rewriter question.

## Smaller, code-only todos (no network needed at all)

- **EXP-026** -- qualification-rule handling (`except`/`unless`/`provided
  that`) for the lexical NLI judge. EXP-006 measured 0.0 accuracy on exactly
  this category; it's a known, named weak spot.
- **EXP-024** -- train a small span tagger on labels already stored in this
  repo (sklearn, explicitly allowed by `FORBIDDEN.md`: "train a small head or
  a span tagger only on labels stored in this repository").
- **EXP-022** -- an on-disk index, only worth doing once a corpus bigger than
  the current 76 chunks is attached.
- **EXP-023** -- a human fluency rating. Needs an actual person (you), not a
  model standing in for one.
