"""Gemma 3 270M via Ollama: local generation backend.

Its former rewriter-role use (joining verified findings into prose,
FORBIDDEN.md's bounded rewriter exception) was withdrawn 2026-11-11 --
see `lab.common.rewriter_backends`'s module docstring for the measured
reason. `generate()` below is kept because `lab.common.open_domain` still
uses it for a different, separate, still-live exception (FORBIDDEN.md,
2026-10-16, "genuinely empty context": answering from the checkpoint's
own pretrained knowledge only when `brain.reason` is called with no
passages at all). The now-unused rewriter-specific functions this module
used to carry (`rewrite_unit`, `rewrite_unit_constrained`,
`generate_constrained`, `_splice_missing_citations`, `model_card`) are
recoverable from git history if a generative rewriter role is ever
reinstated.

Ollama is permitted here only to run this one named checkpoint, only
fully local (the Ollama server on localhost, never a remote host). It
does not become a general local LLM runtime for this project.
"""

from __future__ import annotations

import time

import requests

MODEL_NAME = "gemma3:270m"
OLLAMA_URL = "http://localhost:11434/api/generate"


def _post_with_retry(payload: dict, timeout: int = 60, retries: int = 2, backoff_sec: float = 2.0):
    """A transient 5xx (Ollama found, EXP-077: reproducible only as the first
    call after the model had been idle/under load elsewhere -- a cold-start
    race, not a bad request, since replaying the identical payload alone
    succeeded immediately) shouldn't abort an entire batch of generations.
    Retries only on a server error, never papers over a 4xx (a real request
    problem retrying won't fix).
    """
    last_exc = None
    for attempt in range(retries + 1):
        resp = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        if resp.status_code < 500:
            return resp
        last_exc = resp
        if attempt < retries:
            time.sleep(backoff_sec * (attempt + 1))
    return last_exc


def generate(prompt: str, max_tokens: int = 160) -> str:
    # temperature=0 (greedy): Ollama samples by default -- without pinning
    # this, two runs of the identical prompt produce different outputs.
    resp = _post_with_retry(
        {"model": MODEL_NAME, "prompt": prompt, "stream": False, "options": {"num_predict": max_tokens, "temperature": 0, "seed": 0}},
    )
    resp.raise_for_status()
    return resp.json()["response"].strip()
