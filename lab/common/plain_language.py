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

Explicitly NOT a sentence-restructuring tool: a long subordinate-clause
sentence with every formal word swapped for a plain one is still a long,
dense sentence. This module only ever swaps vocabulary; it has no
mechanism to split a sentence, reorder a clause, or convert passive to
active voice. Tested directly against a real ~3,400-word GDPR excerpt
(2026-11-09): most sentences get at least one substitution, but several
of the document's longest, most convoluted sentences (deeply nested
conditions, multiple cross-references) read almost as densely after
substitution as before -- the hard part of "plain English" for this kind
of text is sentence structure, not vocabulary, and this module does not
solve that part. Reported as a real, measured limit, not glossed over.
"""

from __future__ import annotations

import re

# formal phrase (lowercase) -> plain equivalent. Longer phrases are tried
# before shorter ones that could be a substring of them (handled by
# sorting PLAIN_TABLE by phrase length, descending, before compiling).
PLAIN_TABLE: dict[str, str] = {
    "notwithstanding the foregoing": "despite this",
    "notwithstanding anything to the contrary": "despite anything else said here",
    "notwithstanding": "despite",
    "pursuant to": "under",
    "in accordance with": "under",
    "in the event that": "if",
    "in the event of": "if there is",
    "in so far as": "to the extent that",
    "insofar as": "to the extent that",
    "with respect to": "about",
    "with regard to": "about",
    "in respect of": "about",
    "prior to": "before",
    "subsequent to": "after",
    "for the purposes of": "for",
    "for the purpose of": "for",
    "by virtue of": "because of",
    "in the absence of": "without",
    "shall not": "must not",
    "shall": "must",
    "may not": "must not",
    "forthwith": "immediately",
    "herein": "in this document",
    "hereof": "of this document",
    "hereby": "by this",
    "hereto": "to this",
    "heretofore": "until now",
    "thereof": "of it",
    "thereto": "to it",
    "therein": "in it",
    "the aforementioned": "this",
    "aforementioned": "already mentioned",
    "the said": "this",
    "whereas": "since",
    "whereby": "by which",
    "wherein": "in which",
    "provided that": "if",
    "save that": "except that",
    "save for": "except for",
    "inter alia": "among other things",
    "mutatis mutandis": "with the necessary changes",
    "bona fide": "genuine",
    "ab initio": "from the start",
    "de minimis": "too small to matter",
    "ipso facto": "by that fact alone",
    "null and void": "invalid",
    "deemed to be": "treated as",
    "at the discretion of": "as decided by",
    "undertake to": "agree to",
    "endeavour to": "try to",
    "render": "make",
    "utilise": "use",
    "utilize": "use",
    "ascertain": "find out",
    "constitute": "count as",
    "comprise": "include",
    "facilitate": "help",
    "commence": "start",
    "terminate": "end",
    "cease": "stop",
    "remuneration": "pay",
    "indemnify": "cover the cost for",
    "sufficient": "enough",
    "promulgate": "issue",
    "stipulate": "set out",
    "expeditiously": "quickly",
}

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
