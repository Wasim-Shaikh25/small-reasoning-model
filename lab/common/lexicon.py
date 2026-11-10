"""Tiny shared loader for `lab/common/lexicons/*.yaml` -- the same "a
closed vocabulary is DATA, never a Python literal" rule `concept_tools.py`
already established for a concept's recipe, applied here to the handful of
genuinely closed real-world vocabularies (business-entity suffixes,
street-type words, formal/legal phrase substitutions, decision-verb
lemmas) that used to be hardcoded dicts/sets directly inside
`entities.py`/`plain_language.py`/`decision_findings.py`. A company can
edit or extend one of these files without touching Python, and the file
is the one place the vocabulary lives (no more silently-duplicated copy
of the same suffix list inside a regex elsewhere in the same module).

This is NOT a replacement for `concept_tools.py` -- that YAML layer
teaches a new CAPABILITY (which primitives to run); this one just
externalizes a closed VOCABULARY an existing primitive already needs.
"""

from __future__ import annotations

from pathlib import Path

import yaml

LEXICONS_DIR = Path(__file__).resolve().parent / "lexicons"

_cache: dict[str, object] = {}


def load_lexicon(name: str) -> object:
    """Reads `lab/common/lexicons/<name>.yaml` once per process and caches
    it -- these are closed vocabularies that don't change at runtime the
    way a concept registry can, so re-reading on every call (like
    `concept_tools.load_concepts` deliberately does) isn't needed here.
    """
    if name not in _cache:
        path = LEXICONS_DIR / f"{name}.yaml"
        _cache[name] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return _cache[name]
