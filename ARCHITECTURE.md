# Evidence-Grounded Reasoning System (No Generative Reasoner): Implementation Architecture

Version 0.2 (PoC blueprint) | CPU-first, private, domain-agnostic. The legal domain is attached later through RAG.

Changes from v0.1: the reasoner is now an **encoder-only judgment engine** (no generative LLM makes decisions). Added entity detection and an on-the-fly **entity resolution loop** that pulls missing context from RAG. FLAN-T5 is used **only** as the final rewriter.

---

## 1. Purpose, principles, hard constraints

Build a system that analyzes large document collections and produces answers traceable to evidence, with no cloud LLM and no new foundation model.

**Hard constraints**

1. No generative model makes decisions or asserts facts. Decisions come from encoder models (classifiers, extractive QA, NLI, rerankers) and small learned decision heads.
2. FLAN-T5 is used in two bounded roles: as an untrusted proposer before retrieval (section 3.2.1) and as the rewriter of already-verified findings. It never decides or asserts facts, and its outputs are filtered or re-checked.
3. The domain (legal, medical, finance) comes only from the attached knowledge base. Nothing in the pipeline is law-specific.
4. The system never changes model weights at inference time. "Learning on the fly" means retrieving missing context and re-reading with it (section 6).
5. The system is general-purpose. It reasons from the supplied context and retrieved raw data, not from what is stored in model weights. Names, addresses, clauses and legal terms in this document are examples of context gaps, not the scope.
6. A model's own understanding is limited to language, common sense and task skills (comparing, counting, following conditions). It is never an accepted source of facts (section 1.1).

**Design principles**

1. **Fetch first, assert later.** No factual claim before evidence is in front of the engine. Rewriting supplied text is the only task that skips retrieval.
2. **Judgment over evidence, not generation.** The engine outputs labels, spans, scores and next actions.
3. **The controller enforces limits.** Budgets, permissions, stopping rules and schema validity are plain code. Learned heads propose; the controller disposes.
4. **Abstain by default.** "Insufficient evidence" and "ambiguous" are valid outputs.
5. **Measure each stage separately.** Retrieval, entity detection, QA, NLI, decision head and rewriter are scored independently.
6. **Memory is an index, not a replacement.** Notes point into the archive and are re-verified before use.
7. **Retrieved text is data, never instructions.**

**What this design cannot promise**

- Zero errors. It can detect many unsupported claims, flag ambiguity and abstain.
- Free-form reasoning. It finds, compares, judges and flags. It does not write novel arguments, and its accuracy drops with chain depth (measure this in Phase 0).
- That a citation proves a claim. Verification is separate from citation.

### 1.1 Knowledge sources and provenance ("little of its own understanding")

Every statement in an output carries one of three provenance tags, and the output shows them separately:

| Tag | Source | Allowed use |
|---|---|---|
| `evidence` | Supplied prompt text and retrieved passages, with a quote and a citation id | Any factual claim |
| `background` | The model's own understanding: word meanings, grammar, common sense, how to compare, count or apply a condition | Interpreting the ask and the evidence. Never the sole support for a factual claim about the documents or the world |
| `inference` | A conclusion drawn from `evidence` through a stated step (comparison, calculation, condition) | Allowed when the inputs are cited and the step is shown |

Rules:

- A factual claim with only `background` support is dropped or reported as "not established in the provided material".
- If the context contradicts what the model "knows", the context wins (tested in Experiment H1).
- A term the model has never seen is safe only when retrieved context defines it. With no definition found, the term is `unresolved`. It is never guessed from weights.
- `background` use is logged so you can see how much the model leaned on its own understanding for each answer.

---

## 2. System overview

```
                          USER ASK
                             |
                             v
                   +-------------------+
                   | TASK CONTROLLER   |  budgets, limits, schema checks
                   +---------+---------+
                             |
          +------------------+------------------+
          |                                     |
          v                                     v
 +--------------------+                +------------------+
 | ASK ANALYZER       |                | REWRITE-ONLY     |
 | (encoders)         |                | PATH (no fetch)  |
 | task type, depth,  |                +---------+--------+
 | keyphrases, sub-Qs,|                          |
 | query variants     |                          |
 +---------+----------+                          |
           v                                     |
 +---------------------------+                   |
 | MEMORY + RETRIEVAL        |                   |
 | recall -> hybrid -> rerank|                   |
 | -> optional GraphRAG      |                   |
 +------------+--------------+                   |
              | passages (id, doc, page, version, text)
              v                                  |
 +---------------------------+                   |
 | GAP RESOLUTION ENGINE     |                   |
 | find unknowns -> fetch    |                   |
 | context -> re-read ->     |                   |
 | verify -> store           |                   |
 +------------+--------------+                   |
              v                                  |
 +---------------------------+                   |
 | JUDGMENT ENGINE           |                   |
 | answerability, extractive |                   |
 | QA, hop chaining, NLI,    |                   |
 | conflict scoring,         |                   |
 | decision head,            |                   |
 | next-action head          |                   |
 +------------+--------------+                   |
   missing / conflict / low confidence           |
   -> back to retrieval (within budget)          |
              v                                  |
 +---------------------------+                   |
 | VERIFICATION ENGINE       |                   |
 | quote, NLI re-check,      |                   |
 | contradiction search,     |                   |
 | calc check, coverage      |                   |
 +------------+--------------+                   |
              v                                  v
 +------------------------------------------------------+
 | REWRITER (FLAN-T5) + FIDELITY VALIDATOR              |
 +--------------------------+---------------------------+
                            v
                     FINAL OUTPUT VALIDATOR
                            v
        ANSWER  (or "insufficient evidence" / "ambiguous" + what is missing)
```

---

## 3. Components

### 3.1 Task controller (deterministic code)

- Runs the loop, enforces round, passage, token and time budgets.
- Validates every component output against its schema. One repair attempt, then fail safe (abstain).
- Approves or caps the fetch depth proposed by the ask analyzer.
- Logs every step (ask, queries, retrieved ids, scores, decisions, timings) for evaluation.

### 3.2 Ask analyzer (encoders only)

Without a generator, "reframing" is built from encoder parts:

| Job | Method |
|---|---|
| Task type (rewrite, lookup, compare, chronology, entity, reason) | Zero-shot NLI classifier at first; a small fine-tuned DeBERTa classifier once you have labeled asks |
| Fetch depth (none, light, medium, deep) | Classifier on ask features (length, number of entities, question words, comparison words) |
| Keyphrases and entities in the ask | Embedding-based keyphrase extraction (KeyBERT-style) plus GLiNER |
| Sub-questions | Split on conjunctions, lists and comparison patterns using a small tagger, then fill per-task-type question templates ("What is the {X}?", "When was {X} {verb}?") |
| Query variants | Original ask, keyphrase query, and template queries. Add pseudo-relevance feedback: take salient terms from the top retrieved passages to form a second query |
| Missing facts | Each sub-question is a required fact the judgment engine must answer |

Known limit: decomposition of unusual, multi-clause asks is the weakest part of the template-based design. Phase 0 measures it (Experiment F). Fallback: ask the user a clarifying question, or search the whole ask as one query. The proposer stage below is the first fix for this weakness.

### 3.2.1 Proposer stage (FLAN-T5, untrusted pre-stage)

Role: before retrieval, and again whenever evidence is missing, FLAN-T5 proposes a reframed question, sub-questions, search queries, the facts that would be needed, and hypotheses written as questions to test. It fills the weak spots of the template-based analyzer. It is expected to hallucinate, so everything it outputs is a proposal. A proposal is never evidence and never a conclusion.

Rules:

- **Allowed asks:** reframe, decompose, propose queries, list needed facts, turn a guess into a question to test ("Is the notice period 30 days?" becomes the query "notice period").
- **Disallowed asks:** answer the question, state facts about the documents or the world, produce citations.
- **Output format:** short fixed-format lists with capped counts (for example at most 5 sub-questions and 5 queries). Greedy decoding, or 3 to 5 samples merged by agreement.
- **Raw ask always searched:** the original ask is always one of the queries, so a bad proposer can never lower baseline recall.
- **Grounding filter before use:** each proposal must be well-formed, deduplicated, and have its content terms present in the ask, the retrieved context, recall memory or generic vocabulary. Proposals that introduce new names, numbers or dates are dropped or flagged. A query that retrieves nothing above the reranker threshold is dropped.
- **Merge:** proposer items are united with the analyzer's template items. If the proposer's output fails the filter, the analyzer's version is the fallback.
- **Cost of a bad proposal:** a wasted retrieval, not a wrong answer, because nothing from the proposer is treated as a fact. Controller budgets cap the waste.
- **Bias guard:** a proposed hypothesis can steer retrieval toward its own guess, so the mandatory contradiction search still runs before any `supported` answer.
- **Calibrated limits:** the maximum input size, item count and hop count per proposer call come from Experiment P and are stored in config and enforced by the controller.

### 3.3 Memory and retrieval

**Three tiers**

| Tier | Holds | Store |
|---|---|---|
| Working memory | Current ask, sub-questions, evidence in use, loop state, entity table | In-process object, reset per task |
| Recall memory | Verified notes and verified entity facts with importance and source pointer | SQLite (or a Qdrant collection) |
| Archive | Documents, chunks, graph | Qdrant + document store (+ graph store) |

**Recall note schema**

```json
{
  "note_id": "N-000123",
  "kind": "stated_fact | entity_fact | inference",
  "statement": "Ravi Sharma is the Lessee; address: 14 MG Road, Pune 411001.",
  "source": {"doc_id": "D3", "version": "sha256:...", "page": 3,
             "chunk_id": "D3-p3-c1", "exact_text": "..."},
  "verification": {"status": "verified", "method": "quote+nli+qa_agree",
                   "checked_at": "2026-10-14T10:15:00+05:30"},
  "importance": 0.9,
  "conflicts": [],
  "created_at": "...", "last_used_at": "...", "use_count": 4
}
```

Rules:

- Store verified extractions and pointers, never model conclusions as truth. Label inferences as `inference`.
- Before using a note: reopen the source, confirm the version hash and exact text. Changed or missing source invalidates the note.
- Rank by relevance and importance. Recency only resolves changing information. Durable facts (a clause, a party) do not decay from disuse.
- A conflicting source flips the note to `conflicted` and triggers re-verification.

**Retrieval stack**

1. Recall lookup (embedding match on `statement`).
2. Hybrid search in Qdrant: dense + sparse (BM25/SPLADE), with metadata filters (document, date, type, section).
3. Cross-encoder reranker over the top 30 to 50 candidates, keep the top 5 to 10.
4. Optional GraphRAG for cross-document relations (entities, defined terms, clause references).

**Chunking**

- Structure-aware (headings, numbered clauses, party blocks, schedules, signature pages), 200 to 400 tokens, 10 to 15 percent overlap.
- Each chunk stores `doc_id, version_hash, page, section_path, char_offsets, chunk_type` (for example `party_block`, `definition`, `clause`, `schedule`, `signature`). Chunk type lets entity resolution query the right places.
- Hierarchical summaries are navigation aids stored as source-linked chunks. They are never evidence. Because no generator exists, summaries are **extractive** (top-ranked sentences), not written.

### 3.4 Gap resolution engine

Purpose: whenever the engine meets something it cannot handle confidently from the context (an unfamiliar term, an abbreviation, an ambiguous reference, an unclear identity, a missing premise, conflicting values), it fetches defining context from RAG, re-reads with it, verifies the result, and stores it. This is how the system "learns" what it was not trained on. Entities (names, addresses, roles) are one worked example, not the scope. Details in section 6.

Tools used for the entity example:

| Job | Tool |
|---|---|
| Zero-shot tagging (person, organization, address, defined term, date, amount) | GLiNER |
| Second opinion for people and organizations | BERT/RoBERTa NER (for example dslim/bert-base-NER) |
| Address parsing into house number, street, locality, city, state, postcode | libpostal |
| Role assignment ("Who is the Lessee?") | Extractive QA over retrieved passages |
| Same-entity matching | Pairwise matcher over string similarity (rapidfuzz), embedding similarity, and context compatibility |
| Entity example store | Verified (span, context, label) examples in recall memory, used for nearest-neighbor voting |

### 3.5 Judgment engine (encoders and heads)

| Module | Model | Output |
|---|---|---|
| Answerability | SQuAD2-style QA model's no-answer score | Probability the passages contain the answer |
| Extractive QA | DeBERTa-v3 or RoBERTa SQuAD2 model | Exact span, start/end offsets, confidence |
| Hop chaining | Chained QA: answer from hop 1 is inserted into the query for hop 2 | Spans per hop with confidences |
| Support / contradiction | DeBERTa-v3 NLI cross-encoder (premise = passage, hypothesis = claim statement) | entailment / neutral / contradiction probabilities |
| Conflict scoring | NLI pairwise across passages that answer the same sub-question | Conflict flag with the pair ids |
| Decision head | Small learned model (gradient-boosted trees or logistic regression) over features below | supported / contradicted / inconclusive with calibrated confidence |
| Next-action head | Small learned classifier over loop state | retrieve_more / verify / calculate / answer / abstain |

**Decision head features** (per required fact and overall):

- NLI entail / neutral / contradict probabilities (max and mean across passages)
- QA span confidence and no-answer probability
- Reranker score of the supporting passage
- Number of independent supporting sources
- Source agreement or conflict flag
- Coverage ratio (required facts found / total)
- Entity confidence for entities in the claim
- Retrieval round number and remaining budget

**Claim statements for NLI:** since nothing generates text, the claim hypothesis is built by filling a template with the extracted span ("The notice period is 30 days.", from sub-question template plus QA span). Template quality affects NLI accuracy, so test several templates per question type.

**Next-action head inputs:** missing facts count, conflicts count, decision confidence, rounds used, passages seen, whether a contradiction search has been run.

Both heads are trained offline on public general data (section 9). They contain no legal knowledge.

Arithmetic and date logic (notice period plus delivery date, amounts) go to a small calculator with a date parser (for example `dateparser`). It runs on spans the QA model extracted. It is a tool, not reasoning, and its inputs are shown in the output.

### 3.6 Verification engine

Checks run in order. A failure removes the claim or triggers re-retrieval.

| Check | Method | Catches |
|---|---|---|
| Quote check | Exact or fuzzy substring match of the span in the cited passage | Wrong offsets, altered text |
| Support re-check | NLI on the final claim statement vs the cited passage | Template or span errors |
| Cross-model agreement | A second QA model must return an overlapping span | Single-model extraction errors |
| Conflict check | NLI across passages for the same fact | Contradictory sources |
| Contradiction search | Targeted retrieval for evidence against the conclusion (negated query variants, "except", "unless", "provided that") | Confirmation bias |
| Calculation check | Recompute dates and amounts in code | Arithmetic errors |
| Coverage check | Every required fact is `found` or explicitly `missing` | Skipped premises |

NLI weaknesses (negation, exceptions, qualifications, cross-document conflicts) are known. It is one check among several. Log disagreements for human review.

### 3.7 Rewriter (FLAN-T5) and fidelity validator

FLAN-T5 receives only verified findings (claim statements with citation ids) and the requested style. It outputs prose with citation markers carried through. Long outputs are rewritten section by section.

After rewriting, the fidelity validator checks:

1. **Entity and number check:** numbers, dates, names and amounts in the output must all appear in the input.
2. **Negation and modality check:** `not, no, shall, may, must, unless, except, only, provided` must not change between input and output.
3. **Bidirectional NLI:** input entails output and output entails input.
4. **Citation preservation:** every citation marker survives.

Failure: retry with a stricter prompt, then fall back to the unrewritten verified findings.

### 3.8 Final output validator

Re-run quote and support checks on the final text, confirm caveats and "ambiguous" flags survived, no unsupported qualifiers ("clearly", "always") were added, and the answer addresses the ask without extra scope.

### 3.9 Unlimited context: paged memory and chunk-wise reasoning

Context size is not limited by any model's window. The system pages evidence in and out the way an operating system manages RAM and disk, and reasons over one chunk and one step at a time.

**Memory mapping**

| OS concept | In this system |
|---|---|
| RAM (working set) | The few passages and the notebook currently fed to the judgment engine (token budget per call, for example 2k to 4k) |
| Cache | Recall memory (verified notes) |
| Disk | Archive (Qdrant, document store, graph) |
| Page table | The index: chunk ids, version hashes, section tree, extractive summaries, entity and graph links |
| Page fault | A required fact is not in the working set, so the controller retrieves it and pages it in |
| Eviction | Drop passages least relevant to the open sub-questions. Never evict pinned items: the ask, open sub-questions, unresolved conflicts, the notebook |

**What embeddings do (and do not do).** An embedding model does not reason by itself. It gives addressing (find the right page), navigation (section vectors first, then chunk vectors), features for the learned heads (similarity to a sub-question, novelty against the notebook, cluster membership), and deduplication. The reasoning decisions still come from the cross-encoder reranker, extractive QA, NLI and the decision and next-action heads.

**Chunk-wise reasoning (map, notebook, reduce)**

1. **Plan:** the ask becomes a list of sub-questions (the "steps", also the required facts).
2. **Map:** for each candidate chunk, in rerank order and within budget, run QA and NLI against every open sub-question. The output is a finding (span, scores, evidence id), never generated text.
3. **Notebook:** a small structured table, one row per sub-question, holding found spans, conflicts and status. It is persisted and always in the working set, so progress survives paging.
4. **Reduce:** the decision head and conflict check run over the notebook, not over raw text. Counts, comparisons and timelines are computed in code from the extracted values.
5. **Next step:** the next-action head picks the next sub-question or retrieval. Stop when coverage is complete, the budget ends, or the result is `inconclusive`.
6. **Write:** FLAN-T5 receives only the notebook's verified findings, section by section, then the fidelity and output validators run.

**Very large collections (1,000-plus pages)**

- Coarse to fine: section-level vectors, then chunk-level hybrid search, then rerank.
- Cross-document hops use entity and graph links plus gap resolution (section 6).
- Exhaustive asks ("find every document about termination") use scan mode: a cheap filter over all chunks (embedding similarity plus keywords), then the cross-encoder on survivors. The output reports coverage (chunks scanned out of total) so "unlimited" never hides what was not read.

**Limits**

- "Unlimited" means bounded by storage and time, not by a context window. Exhaustive tasks cost time in proportion to corpus size.
- A fact that only makes sense with another page can be missed if no link or retrieval connects them.
- Errors can compound across steps, so verification runs per step, not only at the end.
- The reduce step can only use what the notebook schema captures. A new question shape may need new notebook fields.

**Tests (run in Phase 1, once retrieval exists):** needle-in-haystack recall at 10, 100 and 1,000 pages; page-fault handling when a needed fact is evicted; multi-fact aggregation across distant pages; coverage reporting accuracy; effect of the working-set budget on accuracy, latency and RAM.

### 3.10 Long-form output: chunked, outline-driven writing

FLAN-T5 can contribute to documents of any length by writing small units, since no single call writes more than a short passage. The length comes from the verified findings. The model never fills space with invented content.

**Pipeline**

1. **Outline (code):** built from the notebook according to the task: chronology by date, clause by clause, issue by issue, or document by document. The outline is a tree, and each leaf is bound to a list of verified finding ids.
2. **Write units:** each leaf is split into units of a few findings (input about 300 to 400 tokens, output about 150 to 250 tokens; set the real limits from Experiments A and P). FLAN-T5 rewrites one unit at a time.
3. **Per-unit validation:** the fidelity validator (3.7) runs on every unit. A failure retries with a stricter prompt, then falls back to the plain verified text.
4. **Assembly (code, not generation):** headings, numbering, tables (chronology and party tables built directly from structured data), citations, cross-references and the table of contents.
5. **Global consistency pass (code and encoders):**
   - Glossary: canonical names and defined terms are enforced across units, and variants are flagged.
   - Repetition: embedding similarity between units finds duplicates to merge or remove.
   - Coverage: every verified finding appears once or is marked omitted, and no unit lacks a source.
   - Cross-section conflicts: NLI on sampled pairs of findings about the same fact.
   - Citation integrity: every marker resolves to a real passage.
6. **Checkpointing:** each unit's output, input hash and status are saved to disk. A job can pause and resume, and an edited finding regenerates only the units that depend on it.

**Context passed to each unit** is kept small: the section title, the relevant glossary entries, canonical names and a style instruction. Earlier generated text is not fed back in, which limits drift and keeps units independent.

**Limits**

- Pages come from evidence. A 1,000-page output needs about 1,000 pages worth of verified findings. The system cannot create depth that the sources do not contain.
- FLAN-T5 prose over thousands of units can read as repetitive or stiff. Structured outputs (tables, schedules, clause-by-clause reports) suit it better than flowing narrative.
- Executive summaries and transitions are the riskiest parts. Build summaries from the notebook (extractive), then verify them.
- Time: 1,000 pages is roughly 500,000 words, or about 700,000 tokens. At tens of tokens per second on CPU that takes hours, so run it as a background job and measure real throughput.
- Consistency across units depends on the glossary and the checks, because the model has no memory of earlier units.

**Experiment L (long-form writing, runs in Phase 0, no RAG needed):** feed lists of 200, 1,000 and 5,000 verified claims with citations and generate documents of about 10, 50 and 250 pages. Measure the unit fidelity pass rate, repetition rate, term consistency, coverage, throughput in tokens per second, RAM growth over the run, and resume correctness. Targets: fidelity as in Experiment A, coverage 100 percent, zero units without a citation.

---

## 4. Data schemas

**Judgment output (per ask)**

```json
{
  "ask": "...",
  "task_type": "lookup",
  "required_facts": [
    {"fact": "notice period",
     "status": "found | missing | conflicted",
     "span": "30 days",
     "claim_statement": "The notice period is 30 days.",
     "evidence_ids": ["D3-p12-c2"],
     "qa_confidence": 0.93,
     "nli": {"entail": 0.96, "neutral": 0.03, "contradict": 0.01},
     "second_model_agrees": true}
  ],
  "conflicts": [],
  "decision": {"label": "supported", "confidence": 0.91},
  "next_action": "answer"
}
```

**Entity record**

```json
{
  "entity_id": "E-17",
  "canonical_name": "Ravi Sharma",
  "type": "person",
  "mentions": [{"chunk_id": "D3-p3-c1", "span": "Ravi Sharma", "conf": 0.97},
               {"chunk_id": "D3-p9-c4", "span": "the Lessee", "conf": 0.88}],
  "roles": [{"role": "Lessee", "evidence_id": "D3-p3-c1", "conf": 0.93}],
  "addresses": [{"text": "14 MG Road, Pune 411001", "evidence_id": "D3-p3-c1",
                 "parsed": {"house_number": "14", "road": "MG Road",
                            "city": "Pune", "postcode": "411001"}}],
  "status": "resolved | ambiguous | unresolved",
  "alternatives": []
}
```

---

## 5. Controller loop (pseudocode)

```python
def run_task(ask, kb, cfg):
    state = TaskState(ask=ask)
    plan = ask_analyzer.analyze(ask)            # task type, depth, subqs, queries
    if plan.task_type == "rewrite":
        return rewrite_path(ask)

    state.set_budget(controller.cap(plan.depth, cfg))

    while state.rounds < state.max_rounds:
        notes = [n for n in memory.recall(plan.queries) if memory.revalidate(n)]
        passages = retrieval.search(state.next_queries(plan),
                                    top_k=state.top_k, exclude=state.seen_ids)
        passages = reranker.rank(ask, passages)[:state.keep]
        state.add_evidence(notes, passages)

        entities = entity_engine.run(state.evidence, kb, cfg)    # section 6
        state.add_entities(entities)

        result = judgment.run(plan.subquestions, state.evidence, entities)
        report = verifier.check(result, state.evidence)
        result = result.drop(report.unsupported)

        action = judgment.next_action(result, state)
        if action == "retrieve_more" and state.can_continue():
            state.queue(result.missing_facts, report.conflicts)
            state.rounds += 1
            continue
        if result.decision.label == "supported" and not state.contradiction_checked:
            state.queue(contradiction_queries(result))      # mandatory
            state.contradiction_checked = True
            state.rounds += 1
            continue
        break

    if result.decision.label == "inconclusive" or state.exhausted():
        return abstain(result.missing_facts, result.ambiguous_entities, state.trace)

    memory.write_verified(result, report, entities)
    text = rewriter.rewrite(result.verified_claims, ask)
    final = validator.check(text, result)
    return final if final.ok else result.verified_claims_as_text()
```

---

## 6. Gap resolution (general mechanism, with entities as the worked example)

### 6.0 General mechanism

A **gap** is anything the engine cannot answer from the current context with confidence. Gaps are found by low scores or disagreement between components, not by guessing.

| Gap type | How it is detected | What is fetched | How it is re-read |
|---|---|---|---|
| Unknown term, abbreviation, jargon | Term appears with no definition in context; QA gives low confidence on "What does X mean?" | Definition chunks, glossaries, first-use sentences, other documents using the term | Extractive QA ("What is X?") |
| Ambiguous reference ("it", "the said premises", "the former") | Reference scorer is below threshold | Preceding chunks, defined-term chunks | QA plus NLI on candidate referents |
| Identity or role of an entity | Taggers disagree or are unsure | Party blocks, definitions, signature sections | QA plus pair matcher |
| Missing premise | Coverage check: a required fact has no support | Targeted retrieval built from the sub-question | Extractive QA |
| Conflicting values | NLI conflict between sources | Other versions, dates, amendments, higher-authority sources | Authority and date features, then flag if unresolved |
| Vague criterion ("reasonable time") | Answerability is low | Similar passages and past verified examples | Usually ends as `ambiguous` |
| Unfamiliar task shape | Ask analyzer confidence is low | Similar solved asks from recall memory | Template reuse, else clarifying question |

```python
def resolve_gap(gap, kb, cfg):
    for rnd in range(cfg.max_gap_rounds):               # budget, e.g. 3
        ctx = kb.search(gap.queries(rnd), scope=gap.scope(rnd))   # round 0: same document, later: collection
        ctx = reranker.rank(gap.context, ctx)[:6]
        findings = gap.reread(ctx)                      # QA, NLI or pair matcher, per gap type
        if findings.models_agree and not findings.conflict:
            return gap.close(findings, evidence=ctx)    # verified, can be stored
        gap.add_alternatives(findings)
    return gap.mark("ambiguous" if gap.alternatives else "unresolved")
```

The learning is in-context: retrieved definitions and verified (gap, context, resolution) examples stored in recall memory. No weights change.

The rest of this section applies the mechanism to entities, because entity examples are the easiest to test.

### 6.1 Detection

For each chunk:

1. GLiNER tags `person, organization, address, defined term, date, amount`.
2. A second NER (BERT/RoBERTa) tags people, organizations and locations.
3. libpostal parses every address candidate.
4. Agreement score per mention: both taggers agree on span and type means high confidence. Disagreement, a low score, or a fragment (for example "Plot 14, Sector 5") means unsure.
5. kNN vote: embed the mention and its context, compare with the verified entity example store. Close matches with a consistent label raise confidence, conflicting ones lower it.

### 6.2 Resolution loop (for unsure mentions)

```python
def resolve(mention, kb, cfg):
    for rnd in range(cfg.max_entity_rounds):             # budget, e.g. 3
        scope = "same_document" if rnd == 0 else "collection"
        queries = [
            f'"{mention.text}"',                                   # exact string
            f'{mention.text} (the',                                # defined-term pattern
            f'{mention.text} residing at / having its office at',  # party block pattern
        ]
        ctx = kb.search(queries, scope=scope,
                        chunk_types=["party_block", "definition",
                                     "signature", "schedule"])
        ctx = reranker.rank(mention.context, ctx)[:6]

        answers = [qa.ask(q, ctx) for q in role_questions(mention)]
        # e.g. "Who is the Lessee?", "What is the address of Ravi Sharma?"
        if agreeing(answers, second_model=True) and no_conflict(answers):
            return mention.resolve(answers, evidence=ctx)       # verified
        mention.add_alternatives(answers)

    return mention.mark("ambiguous", alternatives=mention.alternatives)
```

### 6.3 Clustering mentions into entities

- Candidate pairs come from blocking (shared surname, shared token, same defined term, nearby chunks).
- A pairwise matcher scores same-entity likelihood from: string similarity (rapidfuzz), embedding similarity of mention contexts, shared address or role, and an NLI check on the context sentences. Start with logistic regression over these features and train it on labeled pairs from Phase 0.
- Defined terms ("the Lessee", "the Company") link to their definition through extractive QA ("Who is the Lessee?").
- Two entities that share a name but have different addresses or roles stay separate and are flagged `ambiguous` if the evidence cannot separate them.

### 6.4 "Learning" without changing weights

1. **Context retrieval:** the resolution loop pulls definitions and party blocks and re-reads with them.
2. **Entity example store:** verified (span, context, label) triples are saved and used for kNN voting on later mentions.
3. **Optional offline step:** periodically fine-tune GLiNER or the pair matcher on verified examples after human review, then re-run the benchmark before swapping the model in.

Write back only after verification (quote check plus agreeing second model plus no conflict). An unverified result in memory repeats its error forever.

### 6.5 Outputs and failure behavior

- `resolved`: stored with evidence ids.
- `ambiguous`: reported as "two possible addresses for this party, see pages 3 and 17", with the passages.
- `unresolved`: the defining passage was not found. The answer says so and lists what would resolve it.

---

## 7. Adaptive fetch policy

| Ask type | Retrieval | Passages kept per sub-question | Max rounds |
|---|---|---|---|
| Rewrite supplied text | None | 0 | 0 |
| Simple fact | Recall + 1 search | 3 to 5 | 2 |
| Multi-part or comparison | One search per sub-question | 5 to 8 | 3 |
| Entity-heavy or chronology | Iterative + entity resolution + graph | 8 to 12 | 5 |
| Contradiction hunt / full review | Deep iterative | 10 to 15 | 6 |

The ask analyzer proposes the depth, the controller caps it. Escalate depth when passages conflict, a key fact has one weak source, entity status is `ambiguous`, or the ask is high stakes.

Stop when every required fact has support and the contradiction search found nothing new. Abstain when the budget is spent or searches return nothing relevant. The mandatory contradiction search applies before any `supported` answer, because small models stop early.

---

## 8. Models for the PoC (no generative reasoner)

Model versions and licenses change often. Check Hugging Face for newer releases and verify licenses before commercial use.

| Role | Primary | Alternatives |
|---|---|---|
| Embeddings | bge-small-en-v1.5 | bge-m3 (multilingual), e5-small, all-MiniLM-L6-v2 |
| Sparse retrieval | Qdrant sparse vectors (BM25/SPLADE) | fastembed sparse models |
| Reranker | bge-reranker-v2-m3 | MiniLM cross-encoder (faster, weaker) |
| Ask classifier (start) | Zero-shot NLI classifier (DeBERTa-v3 NLI) | Fine-tuned DeBERTa-v3-small later |
| Keyphrases | KeyBERT-style with bge-small | YAKE |
| Entity tagging | GLiNER (medium or multi) | spaCy NER |
| Second NER | dslim/bert-base-NER | RoBERTa NER models |
| Address parsing | libpostal (pypostal) | Rule-augmented regex for Indian PIN codes only as a feature |
| Extractive QA + answerability | deepset/deberta-v3-base-squad2 | roberta-base-squad2, a second model for agreement |
| NLI | MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli | Larger DeBERTa-v3 NLI; ContractNLI-tuned for legal (Phase 3) |
| Pair matcher | Logistic regression or LightGBM over similarity features | Small cross-encoder fine-tuned on labeled pairs |
| Decision and next-action heads | LightGBM or logistic regression | Small MLP |
| Rewriter | Your FLAN-T5 checkpoint | FLAN-T5-large; LaMini-Flan-T5 (non-commercial license on its card) |
| Vector DB | Qdrant (server or local mode) | Qdrant Edge for embedded |
| Graph (optional) | NetworkX for PoC | Kuzu, Neo4j |
| Date and amount tools | dateparser, a small calculator | Duckling |

**Runtimes**

- Encoders: ONNX Runtime with int8 quantization.
- FLAN-T5: CTranslate2 int8.
- libpostal runs natively and is fast, but its model data is large (a few GB).

---

## 9. Training the decision and next-action heads (general data only)

| Head | Public data | Notes |
|---|---|---|
| Decision head | MNLI, ANLI, FEVER (labels), SQuAD2 (answerable or not), HotpotQA (multi-hop) | Build features by running the real pipeline on these sets so training matches deployment |
| Next-action head | Simulated loops: run the pipeline on HotpotQA/SQuAD2 with deliberately incomplete retrieval, label the correct next action (more retrieval vs answer vs abstain) from gold answers | Gold answer reachable with more retrieval means `retrieve_more` |
| Pair matcher | Name-matching and entity-resolution datasets, plus your own labeled pairs | Include hard negatives (same surname, different person) |
| Calibration | Isotonic regression or Platt scaling on held-out data | Confidence must be meaningful, because abstention thresholds depend on it |

Evaluate on held-out sets and on the red-team set (section 12). Pick abstention thresholds on a validation set so unsupported-claim rate stays under target, and report the coverage you lose by doing so.

---

## 10. Phase 0: validation without RAG (start here)

Evidence is pasted into the prompt, which simulates what RAG supplies later. Test each module on its own first.

### Experiment A: rewrite fidelity (FLAN-T5)

Inputs: 50 formal paragraphs and 50 lists of verified claim statements. Tasks: simplify, formalize, shorten, claims-to-paragraph, memo style.

| Metric | Method | Pass target |
|---|---|---|
| Fact preservation | Numbers, dates, names preserved | 100 percent |
| Added-content rate | Entities or numbers in output not in input | 0 percent |
| Negation/modality errors | `not, shall, may, must, unless, except` | Under 2 percent |
| Bidirectional NLI | Entailment both ways | Over 95 percent |
| Fluency | Human rating 1 to 5 | Average 4 or higher |
| Max useful input length | Largest input before quality drops | Record it, it sets chunk size |

Include probes for negation, exceptions, conditional clauses, long lists, units, defined terms, mixed date formats.

### Experiment B: extractive QA and answerability (closed context)

Give 3 to 10 passages (with distractors) and a question.

- B1 single-fact lookup, B2 unanswerable questions, B3 distractor robustness, B4 span exactness (offset match), B5 second-model agreement rate.
- Data: SQuAD2 dev subset plus 40 custom items.
- Targets: unanswerable recall at 90 percent or higher, span exact-match recorded, valid quote rate 100 percent (a span is a substring by construction, so failures indicate offset bugs).

### Experiment C: NLI as a judge

- C1 supported / contradicted / neutral on claim statements built from QA spans using templates.
- C2 negation and exception probes ("shall not", "except where", "unless").
- C3 pairwise conflict detection (two passages with different values).
- Data: MNLI/ANLI dev subsets, ContractNLI if available, 40 custom items.
- Record accuracy per category, and compare 3 to 5 claim templates per question type.

### Experiment D: multi-hop chaining

- 2-hop and 3-hop questions, for example "Who is the Lessee, and what is their address?" or "When does the notice period end?" (extract two facts, then calculate).
- Data: HotpotQA subset plus 30 custom items.
- Record accuracy by hop count. This sets the maximum reliable chain depth.

### Experiment E: entity detection and resolution

Build `data/benchmarks/phase0/entities/`:

1. **E1 detection (short lines):** 150 to 200 lines mixing person names, company names, Indian and international addresses, partial addresses, ambiguous place-names ("Park Street", "Ashok Nagar"). Score precision and recall per label for GLiNER, BERT-NER, libpostal and the combination.
2. **E2 role assignment:** 30 passages with defined terms ("Ravi Sharma (the Lessee)", "ABC Pvt Ltd (the Lessor)"). Ask role and address questions through extractive QA.
3. **E3 resolution with supplied context:** 20 long documents (5 to 30 pages), each with planted ambiguity: shared surname, two people at one address, one person with two addresses, vague references ("the said premises"), abbreviations ("R. Sharma", "Mr. Sharma"). Run the resolution loop with the document chunks as the searchable context. Score: resolved correctly, flagged ambiguous, resolved wrongly. Wrong resolutions are the most important number.
4. **E4 example store effect:** run E3 twice, once with an empty example store and once after verified results from the first documents are saved. Measure improvement, and confirm no wrong examples were stored.

Targets (adjust, but fix before testing): wrong-resolution rate 5 percent or lower, ambiguous cases flagged (not guessed) 85 percent or higher, person and organization F1 recorded, address F1 recorded.

### Experiment F: ask analysis

- 60 realistic asks of varied shape (single, multi-part, comparison, entity-focused, rewrite).
- Score task-type accuracy, depth label accuracy, and sub-question quality (human rating 1 to 5).
- Record how often decomposition fails, and test the fallback (whole-ask query).

### Experiment G: decision head and chain

- Train the decision head on public data (section 9). Evaluate abstention precision and recall, calibration (reliability curve), and unsupported-claim rate on held-out and red-team items.
- Chain test: judgment output into FLAN-T5, then the fidelity validator, to check that meaning survives end to end.

### Experiment P: proposer calibration (what and how much to ask FLAN-T5)

Goal: find which proposer tasks FLAN-T5 does usefully, how much input and how many items it can handle, and where it starts to hallucinate. Needs a small test corpus and gold passages (can use the Phase 1 test set, or pasted passages with known gold).

Ladder (change one dimension at a time):

- **P1 input size:** ask plus context of 128, 256, 512 and 1024 tokens (FLAN-T5 was trained on short inputs, so expect decline past 512).
- **P2 task type:** reframe, decompose, propose queries, list needed facts, propose hypotheses as questions.
- **P3 item count:** request 1, 3, 5 and 8 items.
- **P4 hops:** 1-hop, 2-hop and 3-hop asks.
- **P5 prompt style:** plain instruction, few-shot (2 to 3 examples), step-by-step.
- **P6 sampling:** greedy vs 3 to 5 samples merged by agreement.
- **P7 model size:** your checkpoint first, then the next size up only if needed.

Metrics:

| Metric | Meaning |
|---|---|
| Retrieval lift | Recall@k of the gold passage using proposer queries versus the raw ask alone (the key metric) |
| Sub-question coverage | Share of gold required facts covered by the proposed sub-questions |
| Over-decomposition rate | Proposed sub-questions that are irrelevant |
| Hallucinated-content rate | Proposals with names, numbers, dates or claims not in the ask or context. Record the raw rate and the share the grounding filter catches |
| Format-valid rate | Parseable on the first try |
| Harm rate | Proposals that lower recall below the raw-ask baseline |
| Latency | Seconds per call on the target CPU |

Decision rule: for each proposer task, set the largest input size, item count and hop count where retrieval lift is positive and hallucinated content after the filter is at or below target (suggest 2 percent). Inside that limit the proposer is used. Outside it, or for tasks with no lift over the templates, fall back to the analyzer's templates.

### Experiment H: general-purpose reasoning from context (domain-agnostic)

This experiment checks the central claim: the system reasons from supplied context, not from weights.

- **H1 Counterfactual context:** passages state altered or invented facts ("In this handbook a sprint lasts 9 days", swapped capitals, changed rule values). Ask questions whose real-world answer differs. Metric: context-faithfulness rate (answer matches the context, not the memorized fact). Target 95 percent or higher.
- **H2 Invented terms:** define made-up terms only in the context ("a zorb is a refund issued after 14 days") and ask questions using them. Then ask the same questions with the definition removed. Metrics: correct with definition; `unresolved` (not guessed) without it. Target for the second case: 90 percent or higher.
- **H3 Cross-domain:** 20 items each in at least five unrelated domains (software documentation, recipes, sports rules, finance, medical leaflets, legal). Compare accuracy per domain. Large gaps indicate domain leakage or domain-specific weakness.
- **H4 General reasoning skills:** comparison, counting and aggregation, conditional logic (if / unless / provided that), ordering and timelines, numeric calculation, multi-source synthesis. Record which skills the encoder-only engine handles and which it fails.
- **H5 Provenance check:** confirm that outputs separate `evidence`, `background` and `inference`, that factual claims with only `background` support are dropped, and measure how often `background` was used.
- **H6 Gap resolution beyond entities:** run the gap types in section 6.0 (unknown term, ambiguous reference, missing premise, vague criterion) on 10 items each with the real resolution loop.

Decision gate from H4: if the engine fails reasoning skills your target tasks need (for example aggregation or conditional logic), record which ones. The FLAN-T5 proposer (section 3.2.1) is the first fix because it is already in the stack. No other generative model is added unless Experiment P and H4 both show it is needed.

### Phase 0 exit criteria

- Unsupported-claim rate 5 percent or lower at the chosen abstention threshold.
- Unanswerable recall 90 percent or higher.
- Wrong entity resolution 5 percent or lower, ambiguity flagged 85 percent or higher.
- Rewrite fidelity targets met.
- Maximum reliable hop count recorded. If it is 2, the controller must decompose asks into at most 2-hop steps.
- Latency and peak RAM on the target laptop recorded for every model.
- Context-faithfulness 95 percent or higher (H1) and unresolved-instead-of-guessed 90 percent or higher (H2).
- Per-domain accuracy gap in H3 recorded, and reasoning skills the engine cannot do (H4) listed explicitly.

### Phase 0 harness (skeleton)

```python
# eval/phase0_qa.py
import re, time

norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()

def span_in_passage(span, passage):
    return norm(span) in norm(passage)

def score_qa(item, qa_out):
    # qa_out: {"span": str|None, "score": float, "no_answer": float, "passage_id": str}
    answerable = item["answerable"]
    abstained = qa_out["no_answer"] >= item["tau_no_answer"] or qa_out["span"] is None
    return {
        "correct_abstain": (not answerable) and abstained,
        "false_answer": (not answerable) and not abstained,
        "missed_answer": answerable and abstained,
        "exact_match": answerable and not abstained and
                       norm(qa_out["span"]) == norm(item["gold"]),
        "span_valid": (not abstained) and
                      span_in_passage(qa_out["span"], item["passages"][qa_out["passage_id"]]),
    }
```

```python
# eval/entities.py
from gliner import GLiNER

LABELS = ["person name", "organization", "address", "defined term", "date", "amount"]
model = GLiNER.from_pretrained("urchade/gliner_medium-v2.1")   # check current release

def detect(text, threshold=0.4):
    return model.predict_entities(text, LABELS, threshold=threshold)

def prf(pred, gold):
    # pred and gold: sets of (start, end, label)
    tp = len(pred & gold)
    p = tp / max(1, len(pred)); r = tp / max(1, len(gold))
    f = 2 * p * r / max(1e-9, p + r)
    return p, r, f
```

```python
# eval/rewrite_fidelity.py
import re
NUM = re.compile(r"\b\d[\d,./-]*\b")
MODAL = re.compile(r"\b(not|no|shall|may|must|unless|except|only|provided)\b", re.I)

def fidelity(src, out):
    sn, on = set(NUM.findall(src)), set(NUM.findall(out))
    sm = sorted(m.lower() for m in MODAL.findall(src))
    om = sorted(m.lower() for m in MODAL.findall(out))
    return {"numbers_dropped": sorted(sn - on),
            "numbers_added": sorted(on - sn),
            "modal_changed": sm != om}
```

---

## 11. Later phases

**Phase 1: add RAG.** Ingest a public document set (public contracts, CUAD, ContractNLI documents, or non-confidential samples) into Qdrant with hybrid indexing and chunk typing. Evaluate retrieval alone (Recall@5/@10, MRR, answer-passage-present rate), reranker lift, then connect the Phase 0 engine. Compare oracle-evidence accuracy (Phase 0) with retrieved-evidence accuracy. The gap is the retrieval loss. Report three numbers every run: retrieval quality, judgment quality given correct evidence, end-to-end quality.

**Phase 2: memory, verification loop, entity resolution at scale.** Implement recall memory with source revalidation, the full verification engine, the contradiction search and the budgeted loop. Run E3 against the real retrieval stack (collection-wide scope). Test repeated questions (memory hit rate and correctness), changed documents (stale note invalidation), conflicting documents (conflict flags). Add GraphRAG only if cross-document questions fail on plain hybrid retrieval.

**Phase 3: attach the legal domain.** Ingest the private corpus with structure-aware chunking (clauses, headings, schedules, annexures, party blocks, signature pages). Add ContractNLI and CUAD-style evaluation plus 30 real tasks reviewed by a lawyer. Optionally swap in a legal-tuned NLI verifier. Outputs state what the documents establish, what is inferred, and what needs a lawyer's judgment. Current law and precedent need a separate authoritative research corpus. Outputs are drafts for lawyer review, not filing-ready.

---

## 12. Evaluation framework

| Layer | Metric |
|---|---|
| Retrieval | Recall@k, MRR, answer-passage-present rate |
| Reranker | Lift in Recall@5 |
| Entity detection | Precision, recall, F1 per label |
| Entity resolution | Correct, flagged ambiguous, wrong (wrong is the headline number) |
| Extractive QA | Exact match, span validity, unanswerable precision and recall |
| NLI | Accuracy per category, negation and exception probe accuracy |
| Decision head | Calibration, abstention precision and recall, unsupported-claim rate |
| Rewriter | Fidelity checks in 10.A |
| Memory | Hit rate, stale-note catch rate, wrong-note-written count (target 0) |
| End to end | Accuracy, citation accuracy, missed issues, abstention accuracy |
| System | Latency p50 and p95, peak RAM, ingestion pages per minute |

**Red-team set:** unanswerable questions, planted contradictions, near-duplicate clauses with different numbers, negations, outdated versions of a document, same-name different-person cases, addresses that fit two parties, and passages containing instructions ("ignore the above"). The pipeline must treat passages as data and must never execute requests found inside them.

**Logging:** for every task, persist ask, plan, queries, retrieved ids, entity table, per-fact scores, decision, verification report, final output and timings. This attributes each failure to a stage.

---

## 13. Repository layout

```
project/
  README.md
  pyproject.toml
  configs/
    models.yaml            # model names, quantization, runtime
    budgets.yaml           # depth presets, caps, thresholds
  src/
    controller/
      loop.py
      budget.py
    analysis/
      task_classifier.py
      keyphrases.py
      decompose.py         # templates + tagger
      query_variants.py
    retrieval/
      ingest.py            # parse, chunk, type, hash, index
      chunking.py
      hybrid_search.py     # Qdrant dense + sparse
      reranker.py
      graph.py             # optional
    entities/
      detect.py            # GLiNER + BERT-NER + libpostal
      resolve.py           # RAG resolution loop
      cluster.py           # pair matcher
      example_store.py     # kNN voting store
    judgment/
      qa.py                # extractive QA + answerability
      nli.py               # support and conflict
      chain.py             # hop chaining
      heads.py             # decision and next-action heads
      calc.py              # dates and amounts
    memory/
      recall_store.py      # SQLite
      revalidate.py
      scoring.py
    verify/
      quote_check.py
      support_check.py
      agreement.py
      conflict_check.py
      rewrite_fidelity.py
    rewrite/
      flan_t5.py           # CTranslate2
    schemas/
      judgment.json
      entity.json
      note.json
    eval/
      phase0_qa.py
      entities.py
      rewrite_fidelity.py
      retrieval_eval.py
      e2e_eval.py
      redteam/
  data/
    benchmarks/
  tests/
```

---

## 14. Hardware and optimization

- Fix the target laptop (CPU model, cores, RAM) up front. Record latency and peak RAM per model.
- Quantize encoders to int8 with ONNX Runtime and FLAN-T5 with CTranslate2 int8. Re-run Phase 0 after quantizing to confirm accuracy held.
- Keep embedder, reranker, QA and NLI resident. Load FLAN-T5 only when rewriting.
- Batch embedding, reranking and NLI calls. Cache embeddings and (query, chunk) scores.
- Cap NLI and QA calls per round (candidate pairs from blocking only), because cross-encoder cost grows with pairs.
- Ingestion dominates for 1,000-plus pages. Parse and embed once, update incrementally by document version hash.
- Rough memory budget (verify on your machine): embedder 0.1 to 0.5 GB, reranker 0.5 to 1 GB, QA 0.4 to 0.8 GB, NLI 0.4 to 1 GB, FLAN-T5 int8 0.3 to 1 GB, GLiNER and BERT-NER about 0.5 to 1 GB total, libpostal data a few GB on disk, Qdrant depends on corpus size.

---

## 15. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Ask decomposition fails on unusual or multi-clause asks | Templates plus tagger, whole-ask fallback, clarifying question to the user, measure in Experiment F |
| Multi-hop accuracy drops past 2 hops | Controller limits chains, one hop per round, calculator for arithmetic |
| NLI misses negation or exceptions | Dedicated probes, contradiction search with exception-phrased queries, cross-model agreement, human review for high stakes |
| Template claim statements confuse NLI | Test several templates per question type; keep best per type |
| Wrong entity resolution | Second tagger agreement, QA agreement, conflict check, `ambiguous` as a valid output, wrong-resolution rate as headline metric |
| Wrong notes persist in memory | Write only after verification, store source pointers, revalidate on use, audit wrong-note count |
| Retrieval misses the defining passage | Chunk typing (party blocks, definitions), collection-wide second round, `unresolved` output |
| Small heads miscalibrated | Calibrate on held-out data, set thresholds on validation set, report lost coverage |
| Rewriter drifts | Fidelity validator, fallback to verified findings text |
| Prompt injection inside documents | Passages are data; controller never executes instructions from retrieved text; red-team items |
| Stale or changed documents | Version hashes, note revalidation |
| libpostal weaker on informal Indian addresses | Combine with GLiNER, add PIN-code and locality features, test on real samples |
| Licenses | Verify each model license before commercial use (LaMini family is listed non-commercial) |
| Building something nobody pays for | After Phase 3, test with real users and compare against existing products |

---

## 16. Roadmap

| Week | Work | Output |
|---|---|---|
| 1 | Phase 0 harness; Experiments A, B, C, P (proposer calibration) | QA, NLI and rewrite baselines |
| 2 | Experiments D, E (detection, roles, resolution with supplied context), F | Entity and chaining report; max reliable hop count |
| 3 | Train decision and next-action heads; Experiment G; controller skeleton and schemas | Phase 0 report, go/no-go on encoder-only reasoning |
| 4 | Phase 1: ingestion, chunk typing, hybrid search, reranker, retrieval eval | Retrieval report |
| 5 | Connect engine to retrieval; verification engine; entity resolution against retrieval | End-to-end v0 |
| 6 | Phase 2: recall memory, example store, contradiction search, red team | End-to-end v1 |
| 7 to 8 | Phase 3: legal corpus, 30 lawyer-reviewed tasks, latency tuning | PoC decision report |

Decision gate at the end of Phase 0 (week 3): if the encoder-only engine cannot reach the exit criteria, report which module fails (decomposition, multi-hop, NLI on exceptions) before changing the design. Final gate after Phase 3: continue, adjust, or stop, based on measured accuracy, abstention behavior, speed on the target laptop and user willingness to pay.

---

## 17. First commands (Phase 0 setup)

```bash
python -m venv .venv && source .venv/bin/activate
pip install transformers sentencepiece ctranslate2 onnxruntime optimum \
            sentence-transformers qdrant-client gliner rapidfuzz dateparser \
            lightgbm scikit-learn pydantic jsonschema datasets

# libpostal needs the C library and data installed first, then:
pip install postal

# convert FLAN-T5 to int8 CTranslate2 (replace with your checkpoint path)
ct2-transformers-converter --model <your-flan-t5-path> \
    --output_dir models/flan-t5-ct2 --quantization int8
```

Then build `data/benchmarks/phase0/` per section 10, implement the harness files in `src/eval/`, and run Experiments A to G against the exit criteria.
