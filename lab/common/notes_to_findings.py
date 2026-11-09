"""Turn messy, unstructured notes into the {statement, citation} shape
lab.common.assemble already consumes -- no LLM, no embeddings.

This is the one piece assemble.py's own docstring ("Code writes the
document; nothing is generated.") never covered: assemble() can only
write from already-structured findings, it doesn't parse raw prose into
that shape itself. Built after a live test (AUDIT.md, "Open-ended
'article from messy notes + sources' experiment", 2026-11-09) showed an
LLM asked to do this whole job at once -- parse, attribute, and write --
ignored its own citation instructions, fabricated a source organization,
and (even under citation-schema-constrained decoding) produced claims
with zero literal grounding in their cited source. Splitting the job
differently closes that gap: sentence-splitting and lexical-overlap
attribution are both purely mechanical, so assemble() can do the actual
writing with zero chance of fabrication, the same way it already does
for pre-structured findings.

Two bugs found and fixed by actually running this on real messy text
rather than assuming it would work (same discipline as every other
module in this file's AUDIT.md trail):
  1. A hard-wrapped line break is not a sentence boundary -- joining
     whitespace before splitting prevents one sentence being torn into
     fragments that can each coincidentally match a DIFFERENT source.
  2. A single short-token prefix match is not reliable evidence of a real
     connection (textutil's own _token_close matched "realy," a typo for
     "really," against "real" from "real-estate" on substring prefix
     alone). Requiring at least `min_shared` distinct tokens of length
     >=5 before trusting an attribution removes this false-positive class
     without touching the shared textutil.coverage() other callers rely on.

Third bug, found testing a petition built from one narrowly-topical rule
source (2026-11-09): when every sentence in a document is naturally
about the same topic as its one source, lexical overlap alone isn't
enough -- a petitioner's prayer ("I want the rent increase stopped and
my deposit back") was wrongly attributed to the rule source purely
because it shares two generic words ("rent", "increase") with it, even
though it is not evidence of anything the rule talks about. Fixed with a
second, STRUCTURAL gate, applied only when the source itself parses as a
conditional rule (`rules.parse_conditional_rule`): the candidate note
must also parse as a fact triple whose own verb lemma structurally
matches the rule's trigger (`rules.apply_rule`), the same language-to-
logic + tree-reasoning mechanism already validated for Grounds sections
in method_teaching.py's `list_grounded_arguments`. Lexical overlap alone
is the whole story for non-rule sources (unchanged, so the already-
validated remote-work example keeps resolving exactly as before); this
check only fires in the specific case it is needed for.
"""

from __future__ import annotations

from lab.common.rules import apply_rule, extract_fact_triple, parse_conditional_rule
from lab.common.textutil import content_tokens, coverage, sentences


def _shared_tokens(a_tokens: list[str], b_tokens: list[str]) -> list[str]:
    bset = set(b_tokens)
    hits = []
    for t in a_tokens:
        if t in bset or any(
            len(t) >= 5 and len(o) >= 5 and (t.startswith(o) or o.startswith(t))
            for o in bset
        ):
            hits.append(t)
    return hits


def notes_to_findings(
    messy_text: str,
    sources: list[dict],
    tau: float = 0.2,
    min_shared: int = 2,
) -> list[dict]:
    """Split `messy_text` into sentences and attribute each one to the
    source it shares the most distinctive content words with, if any;
    otherwise tag it USER-NOTE (the user's own uncited observation).

    `sources`: list of {"id": str, "text": str}.
    A sentence is attributed to a source only if it shares at least
    `min_shared` tokens (length >=5, exact or long-prefix match) AND
    clears the `tau` coverage ratio -- a single coincidental short-token
    match is not enough, same reasoning as the bugfix above.

    Never invents a source id and never rewrites the sentence text --
    spelling/grammar errors in `messy_text` are preserved verbatim in the
    output, since nothing here generates or paraphrases.
    """
    normalized = " ".join(messy_text.split())
    rules_by_source_id = {
        src["id"]: parse_conditional_rule(src["text"])
        for src in sources
        if parse_conditional_rule(src["text"])
    }
    findings = []
    for i, sent in enumerate(sentences(normalized)):
        sent_tokens = content_tokens(sent)
        best_id, best_cov, best_shared = None, 0.0, []
        for src in sources:
            src_tokens = content_tokens(src["text"])
            hits = _shared_tokens(sent_tokens, src_tokens)
            cov = coverage(sent_tokens, src_tokens)
            if len(hits) >= min_shared and cov > best_cov:
                best_cov, best_id, best_shared = cov, src["id"], hits
        if best_id in rules_by_source_id:
            fact = extract_fact_triple(sent)
            if not fact or not apply_rule(rules_by_source_id[best_id], fact)["matched"]:
                best_id, best_cov, best_shared = None, 0.0, []
        findings.append({
            "finding_id": f"N{i + 1}",
            "statement": sent,
            "citation": best_id or "USER-NOTE",
            "match_coverage": round(best_cov, 4),
            "shared_tokens": best_shared,
        })
    return findings
