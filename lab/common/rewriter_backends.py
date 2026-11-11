"""The bounded-rewriter generative exception, withdrawn (2026-11-11).

This module used to dispatch to one of several small local checkpoints
(flan-t5-small, gemma3:270m, a legal-finetuned gemma, Qwen2.5-0.5B-Instruct)
to join verified findings into prose, each gated by `fidelity_gate` before
use. It is kept, trimmed to its deterministic remainder, because every
real/recent measurement -- not just a weak fidelity-pass rate, genuinely
zero invocations -- showed the generative call never actually fired once
the pre-checks below were added: `data/exp_081_real_document_pipeline`
(a real 2,368-word GDPR excerpt, the most realistic fixture this project
has) measured 0/18 generative calls across BOTH permitted checkpoints, and
every experiment from exp_078 onward shows the same zero. FORBIDDEN.md's
own rewriter exception has a built-in reversibility clause for exactly
this ("if measurement shows the fidelity failure rate is unacceptable, the
exception is withdrawn and the deterministic fallback becomes the only
path again") -- invoked here, see FORBIDDEN.md's own dated note.

`rewrite_unit` below keeps its name and return shape (every caller --
longform.py, assemble.py, write_article.py -- depends on that shape) but
never loads or calls a generative checkpoint: it is `template_rewriter.
splice_unit`, decorated with the same `used_generative`/`fallback_reason`
diagnostic fields every caller already expects, permanently.

The deleted generative backends (`real_rewriter.py`, `real_rewriter_legal_
gemma.py`, `real_rewriter_qwen.py`) and the training tool for them (`lora_
finetune.py`) are recoverable from git history if this decision is ever
revisited. `real_rewriter_ollama.py`'s `generate()` is NOT deleted -- it is
still used by `lab.common.open_domain`'s separate, still-live
"genuinely empty context" exception (FORBIDDEN.md, 2026-10-16), a
different generative role this withdrawal does not touch.
"""

from __future__ import annotations

from lab.common.template_rewriter import splice_unit


def rewrite_unit(
    leaf: dict,
    glossary: dict[str, str],
    ask: str | None = None,
    max_new_tokens: int = 160,
) -> dict:
    """Deterministic splice, unconditionally -- see module docstring for
    why. `ask`/`max_new_tokens` are accepted and ignored, kept only so
    every existing caller's call site (which still passes them) needs no
    change beyond dropping the now-meaningless `checkpoint`/`use_real_nli`/
    `use_repair` arguments.
    """
    return {
        "text": splice_unit(leaf, glossary),
        "used_generative": False,
        "generated_text": None,
        "checks": None,
        "fallback_reason": ["generative_rewriter_withdrawn"],
        "checkpoint": None,
    }
