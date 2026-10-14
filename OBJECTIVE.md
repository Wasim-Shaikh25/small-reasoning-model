# Objective

Build a research proof of concept of an evidence-grounded reasoning system that answers from supplied documents, with every factual claim traceable to a quote.

The system in `ARCHITECTURE.md` analyzes a document collection and returns an answer, or an explicit abstention, that a person can check. This repository is the Phase 0 and scaled Phase 1/2 proof of that design:

- The task controller is ordinary code. It enforces budgets, schemas, and stopping rules.
- The ask analyzer proposes a task type, a fetch depth, keyphrases, template sub-questions, and query variants. The original ask is always one of the queries.
- Retrieval is hybrid (sparse plus dense), then reranked. Memory notes point back at source text and are revalidated.
- Gaps (unknown terms, ambiguous references, missing premises, conflicts, vague criteria) are closed by fetching context and reading it again, or they are left unresolved. Model weights do not change at inference time.
- The judgment engine emits spans, support scores, conflicts, a decision, and a next action. Multi-hop arithmetic goes to a calculator whose inputs are shown.
- Verification checks the quote, the support score, agreement, conflicts, calculations, and coverage.
- Final text is assembled from verified findings. A fidelity check rejects added numbers, dropped numbers, and changed modality. If that check fails, the output falls back to the verified findings.
- Every statement is tagged `evidence`, `background`, or `inference`. A factual claim with only background support is dropped. If the supplied context contradicts a background prior, the context wins.
- The domain is not baked into the pipeline. A legal collection can be attached later as data. Names and clauses in the fixtures are examples of context, not the scope of the engine.

Success for this POC is a closed exploration for each stage, with measurements taken on this machine. Where a blueprint target is missed, or a full corpus or a human rating could not be run, the exploration says so and leaves a follow-up todo.

The POC does not train or call a generative language model. The blueprint's FLAN-T5 rewriter and proposer are replaced by the deterministic fallback the blueprint already allows: verified findings, rendered by code, and filtered proposals that introduce no new names, numbers, or dates.
