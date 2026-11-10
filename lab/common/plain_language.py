"""Formal/legal-register to plain-English VOCABULARY substitution -- not a
restructuring tool, and not claimed to be one.

Same grounding and same mechanism as `lab.common.informal_register`
(informal -> formal) and `lab.common.connectives` (a small, closed,
catalogued class, not open-ended guessing): legal/formal English's stock
connective and hedging phrases ("notwithstanding", "pursuant to", "shall")
are a small, well-documented closed set -- plain-language style guides
(e.g. the US Securities and Exchange Commission's "A Plain English
Handbook", the UK government's own plain-English guidance) have been
cataloguing exactly this substitution list for decades. Hardcoded here for
the same reason: enumerating a closed class is not guessing. Replacement
is the same literal, whole-word/whole-phrase, case-preserving substitution
`informal_register.py`/`assemble.render_unit`'s glossary step already use.

`simplify_vocabulary` alone was NOT a sentence-restructuring tool: a long
subordinate-clause sentence with every formal word swapped for a plain
one is still a long, dense sentence. Tested directly against a real
~3,400-word GDPR excerpt (2026-11-09): most sentences got at least one
substitution, but several of the document's longest, most convoluted
sentences (deeply nested conditions, multiple cross-references) read
almost as densely after substitution as before -- the hard part of
"plain English" for this kind of text is sentence structure, not
vocabulary.

`simplify_document` (2026-11-10) is the fix for that gap: vocabulary
substitution, THEN `lab.common.grammar_logic.passive_to_active` and
`.split_on_connective` per sentence -- both gated by bidirectional NLI
entailment, falling back to the ungated text on any sentence where a
transform doesn't apply or doesn't pass the gate. See
`grammar_logic.py`'s own docstring for exactly which passive/split
shapes those two transforms do and don't attempt; this module does not
claim they cover every sentence, only that every sentence they DO touch
is checked, not guessed.
"""

from __future__ import annotations

import re

from lab.common.lexicon import load_lexicon

# formal phrase (lowercase) -> plain equivalent, now DATA
# (lab/common/lexicons/plain_language_phrases.yaml), not a Python
# literal, so a company can add its own formal phrases without a code
# change -- same "closed vocabulary lives in a file" rule as
# entities.py's org-suffix/place-word lexicons. Longer phrases are tried
# before shorter ones that could be a substring of them (handled by
# sorting PLAIN_TABLE by phrase length, descending, before compiling).
PLAIN_TABLE: dict[str, str] = load_lexicon("plain_language_phrases")["phrases"]

_SORTED_PHRASES = sorted(PLAIN_TABLE, key=len, reverse=True)
_WORD_RE = {phrase: re.compile(rf"\b{re.escape(phrase)}\b", re.I) for phrase in PLAIN_TABLE}


def simplify_vocabulary(text: str) -> dict:
    """Returns {"text": simplified, "changes": [{"from", "to"}, ...]}.

    Case-preserving on the first letter only, same limit
    `informal_register.normalize_informal` already documents -- good
    enough for this closed, small table, not a general capitalization
    engine. Phrases are tried longest-first so "notwithstanding the
    foregoing" matches before the bare "notwithstanding" entry can eat
    part of it.
    """
    changes = []
    result = text
    for phrase in _SORTED_PHRASES:
        plain = PLAIN_TABLE[phrase]
        pattern = _WORD_RE[phrase]

        def _replace(match: re.Match) -> str:
            original = match.group(0)
            replacement = plain
            if original[:1].isupper():
                replacement = replacement[:1].upper() + replacement[1:]
            changes.append({"from": original, "to": replacement})
            return replacement

        result = pattern.sub(_replace, result)
    return {"text": result, "changes": changes}


def simplify_document(text: str) -> dict:
    """Vocabulary substitution + per-sentence structural simplification
    (`grammar_logic.passive_to_active` then `.split_on_connective`),
    each sentence handled independently so one sentence's rejected
    transform never blocks another's. Returns `{"text", "vocabulary_
    changes", "sentence_results"}` -- `sentence_results` is one entry per
    output sentence with whatever `passive_to_active`/`split_on_
    connective` actually did, so a caller can see exactly which
    sentences were touched and which were left alone, and why.
    """
    from lab.common.grammar_logic import passive_to_active, split_on_connective
    from lab.common.textutil import sentences as split_sentences

    vocab = simplify_vocabulary(text)
    sentence_results = []
    out_sentences = []
    for sent in split_sentences(vocab["text"]):
        voice = passive_to_active(sent)
        split = split_on_connective(voice["text"])
        out_sentences.append(split["text"])
        sentence_results.append(
            {
                "original": sent,
                "final": split["text"],
                "voice_converted": voice["converted"],
                "voice_reason": voice["reason"],
                "split": split["split"],
                "split_reason": split["reason"],
            }
        )
    return {
        "text": " ".join(out_sentences),
        "vocabulary_changes": vocab["changes"],
        "sentence_results": sentence_results,
    }
