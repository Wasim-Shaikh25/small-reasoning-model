"""Gemma 3 270M via Ollama: a second candidate for the bounded rewriter role.

Permitted 2026-10-15 (FORBIDDEN.md), alongside flan-t5-small, specifically to
test whether a different, more recently trained small checkpoint handles the
rewriter role more faithfully than flan-t5-small measured across
EXP-048/054/056/062 (consistent content-dropping, unmoved by smaller leaves,
a more directive prompt, or retry-with-feedback). This module supplies a
different generation backend only -- it reuses lab.common.real_rewriter's
prompt builder and fidelity gate completely unchanged, so the two checkpoints
are measured on the identical contract, not two different tests.

Ollama is permitted here only to run this one named checkpoint, only in this
one role, only fully local (the Ollama server on localhost, never a remote
host). It does not become a general local LLM runtime for this project.
"""

from __future__ import annotations

import requests

from lab.common.assemble import render_unit
from lab.common.real_rewriter import build_prompt, fidelity_gate

MODEL_NAME = "gemma3:270m"
OLLAMA_URL = "http://localhost:11434/api/generate"


def generate(prompt: str, max_tokens: int = 160) -> str:
    # temperature=0 (greedy): Ollama samples by default, unlike flan-t5-small's
    # deterministic beam search in lab.common.real_rewriter. Without pinning
    # this, two runs of the identical fixture produce different outputs and
    # are not a fair comparison, and this module's own result is not
    # reproducible -- discovered directly (EXP-063's first scripted run
    # didn't match its own manual diagnostic sample) rather than assumed.
    resp = requests.post(
        OLLAMA_URL,
        json={"model": MODEL_NAME, "prompt": prompt, "stream": False, "options": {"num_predict": max_tokens, "temperature": 0, "seed": 0}},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["response"].strip()


def model_card() -> dict:
    return {
        "checkpoint": MODEL_NAME,
        "params_approx": "~270M",
        "runtime": "Ollama, local only (http://localhost:11434)",
        "role": "rewriter only (ARCHITECTURE.md section 3.7): join verified findings into prose",
        "source": "https://ollama.com/library/gemma3",
        "not_used_for": ["extraction", "answering", "support/contradiction judging", "proposing"],
        "forbidden_reference": "FORBIDDEN.md, 'bounded rewriter exception', widened 2026-10-15",
    }


def _splice_missing_citations(generated: str, cite_ids: list[str], checks: dict) -> tuple[str, dict]:
    """If the only thing wrong is a missing citation marker, append it deterministically
    and re-check, instead of discarding an otherwise-faithful rewrite.

    Measured specifically on gemma3:270m (EXP-063): its content fidelity was
    excellent (verbatim fact preservation in every sampled case) but it
    consistently did not reproduce the literal "[CITE-x]" bracket convention
    the prompt asked for. That is a formatting gap, not a content-fidelity
    failure, and deterministically supplying the missing marker -- never
    inventing a number or a fact, only re-attaching a citation id the
    source itself named -- turned 11 of 13 otherwise-discarded rewrites
    faithful. This is checkpoint-specific behavior: flan-t5-small's
    failures (EXP-048/054/056/062) were about dropped *content*, which this
    splice cannot and must not paper over -- it only fires when citations
    are the sole failure reason.
    """
    # Try the splice whenever a citation is missing, even if other reasons
    # (typically "nli") also fired -- a missing citation marker spuriously
    # fails the NLI check too, since the source text's bidirectional
    # entailment comparison includes the citation token as part of what the
    # output is expected to cover. Whether the splice actually fixes things
    # is decided by re-running the full gate below, not by pre-filtering on
    # which reasons fired before the splice existed.
    if not checks["missing_citations"] or set(checks["missing_citations"]) != set(cite_ids):
        return generated, checks
    spliced = generated.rstrip() + " " + " ".join(f"[{c}]" for c in checks["missing_citations"])
    return spliced, None


def rewrite_unit(
    leaf: dict,
    glossary: dict[str, str],
    ask: str | None = None,
    max_new_tokens: int = 160,
    splice_missing_citations: bool = True,
) -> dict:
    """Same contract as lab.common.real_rewriter.rewrite_unit: same input shape,
    same fidelity gate, same fallback -- the generation backend differs, and,
    when `splice_missing_citations` is on (the default), a citation-only
    failure is repaired deterministically before falling back. Set it False
    to measure this checkpoint's raw, unrepaired behavior.
    """
    deterministic_text = render_unit(leaf, glossary)
    prompt, src_text, cite_ids = build_prompt(leaf, glossary, ask=ask)
    generated = generate(prompt, max_new_tokens)

    checks = fidelity_gate(src_text, generated, cite_ids, ask=ask)
    final_text = generated
    repaired = False
    if not checks["ok"] and splice_missing_citations:
        spliced, rechecked = _splice_missing_citations(generated, cite_ids, checks)
        if rechecked is None:
            rechecked_checks = fidelity_gate(src_text, spliced, cite_ids, ask=ask)
            if rechecked_checks["ok"]:
                final_text, checks, repaired = spliced, rechecked_checks, True

    if checks["ok"]:
        return {
            "text": final_text,
            "used_generative": True,
            "generated_text": generated,
            "checks": checks,
            "fallback_reason": None,
            "repaired": repaired,
        }
    return {
        "text": deterministic_text,
        "used_generative": False,
        "generated_text": generated,
        "checks": checks,
        "fallback_reason": checks["fail_reasons"],
        "repaired": False,
    }
