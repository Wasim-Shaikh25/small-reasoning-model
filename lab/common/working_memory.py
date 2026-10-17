"""The brain's RAM: one small, inspectable structure carried through any
task -- a short lookup, a multi-signal reasoning chain, or writing a long
document page by page -- instead of each task re-inventing its own loose
local variables for the same thing.

The one rule that makes this different from just holding everything in
memory: once a page/leaf is no longer the immediate focus, this keeps only
a *pointer* back to it (its id) plus a short extracted digest (subject-
verb-object triples via lab.common.rules.extract_fact_triple, the same
non-generative dependency-parse extraction EXP-057-059 already use for
rule application) -- never the page's full text. If a later check needs
the real content, it navigates back to the original passage by id
(lab.common.nested_index / lab.common.graph_index already do exactly this
kind of pointer-based navigation; this module does not duplicate that, it
just remembers which id to go back to). This is the same bounded-working-
set principle EXP-015's paged memory already proved for retrieval,
generalized here to the controller's own reasoning and to long-form
writing, where it has never existed before (EXP-053's gap).
"""

from __future__ import annotations

from lab.common.rules import extract_fact_triple
from lab.common.textutil import sentences


def _triples_for(text: str) -> list[dict]:
    triples = []
    for sentence in sentences(text):
        triple = extract_fact_triple(sentence)
        if triple and triple["subject"] and triple["object"]:
            triples.append(triple)
    return triples


class WorkingMemory:
    def __init__(self):
        self.trace: list[dict] = []
        self.citations: set[str] = set()
        self.facts: dict = {}
        # Long-form only: one compact entry per page/leaf already written.
        self.pages: list[dict] = []

    def check_and_remember_page(self, leaf_id: str, text: str, citation_ids: list[str]) -> list[dict]:
        """Called once per leaf as a long document is written, in order.

        Checks this leaf's claims against every *earlier* page's digest
        first -- a leaf can only be flagged against pages already written,
        never against itself -- then adds this leaf's own digest, so the
        next call sees it too. A flag is (same subject, same verb, a
        different object) against something an earlier page already
        claimed: a real candidate contradiction, not proven false (the
        same subject+verb pair can legitimately describe two different
        facts -- "Ravi worked at ABC" then later "Ravi worked at XYZ" could
        be a job change, not an error), so this surfaces it rather than
        silently rejecting or silently accepting it, the same posture
        every other verification step in this repo takes.
        """
        new_triples = _triples_for(text)
        flags = []
        for triple in new_triples:
            if not triple["subject"]:
                continue
            for prior in self.find_prior_claims(triple["subject"], triple["verb_lemma"]):
                if prior["triple"]["object"] and triple["object"] and prior["triple"]["object"].lower() != triple["object"].lower():
                    flags.append(
                        {
                            "leaf_id": leaf_id,
                            "subject": triple["subject"],
                            "verb_lemma": triple["verb_lemma"],
                            "new_object": triple["object"],
                            "conflicts_with_leaf_id": prior["leaf_id"],
                            "prior_object": prior["triple"]["object"],
                        }
                    )
        self.pages.append({"leaf_id": leaf_id, "triples": new_triples, "citation_ids": list(citation_ids)})
        self.citations.update(citation_ids)
        return flags

    def find_prior_claims(self, subject: str, verb_lemma: str) -> list[dict]:
        """Every earlier page's triple with this exact (subject, verb) --
        the set a new page's claim about the same subject+verb must agree
        with, or be flagged against (lab.common.longform's consistency
        check calls this, not a copy of this matching logic)."""
        hits = []
        for page in self.pages:
            for triple in page["triples"]:
                if triple["subject"] and triple["subject"].lower() == subject.lower() and triple["verb_lemma"] == verb_lemma:
                    hits.append({"leaf_id": page["leaf_id"], "triple": triple})
        return hits

    def to_dict(self) -> dict:
        return {
            "trace": self.trace,
            "citations": sorted(self.citations),
            "facts": self.facts,
            "pages": [{"leaf_id": p["leaf_id"], "triples": p["triples"], "citation_ids": p["citation_ids"]} for p in self.pages],
        }
