"""Informal-register normalization: "cos" -> "because", not a spelling fix.

`spellfix.py` found this live (2026-11-09): "cos" has no candidate within
edit distance 1 that means "because" -- it isn't a typo of "because" at
all, it's a different, informal WORD for it. No candidate-generation or
embedding-disambiguation step can ever find a fix outside its own
edit-distance search, because this isn't that kind of problem.

Same grounding this project already uses for connectives
(lab.common.connectives): English's informal contractions are a small,
closed, catalogued set -- not something to guess or generate one at a
time. Hardcoded here for the same reason PDTB's connective list is
hardcoded in connectives.py: enumerating a closed class is not the same
as guessing open-ended vocabulary. Replacement is a literal, whole-word,
case-preserving substitution -- the same mechanism `assemble.render_unit`
already uses for its own glossary substitution, not a new pattern.
"""

from __future__ import annotations

import re

# word -> formal equivalent. Deliberately small and conservative: only
# unambiguous informal contractions, not every casual word (e.g. "wanna"
# is included because it unambiguously means "want to"; a word like
# "like" is left out because it's too often NOT the filler sense).
INFORMAL_TABLE: dict[str, str] = {
    "cos": "because",
    "coz": "because",
    "cuz": "because",
    "gonna": "going to",
    "wanna": "want to",
    "gotta": "got to",
    "gimme": "give me",
    "lemme": "let me",
    "dunno": "do not know",
    "kinda": "kind of",
    "sorta": "sort of",
    "hafta": "have to",
    "oughta": "ought to",
    "y'all": "you all",
    "ain't": "is not",
}

_WORD_RE = {word: re.compile(rf"\b{re.escape(word)}\b", re.I) for word in INFORMAL_TABLE}


def normalize_informal(text: str) -> dict:
    """Returns {"text": normalized, "changes": [{"from", "to"}, ...]}.

    Case-preserving on the first letter only (so "Cos" at a sentence
    start becomes "Because", not "because") -- good enough for this
    closed, small table; not a general capitalization engine.
    """
    changes = []
    result = text
    for word, formal in INFORMAL_TABLE.items():
        pattern = _WORD_RE[word]

        def _replace(match: re.Match) -> str:
            original = match.group(0)
            replacement = formal
            if original[:1].isupper():
                replacement = replacement[:1].upper() + replacement[1:]
            changes.append({"from": original, "to": replacement})
            return replacement

        result = pattern.sub(_replace, result)
    return {"text": result, "changes": changes}
