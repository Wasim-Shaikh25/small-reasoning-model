# Forbidden

These are prohibited at any cost, including for a demo, a test, a fixture, or a "temporary" shortcut.

## No generative language models

Do not use an LLM or any pure generative language model of any size.

- No pretrained or hosted LLM.
- No GPT-style generative model.
- No API call to OpenAI, Anthropic, Google, Cohere, Mistral, Groq, Together, Hugging Face inference, or any similar endpoint.
- No local generative runtime: llama.cpp, vLLM, Ollama, CTranslate2 generation, or a FLAN-T5 / T5 / GPT-2 / Llama / Mistral checkpoint.
- No "small" generative model. Size is not an exception.
- The blueprint mentions FLAN-T5 as an untrusted proposer and as a rewriter. Those calls are not allowed here. Use the deterministic fallback: template queries, copied verified findings, and the fidelity checks.
- Do not ask another agent or chat product to generate the answer text that this system would attribute to evidence.

Encoder checkpoints named in the blueprint (DeBERTa, GLiNER, BERT-NER, bge) are also not loaded in this POC. The explorations use classical substitutes and say so. A later experiment may train a small head or a span tagger only on labels stored in this repository. It still may not download or call a generative model.

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
