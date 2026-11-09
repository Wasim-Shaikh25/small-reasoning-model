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
