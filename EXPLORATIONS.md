# Explorations

An exploration is one research step. Status is `todo`, `open`, or `closed`.
Closed results below were written by `lab/exp_*/run.py` into `data/exp_*/results.json` and copied here by `lab/render_explorations.py`.
Do not edit the numbers by hand. Re-run the exploration and render again.

Generative language models were not used in any exploration.

## EXP-001 Task controller, schemas, and budgets

- Status: `closed`
- Goal: Show that budgets, schema checks, and the fail-safe abstain path are plain code, and that instructions inside a passage are not executed.
- Method: Validate three judgment payloads (valid, repairable, irreparable), cap a deep depth proposal at medium, and run the controller on a deposit question plus a passage that contains an exec instruction.
- Referenced files:
- `lab/exp_001_controller/run.py`
- `lab/common/budget.py`
- `lab/common/engine.py`
- `lab/common/schemas.py`
- `lab/common/harness.py`
- `lab/common/ask.py`
- `lab/common/index.py`
- `lab/common/nli.py`
- `lab/common/qa.py`
- `lab/common/textutil.py`
- `lab/common/verify.py`
- `lab/config/budgets.json`
- `data/exp_001_controller/results.json`
- Results: Valid judgments pass. A string confidence is repaired once to 0.8. An irreparable decision abstains (repair attempted: True). A proposed deep fetch is capped to medium with max_rounds 3 (light stays at 2). Deposit question decision is supported. A passage that tells the system to exec a shell command does not create a file (injection decision contradicted: Ambiguous: sources conflict. Insufficient evidence.).
```json
{
  "valid_schema_accepted": true,
  "string_confidence_repaired": true,
  "repaired_confidence": 0.8,
  "irreparable_abstains": true,
  "repair_attempted_once": true,
  "repair_disabled_still_fails": true,
  "incomplete_note_rejected": true,
  "depth_cap_applied": true,
  "capped_rounds": 3,
  "light_rounds": 2,
  "passages_are_data": true,
  "injection_file_created": false,
  "deposit_decision": "supported",
  "deposit_text": "The security deposit is INR 50000. [D1-p1-c1]",
  "injection_decision": "contradicted",
  "injection_text": "Ambiguous: sources conflict. Insufficient evidence.",
  "trace_has_retrieved_ids": true
}
```

Elapsed seconds: 0.0142. Peak RSS MB: 113.0.
- Scale-down: The loop is run on three passages, not a full archive. Logging is an in-memory trace rather than a log service.
- Conclusion: The controller enforces schema validity, a single repair, depth caps, and the rule that retrieved text is data. 

## EXP-002 Ask analyzer templates

- Status: `closed`
- Goal: Measure task-type accuracy, depth accuracy, and template decomposition on 60 asks without a generative proposer.
- Method: Rule cues classify task type and depth. Sub-questions come from conjunction splits and per-type templates. A fact counts as covered when half of its content tokens appear in a sub-question. The raw ask is always retained as a query.
- Referenced files:
- `lab/exp_002_ask_analyzer/run.py`
- `lab/common/ask.py`
- `lab/common/textutil.py`
- `lab/common/harness.py`
- `data/exp_002_ask_analyzer/asks.json`
- `data/exp_002_ask_analyzer/results.json`
- Results: On 60 hand-labeled asks, task-type accuracy is 0.95 and depth accuracy is 0.9333. Mean gold-fact coverage of template sub-questions is 0.8667. Decomposition failure rate (coverage under 0.5) is 0.1167. The raw ask stays in the query list for every item: True. No human 1-to-5 rating was collected; the automatic proxy is 4.4667. Misses: F09, F17, F20, F30.
```json
{
  "n": 60,
  "task_type_accuracy": 0.95,
  "depth_accuracy": 0.9333,
  "mean_fact_coverage": 0.8667,
  "decomposition_failure_rate": 0.1167,
  "multi_fact_count": 19,
  "multi_fact_full_coverage_rate": 0.8947,
  "raw_ask_always_in_queries": true,
  "automatic_quality_proxy_1_to_5": 4.4667,
  "human_rating_collected": false,
  "misses": [
    "F09",
    "F17",
    "F20",
    "F30"
  ]
}
```

Elapsed seconds: 0.0021. Peak RSS MB: 12.39.
- Scale-down: Sixty original asks stand in for a larger labeled set. Experiment F's human 1-to-5 rating is not fabricated; only an automatic coverage proxy is reported.
- Conclusion: Template analysis covers ordinary asks and keeps the raw ask as a fallback. Unusual multi-clause asks remain the weak spot, which matches the architecture's known limit. A human sub-question rating was not collected.

## EXP-003 Structure-aware chunking

- Status: `closed`
- Goal: Chunk a small contract-shaped document by headings, pages, and block type, and keep summaries extractive.
- Method: Headings and page markers split the document. Each chunk stores doc id, version hash, page, section path, offsets, and chunk type. Summaries are the highest-salience sentences already in the chunk.
- Referenced files:
- `lab/exp_003_chunking/run.py`
- `lab/common/chunking.py`
- `lab/common/textutil.py`
- `lab/common/harness.py`
- `data/exp_003_chunking/document.txt`
- `data/exp_003_chunking/results.json`
- Results: The sample document produced 5 chunks with types {'party_block': 1, 'definition': 1, 'clause': 1, 'schedule': 1, 'signature': 1}. Missing expected types: none. All chunks share one version hash: True. Extractive summaries are substrings and are marked not evidence: True. A 80-sentence obligation block split into 19 chunks (max 50 words) with 18 adjacent overlapping pairs. Pages seen: [1, 2, 3, 4, 5].
```json
{
  "chunks": 5,
  "chunk_types": {
    "party_block": 1,
    "definition": 1,
    "clause": 1,
    "schedule": 1,
    "signature": 1
  },
  "expected_types_found": [
    "clause",
    "definition",
    "party_block",
    "schedule",
    "signature"
  ],
  "missing_expected_types": [],
  "word_counts": [
    25,
    13,
    24,
    9,
    13
  ],
  "long_doc_chunks": 19,
  "long_doc_max_words": 50,
  "adjacent_overlap_pairs": 18,
  "single_version_hash": true,
  "version_hash": "sha256:46cf631e177d9b743288f155165251e0a4b4646623d18639c7981db64b524a22",
  "summaries_are_substrings": true,
  "summaries_marked_not_evidence": true,
  "sample_summary": "Ravi Sharma (the Lessee) residing at 14 MG Road, Pune 411001. ABC Pvt Ltd (the Lessor) having its office at 48 Park Street, Kolkata 700016.",
  "pages": [
    1,
    2,
    3,
    4,
    5
  ]
}
```

Elapsed seconds: 0.0012. Peak RSS MB: 15.97.
- Scale-down: One short document plus one generated long clause. Token counts are whitespace words, not a model tokenizer. Production target of 200 to 400 tokens was not the setting for the short sample.
- Conclusion: Chunk metadata and extractive summaries behave as specified on this sample. The word-window settings used here are smaller than the 200 to 400 token production window so the sample still splits.

## EXP-004 Hybrid retrieval and rerank

- Status: `closed`
- Goal: Measure dense-plus-sparse retrieval, reranker lift, and whether one entity link recovers a cross-passage address.
- Method: Okapi BM25 and TF-IDF cosine are min-max normalized and averaged. A lexical coverage score reranks the top 30. The graph links Lessee to Ravi Sharma and then to the residence passage, which does not contain the word Lessee.
- Referenced files:
- `lab/exp_004_hybrid_retrieval/run.py`
- `lab/common/index.py`
- `lab/common/graph.py`
- `lab/common/textutil.py`
- `lab/common/harness.py`
- `data/exp_004_hybrid_retrieval/corpus.json`
- `data/exp_004_hybrid_retrieval/results.json`
- Results: On 20 queries over 35 passages, hybrid Recall@5 is 1.0, Recall@10 is 1.0, MRR is 1.0, and answer-passage-present@10 is 1.0. Reranking the top 30 changes Recall@5 to 1.0 (lift 0.0). The Lessee-address hop is in the lexical top 5: False. After the entity-link expansion it is present: True.
```json
{
  "n_queries": 20,
  "n_passages": 35,
  "hybrid_recall_at_5": 1.0,
  "hybrid_recall_at_10": 1.0,
  "rerank_recall_at_5": 1.0,
  "reranker_lift_recall_at_5": 0.0,
  "mrr": 1.0,
  "answer_passage_present_at_10": 1.0,
  "graph_query": "Lessee address",
  "lexical_top5": [
    "P05",
    "P01",
    "P02",
    "P03",
    "P04"
  ],
  "lexical_hits_address": false,
  "graph_expanded_ids": [
    "P01",
    "P02",
    "P03",
    "P04",
    "P05",
    "P07"
  ],
  "graph_hits_address": true
}
```

Elapsed seconds: 0.0219. Peak RSS MB: 113.04.
- Scale-down: In-memory BM25 and TF-IDF stand in for Qdrant dense plus sparse vectors and a cross-encoder reranker. The corpus is 35 passages, not a 1,000-page collection.
- Conclusion: Hybrid search finds the labeled passage for most of these queries. The entity link is what connects Lessee to the residence sentence when that sentence does not repeat the role word.

## EXP-005 Extractive QA and answerability

- Status: `closed`
- Goal: Measure span exactness, unanswerable abstention, distractor robustness, and quote validity for lexical extractive QA.
- Method: Two sentence scorers (unigram coverage and bigram overlap) pick a passage. The span is a date, person, amount, or the complement of 'is/means' copied from that sentence. Abstain when the best score is below 0.34. Scoring uses the architecture's score_qa helper.
- Referenced files:
- `lab/exp_005_extractive_qa/run.py`
- `lab/common/qa.py`
- `lab/common/harness.py`
- `lab/common/textutil.py`
- `data/exp_005_extractive_qa/items.json`
- `data/exp_005_extractive_qa/results.json`
- Results: On 40 original items (tau 0.34), exact match on answerable items is 0.5357 and contained-span match is 0.8214. Unanswerable recall is 1.0 (false-answer rate 0.0). When the extractor answers, the span is a substring of the chosen passage 1.0 of the time. The second lexical extractor agrees on 0.8421 of answered items.
```json
{
  "n": 40,
  "tau": 0.34,
  "exact_match_on_answerable": 0.5357,
  "contained_match_on_answerable": 0.8214,
  "unanswerable_recall": 1.0,
  "false_answer_rate_on_unanswerable": 0.0,
  "missed_answer_rate": 0.3214,
  "span_valid_rate_when_answered": 1.0,
  "second_extractor_agreement_when_answered": 0.8421,
  "answered": 19,
  "abstained": 21
}
```

Elapsed seconds: 0.0029. Peak RSS MB: 12.39.
- Scale-down: Forty original items replace the SQuAD2 dev subset plus 40 custom items. No pretrained QA checkpoint is loaded.
- Conclusion: Quote validity holds when a span is returned, because the span is copied from the passage. Unanswerable recall meets the 90 percent Phase 0 target on this set.

## EXP-006 NLI judge and claim templates

- Status: `closed`
- Goal: Compare claim templates and measure support, contradiction, negation, and exception behavior of the lexical judge.
- Method: Each gold relation is turned into a hypothesis by three templates. The judge uses token coverage, number mismatch, and polarity. Exception words are not given a special parser, so that weakness can show up in the score.
- Referenced files:
- `lab/exp_006_nli_judge/run.py`
- `lab/common/nli.py`
- `lab/common/textutil.py`
- `lab/common/harness.py`
- `data/exp_006_nli_judge/items.json`
- `data/exp_006_nli_judge/results.json`
- Results: Three claim templates were scored on 30 premise/span pairs. Accuracy by template: {'T1': 0.7667, 'T2': 0.7667, 'T3': 0.7}. Best template is T1. On that template, number conflicts are 1.0, negation is 1.0, and exception/qualification probes are 0.0. Category breakdown: {'exception': 0.0, 'negation': 1.0, 'neutral': 1.0, 'number': 1.0, 'supported': 0.875}.
```json
{
  "n_base_items": 30,
  "template_accuracy": {
    "T1": 0.7667,
    "T2": 0.7667,
    "T3": 0.7
  },
  "best_template": "T1",
  "accuracy_by_category_best_template": {
    "exception": 0.0,
    "negation": 1.0,
    "neutral": 1.0,
    "number": 1.0,
    "supported": 0.875
  },
  "negation_accuracy": 1.0,
  "exception_accuracy": 0.0,
  "number_conflict_accuracy": 1.0,
  "pairwise_conflict_note": "Number mismatches are the pairwise value test; exception probes are expected to be weaker."
}
```

Elapsed seconds: 0.0022. Peak RSS MB: 12.32.
- Scale-down: MNLI, ANLI, and ContractNLI were not downloaded. Thirty original pairs replace those dev subsets plus 40 custom items.
- Conclusion: Template T1 is the strongest of the three on this set. Number mismatches and direct negation are handled more reliably than except/unless/provided qualifications.

## EXP-007 Multi-hop chaining

- Status: `closed`
- Goal: Measure 2-hop and 3-hop extractive chaining, including date arithmetic done in code.
- Method: Each hop inserts the previous span into the next question and runs extractive QA. Date endings call add_period on the extracted start and length. A chain is correct only if every hop matches.
- Referenced files:
- `lab/exp_007_hop_chain/run.py`
- `lab/common/qa.py`
- `lab/common/calc.py`
- `lab/common/nli.py`
- `lab/common/textutil.py`
- `lab/common/harness.py`
- `data/exp_007_hop_chain/items.json`
- `data/exp_007_hop_chain/results.json`
- Results: Chain accuracy on 12 items is 0.5833. 2-hop accuracy is 0.7778 (n=9). 3-hop accuracy is 0.0 (n=3). Calculator checks: 1.0 on 2 cases. Recorded maximum reliable hop count at the 0.5 cutoff used here: 2.
```json
{
  "n": 12,
  "chain_accuracy": 0.5833,
  "accuracy_2hop": 0.7778,
  "n_2hop": 9,
  "accuracy_3hop": 0.0,
  "n_3hop": 3,
  "calculator_cases": 2,
  "calculator_accuracy": 1.0,
  "max_reliable_hop_count": 2
}
```

Elapsed seconds: 0.0353. Peak RSS MB: 28.7.
- Scale-down: Twelve original chains replace HotpotQA plus 30 custom items. No pretrained QA model is loaded.
- Conclusion: The reliable hop depth on this small set, using a 0.5 accuracy cutoff, is 2. The controller should keep asks inside that depth and send arithmetic to the calculator.

## EXP-008 Entity detection and roles

- Status: `closed`
- Goal: Score rule taggers per label, flag ambiguous place names, parse an address, and answer role questions from the passage.
- Method: A primary rule tagger marks person, organization, address, defined term, date, and amount. A stricter second tagger covers titled people and suffixed organizations. Exact character offsets are compared with gold. Role questions use extractive QA.
- Referenced files:
- `lab/exp_008_entity_detect/run.py`
- `lab/common/entities.py`
- `lab/common/qa.py`
- `lab/common/textutil.py`
- `lab/common/harness.py`
- `lab/common/nli.py`
- `data/exp_008_entity_detect/lines.json`
- `data/exp_008_entity_detect/results.json`
- Results: On 52 lines, overall exact-span F1 is 0.8866 (precision 0.9556, recall 0.8269). Person F1 0.9048, organization F1 0.8571, address F1 0.875, defined term F1 1.0, date F1 1.0, amount F1 0.7273. Easy-slice F1 is 0.962; hard-slice F1 is 0.4615. Ambiguous place names were flagged unsure in 0.6667 of 3 cases. Role and address questions: 0.9167 on 12 passages. Address parse of the sample: {'house_number': '14', 'road': 'MG Road', 'city': 'Pune', 'postcode': '411001'}.
```json
{
  "lines": 52,
  "overall": {
    "precision": 0.9556,
    "recall": 0.8269,
    "f1": 0.8866,
    "tp": 43
  },
  "per_label": {
    "person": {
      "precision": 0.9048,
      "recall": 0.9048,
      "f1": 0.9048,
      "tp": 19
    },
    "organization": {
      "precision": 1.0,
      "recall": 0.75,
      "f1": 0.8571,
      "tp": 6
    },
    "address": {
      "precision": 1.0,
      "recall": 0.7778,
      "f1": 0.875,
      "tp": 7
    },
    "defined term": {
      "precision": 1.0,
      "recall": 1.0,
      "f1": 1.0,
      "tp": 3
    },
    "date": {
      "precision": 1.0,
      "recall": 1.0,
      "f1": 1.0,
      "tp": 4
    },
    "amount": {
      "precision": 1.0,
      "recall": 0.5714,
      "f1": 0.7273,
      "tp": 4
    }
  },
  "easy_f1": 0.962,
  "hard_f1": 0.4615,
  "ambiguous_place_flag_rate": 0.6667,
  "ambiguous_place_n": 3,
  "address_parse_sample": {
    "house_number": "14",
    "road": "MG Road",
    "city": "Pune",
    "postcode": "411001"
  },
  "role_questions": 12,
  "role_accuracy": 0.9167
}
```

Elapsed seconds: 0.0024. Peak RSS MB: 119.18.
- Scale-down: 52 short lines and 12 role passages replace the blueprint's 150 to 200 detection lines and 30 role passages. GLiNER, BERT-NER, and libpostal are not loaded.
- Conclusion: Exact-span F1 is high on easy titled names, suffixed organizations, and fully patterned addresses, and lower on the hard slice (bare company names, amounts in words, lowercase names, courts). Ambiguous place names are flagged rather than treated as high-confidence addresses.

## EXP-009 Entity resolution and example store

- Status: `closed`
- Goal: Measure wrong resolutions, ambiguous flags, a pair matcher, and whether verified examples are stored without errors.
- Method: Documents are chunked and passed through the resolution loop. Shared surnames and two addresses force an ambiguous status. The pair matcher is logistic regression on string and context features. The example store accepts only resolved mentions that match the gold name.
- Referenced files:
- `lab/exp_009_entity_resolve/run.py`
- `lab/common/entities.py`
- `lab/common/chunking.py`
- `lab/common/qa.py`
- `lab/common/textutil.py`
- `lab/common/harness.py`
- `data/exp_009_entity_resolve/docs.json`
- `data/exp_009_entity_resolve/results.json`
- Results: On 6 short documents, wrong resolutions are 0 (rate 0.0). Ambiguous cases flagged: 3 of 3 (rate 1.0). Clearly unique people resolved correctly: 2 of 2. Held-out pair accuracy is 1.0. Example store size 2, wrong examples stored 0. Confidence on a repeated Ravi Sharma line moved from 0.62 to 0.67.
```json
{
  "documents": 6,
  "wrong_resolutions": 0,
  "wrong_resolution_rate": 0.0,
  "ambiguous_gold": 3,
  "ambiguous_flagged": 3,
  "ambiguous_flag_rate": 1.0,
  "resolved_gold": 2,
  "resolved_correct": 2,
  "pair_heldout_accuracy": 1.0,
  "doc5_pair_decisions": [],
  "example_store_size": 2,
  "wrong_examples_stored": 0,
  "confidence_before_store": 0.62,
  "confidence_after_store": 0.67,
  "outcomes": [
    {
      "id": "E3-1",
      "status": "resolved",
      "correct": true
    },
    {
      "id": "E3-2",
      "status": "ambiguous",
      "text": "Mr. Sharma",
      "wrong": false
    },
    {
      "id": "E3-3",
      "status": "ambiguous",
      "text": "Kapil Menon",
      "wrong": false
    },
    {
      "id": "E3-4",
      "status": "ambiguous",
      "text": "R. Sharma",
      "wrong": false
    },
    {
      "id": "E3-5",
      "found": [
        "resolved",
        "resolved"
      ],
      "wrong": false
    },
    {
      "id": "E3-6",
      "status": "resolved",
      "correct": true
    }
  ]
}
```

Elapsed seconds: 0.0095. Peak RSS MB: 121.75.
- Scale-down: Six short documents replace 20 documents of 5 to 30 pages. The searchable context is the document itself, not a collection-wide index.
- Conclusion: Wrong resolution is the headline number and is reported above. Ambiguous shared names are flagged instead of guessed when the rule can see two full names. No wrong example was written when the store required a gold-matching resolved span.

## EXP-010 Gap resolution loop

- Status: `closed`
- Goal: Run the budgeted gap loop on unknown terms, ambiguous references, missing premises, conflicting values, and vague criteria.
- Method: Each round searches the supplied passages, reranks, and re-reads with extractive QA. Disagreeing spans stay open. After at most 3 rounds the gap is resolved, ambiguous, or unresolved. No weights change.
- Referenced files:
- `lab/exp_010_gap_resolution/run.py`
- `lab/common/index.py`
- `lab/common/qa.py`
- `lab/common/nli.py`
- `lab/common/textutil.py`
- `lab/common/harness.py`
- `data/exp_010_gap_resolution/items.json`
- `data/exp_010_gap_resolution/results.json`
- Results: Gap resolution accuracy on 12 items is 0.8333. By type: {'unknown_term': 1.0, 'ambiguous_reference': 0.3333, 'missing_premise': 1.0, 'conflicting_values': 1.0, 'vague_criterion': 1.0}. Conflicts and vague criteria are closed as ambiguous. Missing definitions with no passage stay unresolved.
```json
{
  "n": 12,
  "accuracy": 0.8333,
  "by_gap": {
    "unknown_term": 1.0,
    "ambiguous_reference": 0.3333,
    "missing_premise": 1.0,
    "conflicting_values": 1.0,
    "vague_criterion": 1.0
  },
  "max_rounds": 3,
  "rows": [
    {
      "id": "G01",
      "gap": "unknown_term",
      "gold_status": "resolved",
      "status": "resolved",
      "span": "a refund issued after 14 days",
      "round": 0,
      "evidence_id": "P0",
      "correct": true
    },
    {
      "id": "G02",
      "gap": "unknown_term",
      "gold_status": "unresolved",
      "status": "unresolved",
      "span": null,
      "alternatives": [],
      "correct": true
    },
    {
      "id": "G03",
      "gap": "unknown_term",
      "gold_status": "resolved",
      "status": "resolved",
      "span": "30 days",
      "round": 0,
      "evidence_id": "P0",
      "correct": true
    },
    {
      "id": "G04",
      "gap": "ambiguous_reference",
      "gold_status": "resolved",
      "status": "resolved",
      "span": "The said premises include a parking slot.",
      "round": 0,
      "evidence_id": "P1",
      "correct": false
    },
    {
      "id": "G05",
      "gap": "ambiguous_reference",
      "gold_status": "resolved",
      "status": "resolved",
      "span": "Kapil Iyer",
      "round": 0,
      "evidence_id": "P0",
      "correct": true
    },
    {
      "id": "G06",
      "gap": "ambiguous_reference",
      "gold_status": "unresolved",
      "status": "resolved",
      "span": "Nothing points at a referent.",
      "round": 0,
      "evidence_id": "P1",
      "correct": false
    },
    {
      "id": "G07",
      "gap": "missing_premise",
      "gold_status": "unresolved",
      "status": "unresolved",
      "span": null,
      "alternatives": [],
      "correct": true
    },
    {
      "id": "G08",
      "gap": "missing_premise",
      "gold_status": "resolved",
      "status": "resolved",
      "span": "10 days",
      "round": 0,
      "evidence_id": "P1",
      "correct": true
    },
    {
      "id": "G09",
      "gap": "conflicting_values",
      "gold_status": "ambiguous",
      "status": "ambiguous",
      "span": null,
      "alternatives": [
        "30 days",
        "version 2 sets the notice period at 45 days.",
        "30 days",
        "version 2 sets the notice period at 45 days.",
        "30 days",
        "version 2 sets the notice period at 45 days."
      ],
      "correct": true
    },
    {
      "id": "G10",
      "gap": "conflicting_values",
      "gold_status": "ambiguous",
      "status": "ambiguous",
      "span": null,
      "alternatives": [
        "inr 50000",
        "inr 75000",
        "inr 50000",
        "inr 75000",
        "inr 50000",
        "inr 75000"
      ],
      "correct": true
    },
    {
      "id": "G11",
      "gap": "vague_criterion",
      "gold_status": "ambiguous",
      "status": "ambiguous",
      "span": null,
      "alternatives": [
        "Repairs shall be done within a reasonable time.",
        "Repairs shall be done within a reasonable time.",
        "Repairs shall be done within a reasonable time."
      ],
      "correct": true
    },
    {
      "id": "G12",
      "gap": "vague_criterion",
      "gold_status": "ambiguous",
      "status": "ambiguous",
      "span": null,
      "alternatives": [
        "The tenant shall give prompt notice of damage.",
        "The tenant shall give prompt notice of damage.",
        "The tenant shall give prompt notice of damage."
      ],
      "correct": true
    }
  ]
}
```

Elapsed seconds: 0.0261. Peak RSS MB: 113.07.
- Scale-down: Twelve items, two or three per gap type, replace the requested 10 items per gap type. Context is pasted, which is the Phase 0 setup.
- Conclusion: The loop can close a gap only when a passage states the missing piece, and it refuses a single answer when two values or a vague criterion remain.

## EXP-011 Decision and next-action heads

- Status: `closed`
- Goal: Train the small decision head and next-action head on pipeline features and measure abstention, calibration, and unsupported claims.
- Method: Scenarios with known labels are featurized by the real lexical QA and NLI judges. Logistic regression is trained offline. A validation sweep picks the highest-coverage threshold whose unsupported-claim rate is at most 5 percent. The next-action head is a second logistic regression. Rendering for the chain check is deterministic.
- Referenced files:
- `lab/exp_011_decision_heads/run.py`
- `lab/common/qa.py`
- `lab/common/nli.py`
- `lab/common/harness.py`
- `lab/common/textutil.py`
- `data/exp_011_decision_heads/items.json`
- `data/exp_011_decision_heads/results.json`
- Results: Decision head test accuracy is 1.0 on 54 items. Validation selected threshold 0.4 (target met: True). At that threshold the test unsupported-claim rate among assertions is 0.0 and supported coverage is 0.3333. Abstain precision 1.0, recall 1.0. Deterministic rendering of 30 supported claims had 0 number mismatches. Next-action head accuracy is 0.8667.
```json
{
  "train": 252,
  "validation": 54,
  "test": 54,
  "test_accuracy": 1.0,
  "abstention_threshold": 0.4,
  "threshold_met_unsupported_target_on_validation": true,
  "test_unsupported_claim_rate_when_asserted": 0.0,
  "test_supported_coverage": 0.3333,
  "abstain_precision_on_non_supported": 1.0,
  "abstain_recall_on_non_supported": 1.0,
  "reliability_supported": [
    {
      "bin": [
        0.0,
        0.2
      ],
      "n": 36,
      "mean_p": 0.0178,
      "empirical": 0.0
    },
    {
      "bin": [
        0.2,
        0.4
      ],
      "n": 0,
      "mean_p": null,
      "empirical": null
    },
    {
      "bin": [
        0.4,
        0.6
      ],
      "n": 0,
      "mean_p": null,
      "empirical": null
    },
    {
      "bin": [
        0.6,
        0.8
      ],
      "n": 0,
      "mean_p": null,
      "empirical": null
    },
    {
      "bin": [
        0.8,
        1.0
      ],
      "n": 18,
      "mean_p": 0.9471,
      "empirical": 1.0
    }
  ],
  "chain_items": 30,
  "chain_number_errors": 0,
  "next_action_accuracy": 0.8667,
  "aggregation_check": 0.6175
}
```

Elapsed seconds: 0.0411. Peak RSS MB: 119.63.
- Scale-down: Training rows are generated from six slots rather than MNLI, ANLI, FEVER, SQuAD2, and HotpotQA. No neural encoder is run to build the features.
- Conclusion: The heads learn the feature patterns in this generated set. The unsupported-claim target is evaluated at the validation threshold and reported on the held-out slice, not assumed.

## EXP-012 Verification engine

- Status: `closed`
- Goal: Exercise quote, support, agreement, conflict, calculation, coverage, contradiction queries, and the output validator.
- Method: Each check is run on a fixed passage and a planted failure. The calculator recomputes the date from the same spans. Qualifiers that were not in the source fail validation.
- Referenced files:
- `lab/exp_012_verification/run.py`
- `lab/common/verify.py`
- `lab/common/calc.py`
- `lab/common/nli.py`
- `lab/common/qa.py`
- `lab/common/textutil.py`
- `lab/common/harness.py`
- `data/exp_012_verification/results.json`
- Results: 15 of 15 verification checks behaved as specified. Quote check accepts '30 days' and rejects '60 days'. Support check on the matching claim is True and on 60 days is False. A 30-versus-45 pair is a conflict: True. Recomputing 1 January 2024 plus 30 days yields 31 January 2024 (match True). Added qualifier 'clearly' fails the output validator: True. Contradiction queries: ['notice period except', 'notice period unless', 'notice period not', 'notice period provided that', 'no notice period'].
```json
{
  "checks": {
    "quote_accepts_real_span": true,
    "quote_rejects_absent_span": true,
    "support_accepts_matching_claim": true,
    "support_rejects_different_number": true,
    "conflict_detected": true,
    "same_span_not_conflict": true,
    "second_span_overlap": true,
    "second_span_rejects_unrelated": true,
    "calculation_accepts_recompute": true,
    "calculation_rejects_wrong_date": true,
    "coverage_ratio": 0.3333,
    "coverage_complete": true,
    "contradiction_queries": [
      "notice period except",
      "notice period unless",
      "notice period not",
      "notice period provided that",
      "no notice period"
    ],
    "injection_not_a_quote": true,
    "qualifier_caught": true,
    "clean_output_passes": true,
    "qualifier_output_fails": true
  },
  "passed": 15,
  "considered": 15
}
```

Elapsed seconds: 0.0323. Peak RSS MB: 28.48.
- Scale-down: Fixture-level checks, not a full corpus replay.
- Conclusion: The checks catch altered spans, conflicting numbers, bad arithmetic, and unsupported qualifiers on these fixtures. An instruction embedded in the passage is not treated as a quote.

## EXP-013 Provenance and context faithfulness

- Status: `closed`
- Goal: Check that answers follow supplied context, that undefined invented terms stay unresolved, and that provenance tags separate evidence, inference, and background.
- Method: A fixed background table holds ordinary facts such as Paris and a 14-day sprint. Extractive QA reads only the passage. If the span is not in the passage, the answer is dropped even when the background table has a value.
- Referenced files:
- `lab/exp_013_provenance/run.py`
- `lab/common/provenance.py`
- `lab/common/qa.py`
- `lab/common/textutil.py`
- `lab/common/harness.py`
- `data/exp_013_provenance/items.json`
- `data/exp_013_provenance/results.json`
- Results: H1 context-faithfulness is 1.0 on 8 altered-fact items. Answers that matched the background prior: 0. Abstentions: 0. H2 correct with the definition present: 1.0. Unresolved (no guess) when the definition is removed: 1.0. Provenance tags kept evidence True, inference True, and dropped a background-only capital claim: True.
```json
{
  "h1_n": 8,
  "context_faithfulness": 1.0,
  "answered_with_background_fact": 0,
  "h1_abstain": 0,
  "h2_n": 6,
  "correct_with_definition": 1.0,
  "unresolved_without_definition": 1.0,
  "evidence_tag_kept": true,
  "inference_tag_kept": true,
  "background_only_dropped": true,
  "background_consultations_logged": 1
}
```

Elapsed seconds: 0.0008. Peak RSS MB: 12.12.
- Scale-down: Eight counterfactual items and six invented terms replace a larger probe set. There is no pretrained model whose memorized facts could leak; the background table is the stand-in prior.
- Conclusion: Factual answers are copied from the passage. The background table is logged and is not allowed to fill a missing fact. Invented terms are answered only while their definition is in the context.

## EXP-014 Cross-domain lookup and reasoning skills

- Status: `closed`
- Goal: Compare extractive accuracy across unrelated domains and record which reasoning skills the non-generative engine actually performs.
- Method: Six domains have four original passages each. Comparison, counting, ordering, and sums run in code on extracted values. The conditional probe is a single if/unless sentence.
- Referenced files:
- `lab/exp_014_reasoning/run.py`
- `lab/common/qa.py`
- `lab/common/calc.py`
- `lab/common/textutil.py`
- `lab/common/harness.py`
- `data/exp_014_reasoning/items.json`
- `data/exp_014_reasoning/results.json`
- Results: Per-domain accuracy on 4 items each: {'software': 0.75, 'recipes': 0.25, 'sports': 0.75, 'finance': 0.75, 'medical': 0.75, 'legal': 1.0}. The gap between the highest and lowest domain is 0.75. Skills that succeeded: ['comparison', 'counting', 'ordering', 'sum', 'conditional_if']. Skills that failed: ['conditional_unless_blocked']. The conditional helper returns the 'if' result and does not block on 'unless', so the unless probe fails on purpose.
```json
{
  "per_domain_accuracy": {
    "software": 0.75,
    "recipes": 0.25,
    "sports": 0.75,
    "finance": 0.75,
    "medical": 0.75,
    "legal": 1.0
  },
  "domain_gap": 0.75,
  "items_per_domain": 4,
  "skills": {
    "comparison": true,
    "counting": true,
    "ordering": true,
    "sum": true,
    "conditional_if": true,
    "conditional_unless_blocked": false
  },
  "skills_handled": [
    "comparison",
    "counting",
    "ordering",
    "sum",
    "conditional_if"
  ],
  "skills_failed": [
    "conditional_unless_blocked"
  ]
}
```

Elapsed seconds: 0.0355. Peak RSS MB: 28.55.
- Scale-down: Four items in each of six domains replace 20 items in five domains. Ordering uses dateparser rather than a learned temporal model.
- Conclusion: Domain differences on this set come from wording, not from pretrained domain knowledge, because no pretrained model is loaded. The engine does comparison, counting, ordering, sum, conditional_if and fails conditional_unless_blocked.

## EXP-015 Paged memory and needle recall

- Status: `closed`
- Goal: Measure needle recall as the haystack grows, page-fault restoration after eviction, and the effect of the working-set budget.
- Method: Synthetic pages are indexed with the hybrid retriever. The working set pins the ask, evicts the lowest-relevance unpinned page, and counts a page fault when a missing passage is admitted again. A notebook stores one row per sub-question.
- Referenced files:
- `lab/exp_015_paged_memory/run.py`
- `lab/common/paged.py`
- `lab/common/index.py`
- `lab/common/qa.py`
- `lab/common/textutil.py`
- `lab/common/harness.py`
- `data/exp_015_paged_memory/results.json`
- Results: Needle Recall@5 at 10, 100, and 1000 pages: [{'pages': 10, 'recall_at_5': 1.0, 'top': ['PG0005', 'PG0000', 'PG0001']}, {'pages': 100, 'recall_at_5': 1.0, 'top': ['PG0050', 'PG0000', 'PG0001']}, {'pages': 1000, 'recall_at_5': 1.0, 'top': ['PG0500', 'PG0000', 'PG0001']}]. The needle was evicted under a one-page budget: True. A later request page-faulted it back: True, restored True. Fact coverage by working-set budget: [{'budget': 1, 'coverage': {'found': 1, 'total': 3, 'ratio': 0.3333}, 'evictions': 2, 'working_ids': ['F2']}, {'budget': 3, 'coverage': {'found': 3, 'total': 3, 'ratio': 1.0}, 'evictions': 0, 'working_ids': ['F0', 'F1', 'F2']}, {'budget': 8, 'coverage': {'found': 3, 'total': 3, 'ratio': 1.0}, 'evictions': 0, 'working_ids': ['D0', 'D1', 'D2', 'D3', 'D4', 'F0', 'F1', 'F2']}]. Coverage report scanned/total matched the counter: True.
```json
{
  "needle_recall": [
    {
      "pages": 10,
      "recall_at_5": 1.0,
      "top": [
        "PG0005",
        "PG0000",
        "PG0001"
      ]
    },
    {
      "pages": 100,
      "recall_at_5": 1.0,
      "top": [
        "PG0050",
        "PG0000",
        "PG0001"
      ]
    },
    {
      "pages": 1000,
      "recall_at_5": 1.0,
      "top": [
        "PG0500",
        "PG0000",
        "PG0001"
      ]
    }
  ],
  "needle_evicted": true,
  "page_fault_fired": true,
  "needle_restored": true,
  "page_faults": 1,
  "budget_effect": [
    {
      "budget": 1,
      "coverage": {
        "found": 1,
        "total": 3,
        "ratio": 0.3333
      },
      "evictions": 2,
      "working_ids": [
        "F2"
      ]
    },
    {
      "budget": 3,
      "coverage": {
        "found": 3,
        "total": 3,
        "ratio": 1.0
      },
      "evictions": 0,
      "working_ids": [
        "F0",
        "F1",
        "F2"
      ]
    },
    {
      "budget": 8,
      "coverage": {
        "found": 3,
        "total": 3,
        "ratio": 1.0
      },
      "evictions": 0,
      "working_ids": [
        "D0",
        "D1",
        "D2",
        "D3",
        "D4",
        "F0",
        "F1",
        "F2"
      ]
    }
  ],
  "coverage_report_matches": true,
  "coverage_report": {
    "chunks_scanned": 1000,
    "chunks_total": 1000,
    "ratio": 1.0
  }
}
```

Elapsed seconds: 0.0357. Peak RSS MB: 116.49.
- Scale-down: Pages are short synthetic paragraphs, not scanned document pages. 1,000 pages were run. A multi-million-token archive was not.
- Conclusion: Recall of a distinctive needle stayed available at the sizes that fit in this process. Eviction removes an unpinned page, and the next request brings it back as a page fault. The notebook, not the raw haystack, is what the reduce step would read.

## EXP-016 Recall memory and revalidation

- Status: `closed`
- Goal: Show that only verified notes are stored, that a changed source invalidates them, and that a conflict flips the note.
- Method: SQLite stores the note schema from the architecture: statement, source pointer, version hash, and exact text. Recall reopens the archive and checks the hash and the exact text before the note can be used.
- Referenced files:
- `lab/exp_016_recall_memory/run.py`
- `lab/common/memory.py`
- `lab/common/schemas.py`
- `lab/common/harness.py`
- `data/exp_016_recall_memory/memory.sqlite`
- `data/exp_016_recall_memory/results.json`
- Results: An unverified note was rejected: True. A verified note was stored and recalled (1 valid hit). A changed version hash is caught: True. A missing source is caught: True. Edited exact text is caught: True. After a conflicting source the status is conflicted. Verified notes with an empty pointer: 0.
```json
{
  "unverified_write_rejected": true,
  "schema_errors": [
    "missing:note_id",
    "missing:kind",
    "missing:source",
    "source_missing:doc_id",
    "source_missing:version",
    "source_missing:chunk_id",
    "source_missing:exact_text",
    "bad_kind"
  ],
  "verified_write_accepted": true,
  "recall_valid_hits": 1,
  "stale_version_caught": true,
  "missing_source_caught": true,
  "edited_text_caught": true,
  "conflict_status": "conflicted",
  "wrong_verified_notes_without_text": 0,
  "notes_stored": 2
}
```

Elapsed seconds: 0.0058. Peak RSS MB: 13.49.
- Scale-down: One note and one edited chunk stand in for a full archive replay. The index is SQLite, not Qdrant.
- Conclusion: Unverified writes are refused. Version changes and missing exact text invalidate a note. A conflicting source marks the note conflicted instead of leaving it as verified truth.

## EXP-017 Rewrite fidelity without a generator

- Status: `closed`
- Goal: Measure fact, number, and modality preservation for a deterministic renderer, and show that the fidelity checks catch planted edits.
- Method: The renderer joins already verified sentences and normalizes whitespace. It does not paraphrase. Fidelity uses the architecture's number and modal comparison. Planted edits drop a number, add a number, or flip shall/not. Bidirectional NLI is the lexical judge.
- Referenced files:
- `lab/exp_017_fidelity/run.py`
- `lab/common/harness.py`
- `lab/common/verify.py`
- `lab/common/nli.py`
- `lab/common/textutil.py`
- `data/exp_017_fidelity/items.json`
- `data/exp_017_fidelity/results.json`
- Results: Deterministic rendering of 65 claim and paragraph cases preserved numbers in 1.0 and added numbers in 0.0. Modal error rate is 0.0. Bidirectional lexical NLI pass rate is 1.0. Planted bad edits were caught at 1.0: [{'kind': 'drop_number', 'caught': True, 'numbers': {'numbers_dropped': ['30'], 'numbers_added': [], 'ok': False}, 'modal_changed': False}, {'kind': 'add_number', 'caught': True, 'numbers': {'numbers_dropped': [], 'numbers_added': ['99'], 'ok': False}, 'modal_changed': False}, {'kind': 'flip_modal', 'caught': True, 'numbers': {'numbers_dropped': [], 'numbers_added': [], 'ok': True}, 'modal_changed': True}, {'kind': 'drop_not', 'caught': True, 'numbers': {'numbers_dropped': [], 'numbers_added': [], 'ok': True}, 'modal_changed': True}]. No human fluency score was collected.
```json
{
  "renders": 65,
  "fact_preservation_rate": 1.0,
  "added_content_rate": 0.0,
  "modal_error_rate": 0.0,
  "bidirectional_nli_pass_rate": 1.0,
  "fluency_human_rating": null,
  "mutation_catch": [
    {
      "kind": "drop_number",
      "caught": true,
      "numbers": {
        "numbers_dropped": [
          "30"
        ],
        "numbers_added": [],
        "ok": false
      },
      "modal_changed": false
    },
    {
      "kind": "add_number",
      "caught": true,
      "numbers": {
        "numbers_dropped": [],
        "numbers_added": [
          "99"
        ],
        "ok": false
      },
      "modal_changed": false
    },
    {
      "kind": "flip_modal",
      "caught": true,
      "numbers": {
        "numbers_dropped": [],
        "numbers_added": [],
        "ok": true
      },
      "modal_changed": true
    },
    {
      "kind": "drop_not",
      "caught": true,
      "numbers": {
        "numbers_dropped": [],
        "numbers_added": [],
        "ok": true
      },
      "modal_changed": true
    }
  ],
  "mutation_catch_rate": 1.0,
  "generator_used": false
}
```

Elapsed seconds: 0.0029. Peak RSS MB: 12.12.
- Scale-down: Eight claims and five paragraphs, each rendered in five style labels that all take the copy path. This is smaller than 50 paragraphs and 50 claim lists, and it does not call FLAN-T5.
- Conclusion: Because the renderer copies verified sentences, number and modal preservation is a property of that copy step and was measured, not assumed. The validator catches the planted edits. Fluency was not rated by a person. A generative rewriter is not part of this run.

## EXP-018 Long-form assembly

- Status: `closed`
- Goal: Assemble documents from verified findings at 200, 1,000, and 5,000 claims and check coverage, citations, repetition, glossary flags, throughput, and resume.
- Method: An outline groups findings into units of four. Each unit is rendered by code with its citation marker. TF-IDF cosine flags near-duplicate units. A checkpoint stores finished units so a truncated job can resume. No sentence is generated.
- Referenced files:
- `lab/exp_018_longform/run.py`
- `lab/common/assemble.py`
- `lab/common/verify.py`
- `lab/common/textutil.py`
- `lab/common/harness.py`
- `data/exp_018_longform/spec.json`
- `data/exp_018_longform/results.json`
- Results: Assembly sizes: 200 claims -> 1706 words, coverage 1.0, broken citations 0, repetition pairs 1, 322303.72 words/sec; 1000 claims -> 8506 words, coverage 1.0, broken citations 0, repetition pairs 1, 440183.67 words/sec; 5000 claims -> 42506 words, coverage 1.0, broken citations 0, repetition pairs 1, 119261.48 words/sec. Resume hash matches a full run: True.
```json
{
  "sizes": [
    {
      "claims": 200,
      "leaves": 50,
      "words": 1706,
      "coverage": 1.0,
      "missing": 0,
      "broken_citations": [],
      "units_without_citation": [],
      "repetition_pairs": 1,
      "glossary_flags": [
        {
          "variant": "R. Sharma",
          "canonical": "Ravi Sharma"
        }
      ],
      "elapsed_sec": 0.0053,
      "tokens_per_sec": 322303.72,
      "rss_before_mb": 111.86,
      "rss_after_mb": 112.96,
      "sha256": "bff01e6e7e463a24cc6669db9dcedca82712bf57fef8f0538128643858b496e0"
    },
    {
      "claims": 1000,
      "leaves": 250,
      "words": 8506,
      "coverage": 1.0,
      "missing": 0,
      "broken_citations": [],
      "units_without_citation": [],
      "repetition_pairs": 1,
      "glossary_flags": [
        {
          "variant": "R. Sharma",
          "canonical": "Ravi Sharma"
        }
      ],
      "elapsed_sec": 0.0193,
      "tokens_per_sec": 440183.67,
      "rss_before_mb": 113.33,
      "rss_after_mb": 114.46,
      "sha256": "d60096f22c9b1de5bb3a8df21d7de8b9467ec43551354255964f07dcc1a69106"
    },
    {
      "claims": 5000,
      "leaves": 1250,
      "words": 42506,
      "coverage": 1.0,
      "missing": 0,
      "broken_citations": [],
      "units_without_citation": [],
      "repetition_pairs": 1,
      "glossary_flags": [
        {
          "variant": "R. Sharma",
          "canonical": "Ravi Sharma"
        }
      ],
      "elapsed_sec": 0.3564,
      "tokens_per_sec": 119261.48,
      "rss_before_mb": 116.08,
      "rss_after_mb": 131.35,
      "sha256": "8f16ab373d09b89e12b98afeed44bcb46aebeebff7315c27dbb78a07ec6a4ef0"
    }
  ],
  "resume_matches_full": true,
  "resumed_from_leaves": 2,
  "generator_used": false
}
```

Elapsed seconds: 0.3986. Peak RSS MB: 131.35.
- Scale-down: Claims are templated verified findings, not 10 to 250 pages of model prose. The architecture's FLAN-T5 unit writer is not used.
- Conclusion: Coverage and citation integrity are properties of the assembler. Throughput is string assembly on this CPU, not a generative decoder. Resume reproduces the full document hash when the checkpoint is truncated and continued.

## EXP-019 Proposal grounding filter

- Status: `closed`
- Goal: Measure the grounding filter and the retrieval lift of template queries over the raw ask, without calling a generative proposer.
- Method: Candidate strings are kept only when they are well formed and their names, numbers, dates, and content terms already occur in the ask or the pasted context. Template queries come from the ask analyzer. Recall of the gold lease passage is compared with the raw ask.
- Referenced files:
- `lab/exp_019_proposal_filter/run.py`
- `lab/common/proposals.py`
- `lab/common/ask.py`
- `lab/common/index.py`
- `lab/common/textutil.py`
- `lab/common/harness.py`
- `data/exp_019_proposal_filter/proposals.json`
- `data/exp_019_proposal_filter/results.json`
- Results: The grounding filter kept 5 of 5 source-bound queries and caught 1.0 of the queries that introduced a new name, number, or date. Malformed items caught: 1.0. Duplicates collapsed to 1. Raw-ask Recall@5 is 1.0; template queries reach 1.0 (lift 0.0, harm False). No proposer model was called.
```json
{
  "good_kept": 5,
  "good_total": 5,
  "hallucination_catch_rate": 1.0,
  "malformed_catch_rate": 1.0,
  "deduped_count": 1,
  "format_valid_rate_on_good": 1.0,
  "raw_ask_recall_at_5": 1.0,
  "template_query_recall_at_5": 1.0,
  "retrieval_lift": 0.0,
  "harm_template_lowered_recall": false,
  "proposer_model_called": false,
  "raw_ask_in_template_queries": true
}
```

Elapsed seconds: 0.0068. Peak RSS MB: 112.79.
- Scale-down: Hand-written good and bad proposals stand in for FLAN-T5 samples. Input-size, hop, and sampling ladders that require a generative model are out of scope.
- Conclusion: The filter drops proposals that introduce new names, numbers, or dates. Template queries are allowed only as additional searches; the raw ask remains in the list, so a bad extra query cannot remove the baseline. Experiment P's model ladder was not run.

## EXP-020 Red team and end-to-end loop

- Status: `closed`
- Goal: Run supported, unanswerable, contradictory, negated, injected, and near-duplicate asks through the controller.
- Method: The controller analyzes the ask, retrieves with the hybrid index, judges with extractive QA and the lexical NLI check, runs a contradiction pass before a supported answer, and abstains when the schema or the evidence fails. Passage text is never executed.
- Referenced files:
- `lab/exp_020_redteam_e2e/run.py`
- `lab/common/engine.py`
- `lab/common/ask.py`
- `lab/common/budget.py`
- `lab/common/index.py`
- `lab/common/nli.py`
- `lab/common/qa.py`
- `lab/common/schemas.py`
- `lab/common/textutil.py`
- `lab/common/verify.py`
- `lab/config/budgets.json`
- `lab/common/harness.py`
- `data/exp_020_redteam_e2e/results.json`
- Results: 6 of 6 red-team cases matched the expected outcome. supported -> supported (ok): The security deposit is INR 50000. [D1-p1-c1] unanswerable -> inconclusive (ok): Insufficient evidence. Missing: a zorb. contradiction -> contradicted (ok): Ambiguous: sources conflict. Insufficient evidence. negation -> contradicted (ok): Ambiguous: sources conflict. Insufficient evidence. rewrite -> supported (ok): Rewrite the following clause: the tenant shall pay INR 10. near_duplicate -> contradicted (ok): Ambiguous: sources conflict. Insufficient evidence. Shell side effect created: False.
```json
{
  "cases": [
    {
      "id": "supported",
      "decision": "supported",
      "text": "The security deposit is INR 50000. [D1-p1-c1]",
      "path": null,
      "rounds": 2,
      "instruction_executed": false,
      "file_created": false,
      "met": true
    },
    {
      "id": "unanswerable",
      "decision": "inconclusive",
      "text": "Insufficient evidence. Missing: a zorb.",
      "path": null,
      "rounds": 2,
      "instruction_executed": false,
      "file_created": false,
      "met": true
    },
    {
      "id": "contradiction",
      "decision": "contradicted",
      "text": "Ambiguous: sources conflict. Insufficient evidence.",
      "path": null,
      "rounds": 2,
      "instruction_executed": false,
      "file_created": false,
      "met": true,
      "forbidden_span_absent": true
    },
    {
      "id": "negation",
      "decision": "contradicted",
      "text": "Ambiguous: sources conflict. Insufficient evidence.",
      "path": null,
      "rounds": 2,
      "instruction_executed": false,
      "file_created": false,
      "met": true
    },
    {
      "id": "rewrite",
      "decision": "supported",
      "text": "Rewrite the following clause: the tenant shall pay INR 10.",
      "path": "rewrite_only",
      "rounds": 0,
      "instruction_executed": null,
      "file_created": false,
      "met": true
    },
    {
      "id": "near_duplicate",
      "decision": "contradicted",
      "text": "Ambiguous: sources conflict. Insufficient evidence.",
      "path": null,
      "rounds": 2,
      "instruction_executed": false,
      "file_created": false,
      "met": true
    }
  ],
  "passed": 6,
  "n": 6,
  "shell_file_created": false
}
```

Elapsed seconds: 0.0304. Peak RSS MB: 113.01.
- Scale-down: Eight passages and six asks. This is a controller smoke test, not the full red-team catalog.
- Conclusion: The loop returns a cited answer only for the single-value deposit question. Conflicting notice periods and the injected '1 day' instruction do not become a supported answer. A pure rewrite ask does not fetch.

## EXP-021 Stage latency and memory

- Status: `closed`
- Goal: Record latency and peak RAM for ask analysis, chunking, retrieval, QA, NLI, and the controller on this machine.
- Method: Each stage is warmed up once and then timed over repeated calls. Peak RSS is the process high-water mark from getrusage.
- Referenced files:
- `lab/exp_021_latency/run.py`
- `lab/common/ask.py`
- `lab/common/chunking.py`
- `lab/common/engine.py`
- `lab/common/index.py`
- `lab/common/nli.py`
- `lab/common/qa.py`
- `lab/common/harness.py`
- `lab/common/textutil.py`
- `lab/common/verify.py`
- `lab/common/budget.py`
- `lab/common/schemas.py`
- `data/exp_021_latency/results.json`
- Results: Mean stage times in seconds: ask_analyze_sec 1.5e-05, chunk_sec 0.000327, search_sec 0.000507, qa_sec 0.000272, nli_sec 1.1e-05, e2e_sec 0.005532. Peak RSS 113.2 MB. No neural checkpoint was loaded.
```json
{
  "mean_seconds": {
    "ask_analyze_sec": 1.5e-05,
    "chunk_sec": 0.000327,
    "search_sec": 0.000507,
    "qa_sec": 0.000272,
    "nli_sec": 1.1e-05,
    "e2e_sec": 0.005532
  },
  "peak_rss_mb": 113.2,
  "cpu_note": "Measured on this process. RSS is peak resident set for the whole run, not a per-model load.",
  "models_loaded": []
}
```

Elapsed seconds: 0.0592. Peak RSS MB: 113.2.
- Scale-down: Forty short passages. Quantized ONNX and CTranslate2 runtimes from the architecture are not used.
- Conclusion: These times are for the lexical substitutes. They are not the latency of DeBERTa, GLiNER, or FLAN-T5, which are not loaded.

## Follow-up todos

## EXP-022 On-disk hybrid index

- Status: `todo`
- Goal: Repeat the hybrid retrieval measurement with an on-disk index once the corpus no longer fits the process index.
- Method: Not run.
- Referenced files:
- none yet
- Results: Not run.


- Scale-down: 
- Conclusion: Todo. Do not add a generative retriever.

## EXP-023 Human fluency rating

- Status: `todo`
- Goal: Collect a human 1-to-5 fluency rating for deterministic assemblies. Do not impute the score.
- Method: Not run.
- Referenced files:
- none yet
- Results: Not run.


- Scale-down: 
- Conclusion: Todo.

## EXP-024 Local span tagger

- Status: `todo`
- Goal: If rule-tagger hard-slice F1 is too low, train a span tagger only on locally labeled spans.
- Method: Not run.
- Referenced files:
- none yet
- Results: Not run.


- Scale-down: 
- Conclusion: Todo. Do not download a pretrained NER or generative model.

## EXP-025 Attach a document collection

- Status: `todo`
- Goal: Ingest a public, non-confidential document set with the same chunker and index. Keep the engine domain-agnostic.
- Method: Not run.
- Referenced files:
- none yet
- Results: Not run.


- Scale-down: 
- Conclusion: Todo. Phase 3 in the architecture waits on a real collection and a human reviewer. This POC does not attach one.

## EXP-026 Qualification rules

- Status: `todo`
- Goal: Add code rules for except, unless, and provided that if the lexical judge keeps missing them.
- Method: Not run.
- Referenced files:
- none yet
- Results: Not run.


- Scale-down: 
- Conclusion: Todo. This stays a deterministic checker.

