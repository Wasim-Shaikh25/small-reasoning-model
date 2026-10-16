"""A third bounded-rewriter checkpoint: someone else's completed fine-tune
of gemma3:270m on legal/financial data, permitted 2026-10-16 (FORBIDDEN.md).

Added to test the project owner's question directly: is training-
distribution style match -- not more epochs or a higher LoRA rank, EXP-073's
own finding -- what was missing for multi-fact-leaf synthesis? Rather than
retrain ourselves again, this measures a checkpoint someone else already
fine-tuned at real scale (7,617 examples, including 1,560 "rewriting"
examples specifically) on exactly this content domain.

Unlike flan-t5-small (plain text-in, text-out) and gemma3:270m-via-Ollama
(a raw prompt string), this checkpoint was trained on Gemma's chat template
with the instruction folded into the first user turn (its own model card's
documented format) and expects generation to stop at `<end_of_turn>`, not
just `<eos>`. That is handled entirely inside this module -- the shared
build_prompt/fidelity_gate contract elsewhere never needs to know a
checkpoint wants chat-formatting instead of a raw string.
"""

from __future__ import annotations

MODEL_NAME = "nagbhaskar55/gemma-3-270m-bhaskar-finetune"
BASE_MODEL = "google/gemma-3-270m-it"

_tokenizer = None
_model = None


def load():
    global _tokenizer, _model
    if _tokenizer is None or _model is None:
        from transformers import AutoModelForCausalLM, AutoTokenizer

        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        _model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)
        _model.eval()
    return _tokenizer, _model


def model_card() -> dict:
    return {
        "checkpoint": MODEL_NAME,
        "base_model": BASE_MODEL,
        "params_approx": "268M",
        "role": "rewriter only (ARCHITECTURE.md section 3.7): join verified findings into prose",
        "source": f"https://huggingface.co/{MODEL_NAME}",
        "fine_tuned_by": "a third party (nagbhaskar55), not this project -- a community checkpoint, not Google's own, measured here rather than trusted from its own model card",
        "training_data_per_card": "7,617 synthetic legal/financial instruction examples (US case law, SEC filings, educational web text); 1,560 of them explicitly 'rewriting'",
        "not_used_for": ["extraction", "answering", "support/contradiction judging", "proposing"],
        "forbidden_reference": "FORBIDDEN.md, 'bounded rewriter exception', widened 2026-10-16",
    }


def _generate(tokenizer, model, prompt: str, max_new_tokens: int) -> str:
    import torch

    # The model's own card: no separate system channel -- fold the
    # instruction into the first (only) user turn, exactly as it was
    # trained, and stop generation at <end_of_turn> (the model never
    # learned to emit the base tokenizer's own <eos> as a turn boundary).
    messages = [{"role": "user", "content": prompt}]
    input_ids = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt")
    attention_mask = input_ids.new_ones(input_ids.shape)
    eos_ids = [tokenizer.eos_token_id]
    end_of_turn_id = tokenizer.convert_tokens_to_ids("<end_of_turn>")
    if end_of_turn_id is not None and end_of_turn_id not in eos_ids:
        eos_ids.append(end_of_turn_id)
    with torch.no_grad():
        out_ids = model.generate(input_ids, attention_mask=attention_mask, max_new_tokens=max_new_tokens, eos_token_id=eos_ids, do_sample=False)
    return tokenizer.decode(out_ids[0][input_ids.shape[1] :], skip_special_tokens=True).strip()


def generate(prompt: str, max_tokens: int = 160) -> str:
    tokenizer, model = load()
    return _generate(tokenizer, model, prompt, max_tokens)
