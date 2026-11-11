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

Follow-up (2026-11-10): EXP-081's own follow_ups already named the real
gap here -- "the cross-page consistency checker's false-positive rate on
repetitive legal text (same generic subject, many unrelated clauses) was
not measured... a dedicated precision measurement is a real follow-up
before trusting this flag on this kind of document." Measured directly
on that exact fixture (GDPR, 16 flags after the parser upgrade): 15 of 16
are a generic actor ("the controller"/"the data subject") stating a
DIFFERENT, non-conflicting obligation under a different article, sharing
only a subject+verb lemma -- real bidirectional NLI between the two
underlying sentences (`real_encoders.real_nli`) scores every one of them
under 0.02 contradiction, while the one flag that is plausibly a genuine
tension scores 0.664. `check_and_remember_page`'s `use_real_nli` (default
False, same opt-in discipline as everywhere else in this project) adds
exactly this check -- a flag is only kept if the two sentences' own NLI
contradiction score clears `NLI_CONTRADICTION_TAU` in either direction.

This is a precision knob, not a replacement: default False keeps this
check's original, deliberately recall-oriented design (surface every
same-subject-same-verb-different-object pair as a CANDIDATE, exactly as
this module's own docstring below already says -- "not proven false...
surfaces it rather than silently rejecting or silently accepting it").
A caller writing a document where that recall-first posture is wrong
for the source material (dense regulatory/legal text with one recurring
generic subject) opts in; nothing about the original behavior changes
for a caller that doesn't.

Follow-up (2026-11-11): `self.pages` itself -- one digest per leaf,
never full text -- still grows without limit for as long as a document
is being written, held entirely in RAM. `ram_budget`/`overflow_path`
(both default None, zero behavior change when omitted) bound that: once
more than `ram_budget` pages are held, the OLDEST is archived to
`lab.common.page_archive` (a disk-backed, indexed-by-exact-subject+verb
store, not a copy held nowhere) and dropped from RAM. The same mechanism
a person writing a long document actually uses -- a short, recent
working set actively in mind, everything older filed away and consulted
again only on a specific question, never re-read start to finish.
`find_prior_claims` and `dependency_tree` both transparently see the
archive too, so a contradiction against a page written thousands of
leaves ago is still caught, not silently lost once it ages out of RAM.
"""

from __future__ import annotations

from lab.common.rules import extract_fact_triple
from lab.common.textutil import sentences

NLI_CONTRADICTION_TAU = 0.5  # same order of magnitude as grammar_logic.NLI_TAU's own entailment threshold; provisional, not calibrated against a labeled set


def _looks_contradictory(sentence_a: str, sentence_b: str, tau: float = NLI_CONTRADICTION_TAU) -> bool:
    """Real DeBERTa-v3 MNLI contradiction probability, checked in both
    directions (a sentence pair's contradiction signal is not guaranteed
    symmetric) -- kept if EITHER direction clears `tau`, same "don't miss
    a real conflict just because one direction scored low" posture
    `grammar_logic.preserves_meaning` takes for its own bidirectional
    check (there requiring BOTH directions to pass; here requiring only
    ONE to flag, because the cost of a false negative here is a missed
    contradiction, not a corrupted rewrite).
    """
    from lab.common.real_encoders import real_nli

    forward = real_nli(sentence_a, sentence_b)
    backward = real_nli(sentence_b, sentence_a)
    return max(forward["contradict"], backward["contradict"]) >= tau


def _triples_for(text: str) -> list[dict]:
    triples = []
    for sentence in sentences(text):
        triple = extract_fact_triple(sentence)
        if triple and triple["subject"] and triple["object"]:
            triples.append(triple)
    return triples


class WorkingMemory:
    def __init__(self, ram_budget: int | None = None, overflow_path: str | None = None):
        self.trace: list[dict] = []
        self.citations: set[str] = set()
        self.facts: dict = {}
        # Long-form only: one compact entry per page/leaf still in the
        # active (RAM) working set -- bounded by ram_budget when given,
        # unbounded (today's existing behavior) when it is None.
        self.pages: list[dict] = []
        self.ram_budget = ram_budget
        self.overflow_path = overflow_path
        self._archive_conn = None
        if overflow_path is not None:
            from lab.common.page_archive import connect as _archive_connect

            self._archive_conn = _archive_connect(overflow_path)

    def _evict_oldest_if_over_budget(self) -> None:
        if self.ram_budget is None or len(self.pages) <= self.ram_budget:
            return
        oldest = self.pages.pop(0)
        if self._archive_conn is not None:
            from lab.common.page_archive import archive_page

            archive_page(self._archive_conn, oldest["leaf_id"], oldest["triples"], oldest["citation_ids"])

    def check_and_remember_page(self, leaf_id: str, text: str, citation_ids: list[str], use_real_nli: bool = False) -> list[dict]:
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

        `use_real_nli=True` (see module docstring, "Follow-up 2026-11-10")
        additionally requires the two underlying sentences (each triple's
        own `raw` field -- already carried, not new storage) to clear
        `NLI_CONTRADICTION_TAU` contradiction probability in at least one
        direction before a candidate is kept; a pair that only coincides
        on subject+verb lemma, with no real contradiction signal between
        the actual sentences, is dropped instead of flagged.
        """
        new_triples = _triples_for(text)
        flags = []
        for triple in new_triples:
            if not triple["subject"]:
                continue
            for prior in self.find_prior_claims(triple["subject"], triple["verb_lemma"]):
                if prior["triple"]["object"] and triple["object"] and prior["triple"]["object"].lower() != triple["object"].lower():
                    if use_real_nli and not _looks_contradictory(prior["triple"]["raw"], triple["raw"]):
                        continue
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
        self._evict_oldest_if_over_budget()
        return flags

    def find_prior_claims(self, subject: str, verb_lemma: str) -> list[dict]:
        """Every earlier page's triple with this exact (subject, verb) --
        the set a new page's claim about the same subject+verb must agree
        with, or be flagged against (lab.common.longform's consistency
        check calls this, not a copy of this matching logic). Checks the
        active (RAM) pages first, then -- if any page has aged out to disk
        -- lab.common.page_archive's own exact-key index, so a page's
        archival never silently drops it out of this check."""
        hits = []
        for page in self.pages:
            for triple in page["triples"]:
                if triple["subject"] and triple["subject"].lower() == subject.lower() and triple["verb_lemma"] == verb_lemma:
                    hits.append({"leaf_id": page["leaf_id"], "triple": triple})
        if self._archive_conn is not None:
            from lab.common.page_archive import find_claims

            hits.extend(find_claims(self._archive_conn, subject, verb_lemma))
        return hits

    def dependency_tree(self) -> list[dict]:
        """Same node shape lab.common.brain.reason's own dependency_tree
        uses (`{"id","kind","summary","depends_on"}`): one
        "document_leaf" node per page already written, depending on its
        own citation_ids -- the source findings it was drafted from.
        lab.common.longform.write_long_document appends one
        "contradiction_flag" node per cross-page conflict on top of
        this (it already holds `consistency_flags` locally; this method
        does not duplicate that list), so the finished tree also shows
        which leaf's claim conflicts with which earlier leaf's -- the
        one place this module already connects one page's truth to
        another's, surfaced explicitly instead of only being inferable
        from reading `consistency_flags` by hand.

        Includes archived (disk-overflowed) pages too, read back from
        lab.common.page_archive rather than only the pages still in RAM
        -- a page that aged out of the working set is still a page this
        document wrote, and still belongs in its provenance tree.
        """
        all_page_dicts = list(self.pages)
        if self._archive_conn is not None:
            from lab.common.page_archive import all_pages

            all_page_dicts = all_pages(self._archive_conn) + all_page_dicts
        return [{"id": f"leaf:{p['leaf_id']}", "kind": "document_leaf", "summary": f"leaf {p['leaf_id']} ({len(p['triples'])} extracted claims)", "depends_on": list(p["citation_ids"])} for p in all_page_dicts]

    def to_dict(self) -> dict:
        return {
            "trace": self.trace,
            "citations": sorted(self.citations),
            "facts": self.facts,
            "pages": [{"leaf_id": p["leaf_id"], "triples": p["triples"], "citation_ids": p["citation_ids"]} for p in self.pages],
            "ram_budget": self.ram_budget,
            "archived_page_count": self._archived_page_count(),
        }

    def _archived_page_count(self) -> int:
        if self._archive_conn is None:
            return 0
        from lab.common.page_archive import all_pages

        return len(all_pages(self._archive_conn))
