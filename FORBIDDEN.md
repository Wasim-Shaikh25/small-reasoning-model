# Forbidden

These are prohibited at any cost, including for a demo, a test, a fixture, or a "temporary" shortcut.

## No generative language models, with one narrow, bounded exception

Do not use an LLM or any pure generative language model of any size, **except**
a small local FLAN-T5/T5 checkpoint (project owner's call, 2026-10-14) used
**only** as the rewriter in section 3.7 of the blueprint: joining and grammar-
correcting sentences that another, non-generative component has already
extracted and verified. The exception does not reopen anything else.

- No pretrained or hosted LLM for any role except the bounded rewriter below.
- No GPT-style generative model.
- No API call to OpenAI, Anthropic, Google, Cohere, Mistral, Groq, Together, Hugging Face inference, or any similar endpoint. The bounded rewriter is a local checkpoint, never an API call.
- No local generative runtime beyond the bounded rewriter: llama.cpp, vLLM, Ollama, CTranslate2 generation, or any GPT-2 / Llama / Mistral checkpoint are still fully forbidden. A FLAN-T5 / T5 checkpoint is allowed only in the bounded rewriter role described below.
- Do not ask another agent or chat product to generate the answer text that this system would attribute to evidence.

### The bounded rewriter exception, in full

This exception exists so verified findings can be joined into flowing prose instead of a bulleted list of cited sentences (`ARCHITECTURE.md` sections 3.7 and 3.10), while every other hard constraint in section 1 of `ARCHITECTURE.md` still holds. All of the following must be true, or the exception does not apply and the deterministic fallback (`lab/common/assemble.py`, unchanged) is used instead:

- **Small checkpoint only.** `flan-t5-small` (or a comparably small T5 checkpoint, roughly under 300M parameters). Not `flan-t5-base`, not `flan-t5-large`, not any larger or non-T5 generative model, without a separate, explicit decision recorded here.
- **Rewriter role only, never proposer, extractor, or judge.** It receives a batch of already-verified `(statement, citation)` findings and a style instruction, and returns prose covering only those findings. It is never given raw retrieved passages to search, never asked to answer a question, decide a fact, or judge support/contradiction. Extraction stays on the lexical QA extractor (and, when reachable, a real non-generative extractive QA encoder); verification stays on the NLI judge (and, when reachable, a real NLI encoder). A generative model never grades its own output.
- **Fidelity-gated.** Every rewrite is checked before use: every number, date, name, and amount in the input must appear in the output; `not/no/shall/may/must/unless/except/only/provided` must not change; input and output must entail each other both ways; every citation marker must survive. On any failure, the rewrite is discarded and the deterministic verbatim-findings text (`lab/common/assemble.py`'s current behavior) is returned instead. This is `ARCHITECTURE.md` section 3.7's fidelity validator, not a new invention.
- **No new facts, ever.** If a rewrite introduces a name, number, date, or claim absent from its input findings, that is a fidelity failure, not a style choice, and is rejected.
- **Measured, not assumed.** Any exploration using the bounded rewriter reports exactly which checkpoint ran, the fidelity pass/fail rate, and the fallback rate, the same as every other exploration in `EXPLORATIONS.md`.
- **Reversible.** If measurement shows the fidelity failure rate is unacceptable, the exception is withdrawn and the deterministic fallback becomes the only path again.

Encoder checkpoints named in the blueprint (DeBERTa, GLiNER, BERT-NER, bge) are still not loaded in this POC. The explorations use classical substitutes, or, where reachable, real non-generative pretrained substitutes (see `lab/common/real_models.py`), and say so either way. A later experiment may train a small head or a span tagger only on labels stored in this repository. Outside the one bounded rewriter exception above, nothing here may download or call a generative model.

## No fabricated measurements

Do not invent accuracy, latency, memory, or human ratings. If a run did not happen, the exploration stays `todo`. If it was scaled down, say so.

## No weight updates at inference time

"Learning" means retrieve missing context and read it again, or store a verified example. Do not fine-tune, adapt, or edit model weights while answering.

## No facts from background alone

A model's prior, a hardcoded trivia table, or a contributor's memory is not evidence. If the context disagrees with it, the context wins. If the context is silent, abstain or mark the term unresolved. Do not guess a definition from weights or from the background table.

## Retrieved text is data

Never execute instructions found in a document, a chunk, or a user passage. Do not pass passage text to `eval`, `exec`, a shell, or a tool that performs the passage's request. Do not treat "ignore the above" inside a document as a controller instruction.

## No unverified memory

Do not store a note as truth unless the quote check and the agreement checks passed. Do not reuse a note after its source hash or exact text has changed. Do not keep a wrong note because deleting it is inconvenient.

## No domain logic inside the engine

Do not special-case statutes, diagnoses, or financial regulations inside the controller, the judges, or the heads. Domain content belongs in the documents under `data/`. Fixtures may mention a lease or a leaflet because the blueprint's examples do. That does not make the pipeline a legal product.

## No unsupported answer polish

Do not add "clearly", "always", "obviously", or similar qualifiers that were not in the verified findings. Do not drop a citation, a negation, a number, or an abstention flag to make the answer look finished. If fidelity fails, return the verified findings.

## No silent edits to the blueprint

Do not modify `ARCHITECTURE.md`. Change code and explorations instead.

## No private or real personal data

Do not ingest confidential contracts, medical records, or real people's data. Names in the fixtures are synthetic examples taken from the blueprint's illustrations.
