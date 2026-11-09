"""Content-only template rewriter: splices verified statements into flowing prose
using a small fixed connective vocabulary, never generating a token outside that
vocabulary and the statements themselves.

The middle path between `assemble.render_unit`'s bare "statement [citation]" join
and the bounded FLAN-T5 rewriter (`lab/common/real_rewriter.py`). EXP-054 measured
that even a single-fact generative rewrite can drop the given content outright
(producing only the citation marker); this rewriter structurally cannot do that --
it has no generation step, so there is nothing for it to omit or invent. It can
only choose which of a handful of fixed connector words to place between two
statements it copies verbatim, per AGENT.md's "rewrite from the given content
itself" rule.

BUG found and fixed (AUDIT.md, 2026-11-09) by running this on a real 69-finding
GDPR document, not a handful of hand-picked examples: `choose_connective` used to
infer "contrast" from `textutil.modals()`/`polarity_flipped()` -- raw regex
presence of "not"/"no"/"shall"/"unless" anywhere in the sentence. On real legal
text that is nearly every sentence (legal prose is saturated with negation and
modal "shall"), not evidence of contrast with the PREVIOUS sentence specifically.
Measured consequence: 21 of 51 connectives chosen on the real GDPR fixture were
"However," -- almost none of them an actual contrast, just a list of parallel,
sequential obligations and definitions. Fixed by reusing `lab.common.connectives.
find_connectives` (this project's own already-validated, dependency-parse-based
discourse-connective detector -- grounded, not regex, per [[feedback_no_hardcoded_
connectives]]) instead: "contrast" now fires only when the CURRENT statement's own
text structurally contains a genuine Comparison.Concession-class marker (however,
although, though, despite, while, whereas, nevertheless) -- textual evidence of an
actual contrast, not an inference from negation's mere presence.
"""

from __future__ import annotations

import re

from lab.common.connectives import Operator, find_connectives

CONNECTIVES = {
    "first": "",
    "same_subject": "Also,",
    "contrast": "However,",
    "sequence": "In addition,",
}


def _leading_subject(statement: str) -> str:
    """Crude leading-noun-phrase heuristic: a run of capitalized tokens, or the first word."""
    match = re.match(r"^((?:[A-Z][a-z'.]*\s*){1,3})", statement.strip())
    phrase = match.group(1).strip() if match else ""
    return phrase or (statement.split()[0] if statement.split() else "")


def choose_connective(prev_statement: str | None, curr_statement: str) -> str:
    """One bounded judgment: which of 4 fixed connectors (or none) fits between two
    already-verified statements, decided from simple, inspectable signals -- shared
    subject, a genuine contrast marker already in the text, or plain sequence. Never
    a 5th word, never altered statement text.
    """
    if prev_statement is None:
        return CONNECTIVES["first"]
    if any(m.operator == Operator.CONCESSION for m in find_connectives(curr_statement)):
        return CONNECTIVES["contrast"]
    prev_subject = _leading_subject(prev_statement)
    if prev_subject and prev_subject == _leading_subject(curr_statement):
        return CONNECTIVES["same_subject"]
    return CONNECTIVES["sequence"]


def splice_unit(leaf: dict, glossary: dict[str, str]) -> str:
    """Drop-in alternative to `assemble.render_unit` and `real_rewriter.rewrite_unit`.

    Same input shape and contract: a leaf's findings and a glossary, returning
    one rendered unit. Every statement is copied verbatim (after the same
    glossary substitution render_unit does) and keeps its own citation marker;
    only a connector word chosen from the fixed vocabulary above is inserted
    between statements. There is no fidelity gate here because there is
    nothing for this function to get wrong in the way a generative rewrite
    can -- it cannot drop a fact, invent one, or lose a citation, since it
    never produces a token that isn't either a verbatim statement, its
    citation marker, or one of the four connectives above.
    """
    lines = [leaf["title"]]
    prev_statement = None
    for finding in leaf["findings"]:
        statement = finding["statement"]
        for variant, canonical in glossary.items():
            statement = re.sub(rf"\b{re.escape(variant)}\b", canonical, statement)
        cite = finding.get("citation") or finding.get("evidence_id")
        connective = choose_connective(prev_statement, statement)
        piece = f"{connective} {statement}" if connective else statement
        lines.append(f"{piece} [{cite}]")
        prev_statement = statement
    return "\n".join(lines)
