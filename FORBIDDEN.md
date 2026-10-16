# Forbidden

These are prohibited at any cost, including for a demo, a test, a fixture, or a "temporary" shortcut.

## No generative language models, with one narrow, bounded exception

Do not use an LLM or any pure generative language model of any size, **except**
a small local FLAN-T5/T5 checkpoint (project owner's call, 2026-10-14), or a
small local Gemma 3 checkpoint run via Ollama (project owner's call,
2026-10-15, to test whether a different small checkpoint handles the
rewriter role more faithfully than flan-t5-small measured in EXP-048/054/056/062),
used **only** as the rewriter in section 3.7 of the blueprint: joining and
grammar-correcting sentences that another, non-generative component has
already extracted and verified. The exception does not reopen anything else,
and does not make Ollama or any other local runtime available for any other
use.

- No pretrained or hosted LLM for any role except the bounded rewriter below.
- No GPT-style generative model.
- No API call to OpenAI, Anthropic, Google, Cohere, Mistral, Groq, Together, Hugging Face inference, or any similar endpoint. The bounded rewriter is a local checkpoint, never an API call. Ollama, when used, must run fully local (no `ollama run` against a remote host, no cloud-hosted Ollama); the one-time model pull is the only network access it makes.
- No local generative runtime beyond the bounded rewriter: llama.cpp, vLLM, CTranslate2 generation, or any GPT-2 / Llama / Mistral checkpoint are still fully forbidden. Ollama is allowed **only** to run the one named small Gemma 3 checkpoint below, **only** in the rewriter role — not as a general local LLM runtime, not for any other checkpoint.
- Do not ask another agent or chat product to generate the answer text that this system would attribute to evidence.

### The bounded rewriter exception, in full

This exception exists so verified findings can be joined into flowing prose instead of a bulleted list of cited sentences (`ARCHITECTURE.md` sections 3.7 and 3.10), while every other hard constraint in section 1 of `ARCHITECTURE.md` still holds. All of the following must be true, or the exception does not apply and the deterministic fallback (`lab/common/assemble.py`, unchanged) is used instead:

- **Small checkpoint only.** `flan-t5-small` (or a comparably small T5 checkpoint, roughly under 300M parameters), **or**, as of 2026-10-15, `gemma3:270m` run locally via Ollama (also roughly under 300M parameters, same size ceiling, same role). Not `flan-t5-base`, not `flan-t5-large`, not a larger Gemma 3 variant, not any other non-T5/non-Gemma-3-270m generative model, without a separate, explicit decision recorded here. The two checkpoints are measured side by side on the same fidelity gate and fixtures (EXP-048/054/056/062 for FLAN-T5-small; see the matching Gemma 3 exploration once it exists) -- this entry does not declare a winner, it records that both are permitted to be tried.
- **Rewriter role only, never proposer, extractor, or judge.** It receives a batch of already-verified `(statement, citation)` findings and a style instruction, and returns prose covering only those findings. It is never given raw retrieved passages to search, never asked to answer a question, decide a fact, or judge support/contradiction. Extraction stays on the lexical QA extractor (and, when reachable, a real non-generative extractive QA encoder); verification stays on the NLI judge (and, when reachable, a real NLI encoder). A generative model never grades its own output.
- **Fidelity-gated.** Every rewrite is checked before use: every number, date, name, and amount in the input must appear in the output; `not/no/shall/may/must/unless/except/only/provided` must not change; input and output must entail each other both ways; every citation marker must survive. On any failure, the rewrite is discarded and the deterministic verbatim-findings text (`lab/common/assemble.py`'s current behavior) is returned instead. This is `ARCHITECTURE.md` section 3.7's fidelity validator, not a new invention.
- **No new facts, ever.** If a rewrite introduces a name, number, date, or claim absent from its input findings, that is a fidelity failure, not a style choice, and is rejected.
- **Measured, not assumed.** Any exploration using the bounded rewriter reports exactly which checkpoint ran, the fidelity pass/fail rate, and the fallback rate, the same as every other exploration in `EXPLORATIONS.md`.
- **Reversible.** If measurement shows the fidelity failure rate is unacceptable, the exception is withdrawn and the deterministic fallback becomes the only path again.

### Offline LoRA fine-tuning of the bounded rewriter (project owner's call, 2026-10-16)

The rewriter exception above covers using a pretrained checkpoint as-is. Fine-tuned weights are a different artifact and need their own explicit permission, not an inference by analogy -- granted here, narrowly:

- **Same checkpoint, same role, nothing else widened.** Only a LoRA adapter on top of one of the two checkpoints already named above (`flan-t5-small` or `gemma3:270m`), used only in the rewriter role, under every constraint already listed (fidelity-gated, no new facts, measured, reversible). This does not permit full fine-tuning (all weights), a larger base checkpoint, or fine-tuning for any role other than the rewriter.
- **Training data must be synthetic and deterministically generated**, by code in this repo, never scraped or drawn from real documents -- so this can never become a backdoor for "No private or real personal data" or "No facts from background alone". The generator and its output are checked into `data/`, same as any other exploration's fixture.
- **Offline only, before any answering, not "at inference time."** This is the distinction the "No weight updates at inference time" rule below is actually drawing: that rule forbids the system updating its own weights *while answering a question* (the kind of online "learning" that would be unverified and ungated). A LoRA adapter trained once, offline, as its own measured exploration, with a frozen base checkpoint and a before/after fidelity comparison, is not that -- it is a deliberate, reviewed, one-time change to which checkpoint gets loaded, exactly like choosing `gemma3:270m` over `flan-t5-small` already was.
- **`gemma3:270m` on HuggingFace is gate-restricted** (manual license acceptance); this environment has no HF credentials that have accepted it, and none were obtained to work around that. `flan-t5-small` is used for this fine-tuning instead -- it is the original bounded-rewriter checkpoint, ungated, and EXP-048/054/056/062 already measured the identical multi-fact-synthesis failure on it, so it is a faithful substitute for the question being tested, not a different one. This substitution is logged here, not silent; if Gemma access is ever obtained, the same recipe should be retried there before assuming the result transfers.
- **Measured against the same fixture the failure was found on**, not a new, easier one: EXP-048/054/062/064's 4-fact-leaf case, the one every non-fine-tuning approach tried so far (retry loops, decoding constraints) failed to fix.
- **Reversible, same as the base exception.** If the fine-tuned adapter doesn't measurably improve the fidelity pass rate on held-out cases, it is not adopted and the unmodified checkpoint remains the only path.

Encoder checkpoints named in the blueprint (DeBERTa, GLiNER, BERT-NER, bge) are still not loaded in this POC. The explorations use classical substitutes, or, where reachable, real non-generative pretrained substitutes (see `lab/common/real_models.py`), and say so either way. A later experiment may train a small head or a span tagger only on labels stored in this repository. Outside the one bounded rewriter exception above, nothing here may download or call a generative model.

## No fabricated measurements

Do not invent accuracy, latency, memory, or human ratings. If a run did not happen, the exploration stays `todo`. If it was scaled down, say so.

## No weight updates at inference time

"Learning" means retrieve missing context and read it again, or store a verified example. Do not fine-tune, adapt, or edit model weights while answering. This is about *when*: weight changes during the act of answering a question are forbidden, full stop, regardless of role. It does not conflict with the one narrow offline exception above (LoRA fine-tuning of the bounded rewriter, done once before any answering, as its own measured exploration with a frozen result) -- that happens entirely outside any answering loop, the same way choosing which pretrained checkpoint to load does.

## No facts from background alone

A model's prior, a hardcoded trivia table, or a contributor's memory is not evidence. If the context disagrees with it, the context wins. If the context is silent, abstain or mark the term unresolved. Do not guess a definition from weights or from the background table.

### Narrow exception: genuinely empty context (project owner's call, 2026-10-16)

Everything above still holds the instant any context is supplied, including when retrieval ran and found nothing relevant -- that stays abstention (`ABSTAIN_TEXT`), unchanged. The one new, separate thing permitted: when `lab.common.brain.reason` is called with **no passages at all** (`passages` is empty or `None` -- not "retrieval returned nothing," a structurally different, upstream case: there was nothing to retrieve from), it may answer from the bounded checkpoint's own pretrained knowledge instead of abstaining. This is a third generative role, distinct from the rewriter exception above, and does not reuse or widen it:

- **Triggers only on a literally empty passages list**, checked before retrieval runs, not when retrieval runs and comes up short. A caller cannot reach this path by feeding an ask that merely fails to match real content.
- **The output is never attributed as evidence.** `decision` is `"ungrounded"` -- a third value, never `"supported"` -- and the returned text always carries a fixed, visible prefix stating it is not grounded in any provided evidence. Nothing downstream may treat this text as a citable finding.
- **No fidelity gate is possible here** (there is nothing to check faithfulness against), so the one thing enforced instead: the output must not contain a citation marker (`[...]`) at all -- a bracketed citation here would be fabricated, not evidence, and is rejected outright rather than shown.
- **Still never the proposer/extractor/judge roles.** It answers directly; it is not searching, deciding a contested fact, or judging support/contradiction between two things.
- **Measured and reversible**, same as the rewriter exception: the exploration that adds this reports exactly which checkpoint answered and how often the no-citation check itself had to reject an output; if that rejection rate is high, the exception is withdrawn and a plain abstain becomes the only path again, same as before this existed.

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
