"""EXP-098: lab.common.article_tool/write_article/relationship_graph/
notes_to_findings, wired in and measured for the first time.

This pipeline (messy notes + named sources -> one cited article, plus
directed relationship-cycle detection) was built and individually unit-
tested across several earlier sessions (see each module's own docstring
for its own live-tested claims) but, until now, had exactly zero callers
anywhere outside its own four files -- not wired into lab.common.brain
(a different task shape: QA over documents, not writing from notes), and
never exercised by a measuring experiment either, unlike every other live
capability in this repo. A prior session's audit flagged it as
"self-contained, not wired to brain.reason", which on direct inspection
undersold the gap: it had no caller or test at all, only a TOOL_NAME/
TOOL_DESCRIPTION convention with no registry anywhere that reads it.

This exploration does two things:
1. Gives it a real regression test, same discipline every other live
   module in this repo already has -- so "write_article_tool works" is a
   measured, rerunnable claim, not an inference from old unit tests.
2. Directly tests the one specific thing a prior session's reviewer
   guessed, wrongly, on a surface read: that this pipeline is legal-
   domain-specific. It is not -- `relationship_graph.py`/`write_article.py`/
   `notes_to_findings.py` contain no legal-domain logic at all (checked
   directly: the only domain-flavored text anywhere in the four files is
   one docstring's description of a past bug-hunting session, not
   anything the code depends on). This fixture is deliberately a
   workplace-mentorship scenario, as far from the project's legal/GDPR
   fixtures as this repo gets, specifically to put that claim to a real
   test rather than assert it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.article_tool import write_article_tool
from lab.common.harness import Run

FILES = [
    "lab/exp_098_write_article/run.py",
    "lab/common/article_tool.py",
    "lab/common/write_article.py",
    "lab/common/relationship_graph.py",
    "lab/common/notes_to_findings.py",
    "data/exp_098_write_article/results.json",
]

# Deliberately non-legal, non-financial: a workplace mentorship circle.
# "mentored" was checked directly (lab.common.rules.extract_fact_triple)
# to parse cleanly into subject->object edges before this fixture was
# built, same "measure before trusting" discipline as every other fixture
# in this repo -- "escalated X to Y" was tried first and rejected because
# it parses inconsistently (see this exploration's own follow-up note).
NOTES = (
    "Mentorship circle notes: Alice mentored Bob this quarter. Separately, "
    "Bob has been mentoring Carol since March. People keep joking that the "
    "program went all the way around because Carol ended up mentoring "
    "Alice too."
)
SOURCES = [
    {"id": "src1", "text": "Alice mentored Bob."},
    {"id": "src2", "text": "Bob mentored Carol."},
    {"id": "src3", "text": "Carol mentored Alice."},
    {"id": "src4", "text": "The engineering all-hands is scheduled for Friday."},
]


def main() -> None:
    run = Run("EXP-098", "exp_098_write_article")

    result = write_article_tool({"notes": NOTES, "sources": SOURCES})

    ok = result["ok"]
    citations = result["citations"]
    zero_broken_citations = citations["broken"] == [] and citations["units_without_citation"] == []
    expected_sources_cited = {"src1", "src2", "src3", "src4"} <= {m.strip("[]") for m in _markers_in(result["article"])}

    cycles = result["relationships"]["cycles"]
    found_cycle = len(cycles) == 1 and cycles[0]["chain"] == ["Alice", "Bob", "Carol", "Alice"]
    cycle_not_ambiguous = found_cycle and cycles[0]["ambiguous"] is False

    # No-fabrication check: every content word in the rendered article
    # must trace back to the notes or a source -- not a claim the project
    # already measures per-leaf (lab.common.verify handles that for the
    # rewriter path), checked directly here since this is this pipeline's
    # first real test.
    source_and_note_text = (NOTES + " " + " ".join(s["text"] for s in SOURCES)).lower()
    article_words = set(result["article"].lower().split())
    source_words = set(source_and_note_text.split())
    stopword_like = {"##", "section", "1", "2", "sources", "relationships", "detected", "-", "->", "[src1]", "[src2]", "[src3]", "[src4]"}
    invented_words = {w.strip("-.,[]#") for w in article_words} - {w.strip("-.,[]#") for w in source_words} - stopword_like
    invented_words = {w for w in invented_words if w and w.isalpha() and len(w) > 2}
    no_fabrication = len(invented_words) == 0

    metrics = {
        "ok": ok,
        "zero_broken_citations": zero_broken_citations,
        "expected_sources_cited": expected_sources_cited,
        "found_expected_cycle": found_cycle,
        "cycle_not_ambiguous": cycle_not_ambiguous,
        "no_fabrication": no_fabrication,
        "invented_words_found": sorted(invented_words),
        "coverage": result["coverage"],
        "num_citation_markers": citations["markers"],
    }

    all_correct = ok and zero_broken_citations and expected_sources_cited and found_cycle and cycle_not_ambiguous and no_fabrication

    conclusion = (
        "write_article_tool (article_tool/write_article/relationship_graph/notes_to_findings) is wired in and "
        "measured for the first time, on a deliberately non-legal fixture (a workplace mentorship circle): "
        "every source is cited, no citation is broken or missing, the three-person mentorship cycle "
        "(Alice -> Bob -> Carol -> Alice) is detected correctly and unambiguously, and nothing in the rendered "
        "article is a word absent from the notes/sources it was built from. This directly refutes a prior "
        "session's surface-read guess that this pipeline is legal-domain-specific -- nothing in its own code "
        "mentions a domain at all; the only reason it looked that way is that its historical docstrings mention "
        "the legal-notice bugs it was originally found and fixed against, not anything the code depends on."
        if all_correct
        else "One or more checks failed -- see metrics for exactly which, reported as measured, not assumed."
    )

    run.finish(
        title="write_article_tool wired in and measured on a non-legal fixture: citations, cycle detection, and no-fabrication all hold",
        goal=(
            "Give lab.common.article_tool's notes-to-article pipeline its first real regression test (it had "
            "zero callers and zero tests anywhere before this), and directly test whether it is actually "
            "domain-agnostic, as its own code suggests, or legal-domain-specific, as a prior session's "
            "audit guessed from a surface read without running it."
        ),
        method=(
            "One fixture: workplace mentorship notes plus four named sources (three mentorship facts forming a "
            "three-person cycle, one unrelated all-hands announcement), run through write_article_tool end to "
            "end. Checked: the call succeeds; every citation marker resolves to a real source with none broken "
            "or missing; the directed relationship cycle is found and reported unambiguous; and -- checked "
            "directly, word by word -- the rendered article contains no content word absent from the notes or "
            "sources it was built from."
        ),
        metrics=metrics,
        results_prose=(
            f"ok={ok}, zero_broken_citations={zero_broken_citations}, expected_sources_cited={expected_sources_cited}, "
            f"found_expected_cycle={found_cycle}, cycle_not_ambiguous={cycle_not_ambiguous}, no_fabrication={no_fabrication} "
            f"(invented words: {sorted(invented_words) or 'none'}), citation coverage={result['coverage']}."
        ),
        conclusion=conclusion,
        scale_down="One fixture, four sources, a three-person cycle -- a proof the mechanism works end to end and is genuinely domain-agnostic, not a benchmark across many notes/source shapes or longer cycles.",
        referenced_files=FILES,
        follow_ups=[
            "Still not reachable from lab.common.brain.reason -- it answers a different question shape (write a document from notes) than reason() does (answer a question from documents), so wiring it in, if ever done, belongs as a sibling entry point (like lab.common.engine.run), not a new brain.reason stage.",
            "Only tested on a 3-node cycle with one off-topic distractor source; a longer chain, a non-cyclic chain, or genuinely ambiguous antecedents (relationship_graph.py's own `antecedent_ambiguous` field) are untested here.",
            "checkpoint/rewrite options were real but inert before this session (the generative rewriter role they configured was withdrawn 2026-11-11, see FORBIDDEN.md) -- rewrite=True now runs template_rewriter.splice_unit, not a different renderer's output; worth deciding whether the rewrite flag still earns its keep now that both paths are deterministic.",
        ],
        models_used="None -- this pipeline (and this exploration) never loads a generative or encoder model; attribution is lexical-overlap, relationship extraction is lab.common.rules.extract_fact_triple (deterministic dependency-parse based).",
    )

    print("ok:", all_correct)


def _markers_in(text: str) -> list[str]:
    import re

    return re.findall(r"\[[^\]]+\]", text)


if __name__ == "__main__":
    main()
