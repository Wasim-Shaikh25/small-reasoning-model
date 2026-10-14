"""Bounded FLAN-T5 rewriter: joins already-verified findings into prose, fidelity-gated.

This is the narrow exception recorded in FORBIDDEN.md on 2026-10-14. It is the
only place in this repository that loads a generative language model, and it
is never given raw passages, a question, or a support/contradiction judgment
to make -- only a batch of findings that the lexical QA extractor and the
lexical NLI judge have already verified, plus a style instruction. Every
output is checked by `fidelity_gate` before use; a failure discards the
generated text and falls back to `assemble.render_unit`'s deterministic
output, never a partial accept.
"""

from __future__ import annotations

import re

from lab.common.assemble import render_unit
from lab.common.verify import bidirectional_nli, citation_markers, entity_number_check, modality_preserved

MODEL_NAME = "google/flan-t5-small"

_tokenizer = None
_model = None


def load():
    global _tokenizer, _model
    if _tokenizer is None or _model is None:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        _model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
        _model.eval()
    return _tokenizer, _model


def model_card() -> dict:
    return {
        "checkpoint": MODEL_NAME,
        "params_approx": "~77M",
        "role": "rewriter only (ARCHITECTURE.md section 3.7): join verified findings into prose",
        "source": f"https://huggingface.co/{MODEL_NAME}",
        "not_used_for": ["extraction", "answering", "support/contradiction judging", "proposing"],
        "forbidden_reference": "FORBIDDEN.md, 'bounded rewriter exception', recorded 2026-10-14",
    }


def _source_lines(leaf: dict, glossary: dict[str, str]) -> tuple[list[str], list[str]]:
    lines = []
    cite_ids = []
    for finding in leaf["findings"]:
        statement = finding["statement"]
        for variant, canonical in glossary.items():
            statement = re.sub(rf"\b{re.escape(variant)}\b", canonical, statement)
        cite = finding.get("citation") or finding.get("evidence_id")
        lines.append(f"{statement} [{cite}]")
        cite_ids.append(cite)
    return lines, cite_ids


def build_prompt(leaf: dict, glossary: dict[str, str]) -> tuple[str, str, list[str]]:
    lines, cite_ids = _source_lines(leaf, glossary)
    src_text = "\n".join(lines)
    prompt = (
        "Combine these verified facts into one flowing paragraph. Do not add any fact, name, "
        "number, or date not listed below. Keep every citation marker exactly as written, in "
        "square brackets.\n\n" + src_text
    )
    return prompt, src_text, cite_ids


def fidelity_gate(src_text: str, out_text: str, cite_ids: list[str]) -> dict:
    """ARCHITECTURE.md section 3.7's fidelity validator, applied to a rewrite candidate."""
    numbers = entity_number_check(src_text, out_text)
    modal_ok = modality_preserved(src_text, out_text)
    nli = bidirectional_nli(src_text, out_text)
    found_markers = set(citation_markers(out_text))
    missing_citations = sorted(set(cite_ids) - found_markers)
    broken_citations = sorted(found_markers - set(cite_ids))
    reasons = []
    if not numbers["ok"]:
        reasons.append("numbers")
    if not modal_ok:
        reasons.append("modal")
    if not nli["ok"]:
        reasons.append("nli")
    if missing_citations or broken_citations:
        reasons.append("citations")
    return {
        "ok": not reasons,
        "numbers": numbers,
        "modal_preserved": modal_ok,
        "nli": nli,
        "missing_citations": missing_citations,
        "broken_citations": broken_citations,
        "fail_reasons": reasons,
    }


def rewrite_unit(
    leaf: dict,
    glossary: dict[str, str],
    tokenizer=None,
    model=None,
    max_new_tokens: int = 160,
) -> dict:
    """Generative counterpart to `assemble.render_unit`. Same input shape, fidelity-gated.

    Returns {"text", "used_generative", "generated_text", "checks", "fallback_reason"}.
    `text` is the generated prose when it passes the gate, otherwise the unchanged
    deterministic output -- never a partial accept of a failing rewrite.
    """
    deterministic_text = render_unit(leaf, glossary)
    prompt, src_text, cite_ids = build_prompt(leaf, glossary)
    tok, mdl = (tokenizer, model) if tokenizer is not None and model is not None else load()

    import torch

    with torch.no_grad():
        inputs = tok(prompt, return_tensors="pt", truncation=True, max_length=512)
        out_ids = mdl.generate(**inputs, max_new_tokens=max_new_tokens, num_beams=4)
    generated = tok.decode(out_ids[0], skip_special_tokens=True).strip()

    checks = fidelity_gate(src_text, generated, cite_ids)
    if checks["ok"]:
        return {
            "text": generated,
            "used_generative": True,
            "generated_text": generated,
            "checks": checks,
            "fallback_reason": None,
        }
    return {
        "text": deterministic_text,
        "used_generative": False,
        "generated_text": generated,
        "checks": checks,
        "fallback_reason": checks["fail_reasons"],
    }
