# Handoff: continuing on your laptop

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
  mixed — lost to TF-IDF on a harder real-headline retrieval test, a genuine
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
hand-written items) — the span rules are keyed to narrow patterns (who/when/
amount) that don't cover SQuAD2's open-ended questions. Reported as measured,
not softened.

**Policy change: a narrow FLAN-T5 exception (this session, by your explicit
request).** `FORBIDDEN.md` now permits a small (`flan-t5-small`-class, under
~300M params) local T5 checkpoint, **only** as the section 3.7 rewriter —
joining and grammar-correcting findings that the existing extractor and NLI
judge have already verified. It is explicitly still forbidden as a proposer,
extractor, or judge, and every rewrite must pass the fidelity check (numbers/
dates/names preserved, modals unchanged, bidirectional entailment, citations
preserved) or fall back to the current deterministic assembly
(`lab/common/assemble.py`, unchanged). Read `FORBIDDEN.md`'s "bounded
rewriter exception" section in full before building this — it's the contract
whatever you write has to satisfy.

**This is a policy change only — nothing was implemented.** huggingface.co
was still blocked in the cloud sandbox at the time of writing, so
`flan-t5-small` was never actually downloaded or tested there.

## The one thing to check first on your laptop

```bash
curl -sSI https://huggingface.co | head -1
```

If that comes back reachable (your laptop almost certainly isn't behind the
sandbox's egress policy), you can go straight to implementing EXP-048 below.
If it's somehow still blocked, the plan doesn't change — just check your own
network/proxy/firewall, since there's no sandbox policy to blame on a laptop.

## Next step: EXP-048, the bounded rewriter (this is the real unlock)

This is already written up as a `todo` in `EXPLORATIONS.md` and
`lab/render_explorations.py` (search `EXP-048`). Summary of the plan:

1. **Load `flan-t5-small`** with `transformers` (`AutoModelForSeq2SeqLM`,
   `AutoTokenizer`). Don't bother with CTranslate2 conversion yet — get it
   working plainly first; that's a later speed optimization
   (`ARCHITECTURE.md` section 8/14 mentions it, EXP-045 is the matching
   latency todo).
2. **New file `lab/common/real_rewriter.py`**: a `rewrite_unit(leaf, glossary)`
   function that is a drop-in alternative to `assemble.render_unit` — same
   input shape (a leaf's findings, a glossary dict), same contract (it must
   only use the `statement` + `citation` fields already in each finding, never
   retrieve or invent). Build the prompt from only those verified statements
   plus a short style instruction (e.g. "Combine these verified facts into one
   flowing paragraph. Do not add any fact, name, number, or date not listed
   below.").
3. **Fidelity gate.** Run `lab/common/harness.fidelity(src, out)` (already
   exists — numbers dropped/added, modal changed) on `(joined verified
   statements, generated text)`. Add the two checks that function doesn't
   cover yet: bidirectional entailment (reuse `lab/common/nli.judge` both
   directions) and citation-marker survival (reuse
   `lab/common/assemble.citation_integrity`). On any failure, discard the
   generated text and fall back to `assemble.render_unit`'s plain output for
   that leaf — never partial-accept a rewrite.
4. **Wire it in** behind a flag in `assemble.assemble()` (e.g. `rewriter:
   "deterministic" | "bounded_flan_t5_small"`), defaulting to
   `"deterministic"` so nothing else in the repo changes behavior unless
   explicitly asked.
5. **New exploration `lab/exp_048_bounded_rewriter/run.py`**, following the
   existing pattern exactly (`Run`, `write_json`, `finish(..., models_used=...)`
   — see any of EXP-025/029/032/033/047 for the shape). Feed it the same
   verified-findings fixtures EXP-017/EXP-018 already use so the numbers are
   comparable. Measure and report: fidelity pass rate, fallback rate, and
   (if you have a few minutes) your own 1-5 fluency rating of a handful of
   outputs next to the deterministic baseline — `EXPLORATIONS.md`'s own rule
   is "Human ratings are collected from a person... not filled in by a
   model," so don't invent that number.
6. Run `python3 lab/render_explorations.py` to fold the new closed result in,
   and delete the EXP-048 `_todo(...)` entry from `lab/render_explorations.py`
   once it's closed (same pattern used for EXP-025/029/032/033/048's own
   sibling todos earlier this session — grep this file for how those were
   removed).

**Guardrail, worth repeating because it's the whole point of the exception
being narrow:** if you're tempted to also let FLAN-T5 answer a question or
judge support "since it's already loaded" — don't, without coming back to
`FORBIDDEN.md` and widening the exception on purpose first. The entire
system's one guarantee (every answer is a verbatim quote from a cited
passage) depends on extraction staying on a model that is structurally
incapable of inventing text. A generative model doesn't have that property no
matter how small it is.

## Bigger unlock once huggingface.co is reachable

EXP-048 is one unblock, but reachable huggingface.co opens *all* of the
proposed-model reruns that were stuck behind the sandbox's network policy:
EXP-027, EXP-028, EXP-030, EXP-031, EXP-034 through EXP-045 (see
`EXPLORATIONS.md`'s "Proposed-model reruns" section — every one of them names
exactly which blueprint checkpoint to load: bge-small-en-v1.5, DeBERTa-v3
SQuAD2, DeBERTa-v3 MNLI, GLiNER, dslim/bert-base-NER). Each one already has a
goal, a method, and a list of referenced files written out — they're ready to
implement, not just ideas. If you want the real thing instead of the spaCy
substitutes from this session, re-running EXP-029/032/033 with the actual
bge-small-en-v1.5 and comparing against the spaCy numbers already recorded
would be the most direct next step after EXP-048.

## Smaller, code-only todos (no network needed at all)

- **EXP-026** — qualification-rule handling (`except`/`unless`/`provided
  that`) for the lexical NLI judge. EXP-006 measured 0.0 accuracy on exactly
  this category; it's a known, named weak spot.
- **EXP-024** — train a small span tagger on labels already stored in this
  repo (sklearn, explicitly allowed by `FORBIDDEN.md`: "train a small head or
  a span tagger only on labels stored in this repository").
- **EXP-022** — an on-disk index, only worth doing once a corpus bigger than
  the current 76 chunks is attached.
- **EXP-023** — a human fluency rating. Needs an actual person (you), not a
  model standing in for one.

## House rules to keep following (from `AGENT.md`)

- Add a `todo` entry before implementing a new exploration, close it only
  after a real run writes `results.json`.
- `EXPLORATIONS.md` is generated, not hand-edited — change
  `lab/render_explorations.py` or a `data/exp_*/results.json`, then re-run
  `python3 lab/render_explorations.py`.
- `ARCHITECTURE.md` itself is never edited. `FORBIDDEN.md`, `OBJECTIVE.md`,
  and `lab/config/models.json` are, and all three were kept in sync with each
  other this session — check all three if you change the policy again.
- Any new real-model substitute gets the same honest labeling this session
  used throughout: what was proposed, what actually ran, and why they differ,
  in the exploration's own `models_used` field.
