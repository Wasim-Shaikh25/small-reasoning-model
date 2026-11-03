"""The one place a new bounded-rewriter checkpoint gets registered.

lab.common.real_rewriter (flan-t5-small via transformers) and
lab.common.real_rewriter_ollama (gemma3:270m via Ollama) already shared
build_prompt and fidelity_gate -- only the generation step itself differed,
and each module grew its own copy of rewrite_unit around that one
difference. This module pulls the generation step out into one dispatcher,
so adding a third permitted checkpoint (FORBIDDEN.md's bounded rewriter
exception, which must be widened first -- this module does not itself
grant permission, it only makes a permitted checkpoint pluggable) means
writing one function with this signature and adding one line to BACKENDS,
not a new copy of rewrite_unit's orchestration.

generate(checkpoint, prompt, max_tokens) -> str is the entire contract a
backend must satisfy. Everything downstream -- build_prompt, fidelity_gate,
the deterministic fallback -- stays exactly as it was, unmodified, because
none of it was ever specific to one checkpoint in the first place.
"""

from __future__ import annotations

from collections.abc import Callable

from lab.common.assemble import render_unit
from lab.common.real_rewriter import build_prompt, fidelity_gate


def _flan_t5_small(prompt: str, max_tokens: int) -> str:
    from lab.common.real_rewriter import _generate, load

    tokenizer, model = load()
    return _generate(tokenizer, model, prompt, max_tokens)


def _gemma3_270m_ollama(prompt: str, max_tokens: int) -> str:
    from lab.common.real_rewriter_ollama import generate

    return generate(prompt, max_tokens)


def _gemma3_270m_legal_finetune(prompt: str, max_tokens: int) -> str:
    from lab.common.real_rewriter_legal_gemma import generate

    return generate(prompt, max_tokens)


def _qwen2_5_0_5b_instruct(prompt: str, max_tokens: int) -> str:
    from lab.common.real_rewriter_qwen import generate

    return generate(prompt, max_tokens)


# Keys must match FORBIDDEN.md's bounded rewriter exception exactly -- this
# registry does not decide what's permitted, it only wires up what already
# is. Adding an entry here without a matching FORBIDDEN.md/models.json
# decision line is itself a policy violation, not just a code change.
BACKENDS: dict[str, Callable[[str, int], str]] = {
    "flan-t5-small": _flan_t5_small,
    "gemma3:270m": _gemma3_270m_ollama,
    "nagbhaskar55/gemma-3-270m-bhaskar-finetune": _gemma3_270m_legal_finetune,
    "Qwen/Qwen2.5-0.5B-Instruct": _qwen2_5_0_5b_instruct,
}


def generate(checkpoint: str, prompt: str, max_tokens: int = 160) -> str:
    if checkpoint not in BACKENDS:
        raise ValueError(f"{checkpoint!r} is not a registered backend. Permitted checkpoints: {sorted(BACKENDS)}. See FORBIDDEN.md's bounded rewriter exception before adding a new one.")
    return BACKENDS[checkpoint](prompt, max_tokens)


#  checkpoint -> (module path, repair-capable rewrite_unit name, extra kwargs)
#  for the two backends that have their own repair layer. Only these two:
#  qwen/legal-gemma have no repair module of their own (confirmed by the
#  2026-11-03 reasoning-layer audit, AUDIT.md) -- use_repair is simply a
#  no-op for them, not an error, since there is genuinely nothing to
#  dispatch to.
_REPAIR_BACKENDS = {
    "flan-t5-small": ("lab.common.real_rewriter", {"max_retries": 2}),
    "gemma3:270m": ("lab.common.real_rewriter_ollama", {}),
}


def rewrite_unit(
    leaf: dict,
    glossary: dict[str, str],
    checkpoint: str = "flan-t5-small",
    ask: str | None = None,
    max_new_tokens: int = 160,
    use_real_nli: bool = False,
    use_repair: bool = False,
) -> dict:
    """Same contract every checkpoint-specific rewrite_unit already had:
    same input shape, same fidelity gate, same deterministic fallback.
    `checkpoint` selects the generation backend; nothing else changes with
    it.

    `use_real_nli` (default False, see fidelity_gate's own docstring)
    passes straight through to the fidelity_gate call(s) below -- opt-in,
    zero change to any existing measured fidelity-pass rate unless a
    caller explicitly asks for the real DeBERTa-v3 MNLI check.

    `use_repair` (default False): flagged by the 2026-11-03 reasoning-
    layer audit (AUDIT.md, Top Finding #1) -- this dispatcher used to call
    each backend's own bare `generate()` plus one `fidelity_gate` check,
    bypassing flan-t5-small's own retry-with-feedback
    (lab.common.real_rewriter.rewrite_unit's `max_retries`) and
    gemma3:270m's own citation-splice repair (lab.common.
    real_rewriter_ollama.rewrite_unit's `splice_missing_citations`,
    measured recovering 11/13 otherwise-failed rewrites in EXP-063) --
    both existed, both were measured, neither was reachable through this
    dispatcher. `use_repair=True` dispatches to the checkpoint's own
    repair-capable `rewrite_unit` instead, when one exists (flan-t5-small,
    gemma3:270m); for a checkpoint with no repair module of its own
    (qwen, legal-gemma), this flag changes nothing -- the bare path below
    still runs exactly as it always did. Default False, so every existing
    measured `used_generative`/fidelity-pass rate stays exactly as
    recorded unless a caller explicitly opts in.
    """
    if use_repair and checkpoint in _REPAIR_BACKENDS:
        module_path, extra_kwargs = _REPAIR_BACKENDS[checkpoint]
        import importlib

        backend_rewrite_unit = importlib.import_module(module_path).rewrite_unit
        result = backend_rewrite_unit(leaf, glossary, ask=ask, max_new_tokens=max_new_tokens, use_real_nli=use_real_nli, **extra_kwargs)
        result.setdefault("checkpoint", checkpoint)
        return result

    deterministic_text = render_unit(leaf, glossary)
    prompt, src_text, cite_ids = build_prompt(leaf, glossary, ask=ask)
    generated = generate(checkpoint, prompt, max_new_tokens)
    checks = fidelity_gate(src_text, generated, cite_ids, ask=ask, use_real_nli=use_real_nli)

    if checks["ok"]:
        return {
            "text": generated,
            "used_generative": True,
            "generated_text": generated,
            "checks": checks,
            "fallback_reason": None,
            "checkpoint": checkpoint,
        }
    return {
        "text": deterministic_text,
        "used_generative": False,
        "generated_text": generated,
        "checks": checks,
        "fallback_reason": checks["fail_reasons"],
        "checkpoint": checkpoint,
    }
