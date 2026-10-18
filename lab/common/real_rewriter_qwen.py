"""Qwen2.5-0.5B-Instruct: a fourth candidate for the bounded rewriter role.

Permitted 2026-10-18 (FORBIDDEN.md), under a widened ~500M size ceiling for
this one checkpoint, to test a specific hypothesis from EXP-081: flan-t5-small
failed the fidelity gate on every leaf of a real document, mostly on
numbers/modal/nli checks -- a faithful-paraphrase failure, not a reasoning
one. The question this module exists to answer is whether a 2024-era,
more carefully instruction-tuned decoder-only model holds onto "preserve
these exact facts" constraints better than flan-t5-small's 2022-era T5
instruction tuning, independent of the two being close in parameter count.

This module supplies a different generation backend only -- it reuses
lab.common.real_rewriter's prompt builder and fidelity gate completely
unchanged, so every checkpoint in the registry is measured on the identical
contract, not a different test each time.
"""

from __future__ import annotations

MODEL_NAME = "Qwen/Qwen2.5-0.5B-Instruct"

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


def generate(prompt: str, max_tokens: int = 160) -> str:
    """Same generate(prompt, max_tokens) -> str contract every backend in
    lab.common.rewriter_backends.BACKENDS satisfies. Greedy decoding
    (do_sample=False), not Ollama's default sampling -- the same
    reproducibility reason EXP-063 pinned gemma3:270m's temperature to 0:
    without it, two runs of the identical fixture produce different
    outputs and are not a fair comparison against the other checkpoints.
    """
    import torch

    tok, mdl = load()
    messages = [{"role": "user", "content": prompt}]
    inputs = tok.apply_chat_template(messages, add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt")
    with torch.no_grad():
        out_ids = mdl.generate(**inputs, max_new_tokens=max_tokens, do_sample=False)
    generated_ids = out_ids[0][inputs["input_ids"].shape[-1] :]
    return tok.decode(generated_ids, skip_special_tokens=True).strip()


def model_card() -> dict:
    return {
        "checkpoint": MODEL_NAME,
        "params_approx": "0.49B (0.36B non-embedding, 24 layers)",
        "runtime": "transformers (AutoModelForCausalLM), local only",
        "role": "rewriter only (ARCHITECTURE.md section 3.7): join verified findings into prose",
        "source": f"https://huggingface.co/{MODEL_NAME}",
        "license": "apache-2.0, ungated",
        "not_used_for": ["extraction", "answering", "support/contradiction judging", "proposing"],
        "forbidden_reference": "FORBIDDEN.md, 'A fourth bounded-rewriter checkpoint, and a widened size ceiling', recorded 2026-10-18",
    }
