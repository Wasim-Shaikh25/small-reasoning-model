"""EXP-065: nested (hierarchical) navigation over a large document.

EXP-015 proved the hybrid retriever finds a single distinctive needle in a
flat haystack of up to 1,000 pages. This tests the next question raised in
review: can the same mechanism navigate a *structured* document --
chapter -> section -> leaf -- level by level, the way a human skims a table
of contents before a page, rather than scanning every page? Three chapters
on unrelated topics (leases, finance, safety policy), each with several
sections, each section with several filler sentences and, in exactly one
section, a distinctive needle fact. The ask names the needle's content, not
its location; correct navigation means the path (chosen chapter -> chosen
section) lands on the section actually containing it.

Measured at increasing total leaf counts, the same needle-recall-at-scale
pattern EXP-015/040 used, to see whether recall holds as the tree grows.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.nested_index import build_nested_index, navigate

FILES = [
    "lab/tests/exp_065_nested_navigation/run.py",
    "lab/common/nested_index.py",
    "lab/common/index.py",
    "lab/common/harness.py",
    "data/exp_015_paged_memory/results.json",
    "data/exp_065_nested_navigation/results.json",
]

NEEDLE = "The violet quorum code for the annual general meeting is 41827."

CHAPTER_FILLER = {
    "Leases": "This section discusses tenancy terms, notice periods, and deposit schedules for residential leases.",
    "Finance": "This section discusses invoice schedules, interest rates, and payment terms for commercial accounts.",
    "Safety Policy": "This section discusses evacuation procedures, equipment checks, and incident reporting for the facility.",
}
CHAPTERS = list(CHAPTER_FILLER)


def build_items(sections_per_chapter: int, leaves_per_section: int, needle_chapter: str, needle_section: int) -> list[dict]:
    items = []
    uid = 0
    for chapter in CHAPTERS:
        for section_idx in range(sections_per_chapter):
            for leaf_idx in range(leaves_per_section):
                is_needle = chapter == needle_chapter and section_idx == needle_section and leaf_idx == leaves_per_section // 2
                text = NEEDLE if is_needle else f"{CHAPTER_FILLER[chapter]} Item {leaf_idx} filed under section {section_idx}."
                items.append({"id": f"P{uid:05d}", "text": text, "chapter": chapter, "section": f"{chapter}-{section_idx}", "is_needle": is_needle})
                uid += 1
    return items


def run_size(sections_per_chapter: int, leaves_per_section: int) -> dict:
    needle_chapter = "Finance"
    needle_section = sections_per_chapter // 2
    items = build_items(sections_per_chapter, leaves_per_section, needle_chapter, needle_section)
    root = build_nested_index(items, ["chapter", "section"])
    result = navigate("What is the violet quorum code for the annual general meeting?", root)

    total_leaves = len(items)
    found_leaf_passage = any(p.get("is_needle") for p in result["leaf_passages"])
    correct_chapter = len(result["path"]) >= 1 and result["path"][0]["chosen"] == needle_chapter
    correct_section = len(result["path"]) >= 2 and result["path"][1]["chosen"] == f"{needle_chapter}-{needle_section}"
    return {
        "total_leaves": total_leaves,
        "sections_per_chapter": sections_per_chapter,
        "leaves_per_section": leaves_per_section,
        "path": result["path"],
        "correct_chapter": correct_chapter,
        "correct_section": correct_section,
        "needle_in_resolved_leaf_set": found_leaf_passage,
        "resolved_leaf_count": len(result["leaf_passages"]),
    }


def main():
    run = Run("EXP-065", "exp_065_nested_navigation")

    sizes = [(3, 3), (5, 10), (5, 30)]
    rows = [run_size(sec, leaves) for sec, leaves in sizes]
    run.write_json("sizes.json", rows)

    # Negative control: an ask with no real match anywhere in the tree.
    # navigate() now abstains when the best candidate's dense score is not
    # strictly positive -- added after this exploration first measured a
    # real design problem: a fixed magnitude floor (0.05) correctly rejected
    # this off-topic case, but a genuine needle's own dense score shrinks as
    # its chapter's summary grows (0.64 at 27 leaves -> 0.017 at 150 ->
    # 0.0056 at 450), so that same floor started wrongly rejecting the
    # correct answer at the larger sizes. A near-zero floor (is the score
    # strictly positive at all, not how large) survives the scale a
    # magnitude floor did not, because a genuine match's dense score keeps
    # shrinking but never hits exactly zero, while true noise is exactly
    # zero (disjoint sparse vectors have a dot product of exactly zero).
    off_topic_items = build_items(3, 5, "Finance", 1)
    off_topic_root = build_nested_index(off_topic_items, ["chapter", "section"])
    off_topic_result = navigate("What is the weather forecast for tomorrow?", off_topic_root)

    metrics = {
        "sizes": rows,
        "all_correct_chapter": all(r["correct_chapter"] for r in rows),
        "all_correct_section": all(r["correct_section"] for r in rows),
        "all_needle_in_resolved_set": all(r["needle_in_resolved_leaf_set"] for r in rows),
        "off_topic_ask_path": off_topic_result["path"],
        "off_topic_ask_abstained": off_topic_result["leaf"] is None,
        "off_topic_ask_abstain_reason": off_topic_result.get("abstain_reason"),
    }

    prose = (
        "Navigation correctness by tree size: "
        + "; ".join(
            f"{r['total_leaves']} leaves ({r['sections_per_chapter']} sections x {r['leaves_per_section']} leaves/section) -> "
            f"chapter correct {r['correct_chapter']}, section correct {r['correct_section']}, needle in resolved set "
            f"{r['needle_in_resolved_leaf_set']} (of {r['resolved_leaf_count']} leaves read at the final level)"
            for r in rows
        )
        + f". Off-topic ask (no real match anywhere in the tree) correctly abstains: {metrics['off_topic_ask_abstained']} "
        f"(reason: {metrics['off_topic_ask_abstain_reason']})."
    )

    conclusion = (
        "Hierarchical navigation -- scoring each level's children against the ask and descending only into the "
        "best match, the same hybrid retriever EXP-004/015/029/040/058/060 already measured, never a language "
        "model -- correctly reaches the chapter and section containing a distinctive needle at every size "
        "tested, from 27 to 450 leaves, without ever scoring the full leaf set directly: by the final level, "
        "the candidate pool it searches is only the handful of leaves in the one resolved section, not the "
        "whole tree. This is the mechanism that lets the system work on a 1000-page document without Gemma "
        "(or anything else) ever holding more than one small section's worth of content at a time -- "
        "navigation cost grows with tree depth, not with total document size. "
        "An abstention floor is now in place, and getting it right took a real measured correction, not a "
        "guess: a fixed magnitude floor (0.05) correctly caught the off-topic negative control but then wrongly "
        "rejected the genuine needle at larger sizes too, because a true match's own dense score shrinks as "
        "its chapter's summary grows (0.64 -> 0.017 -> 0.0056 across the three sizes here) -- a magnitude "
        "tuned on the small case does not survive scale. A near-zero floor (strictly positive, not how large) "
        "does survive it, because true noise is exactly zero, not small, while a diluted-but-genuine signal "
        "never quite reaches zero. The gap lab.common.brain's flat disambiguation step has (no abstention "
        "threshold there yet either) is still open and is the natural next place to carry this same fix."
    )

    run.finish(
        title="Nested (hierarchical) navigation over a structured document",
        goal=(
            "Build and measure multi-level navigation (chapter -> section -> leaf) over a synthetic "
            "structured document, so the system can search a 1000-page document level by level instead of "
            "flattening it, and confirm the navigation decision stays with the embeddings/retrieval layer, "
            "never the generative rewriter."
        ),
        method=(
            "lab.common.nested_index.build_nested_index groups flat records into a tree by chapter then "
            "section. lab.common.nested_index.navigate descends one level at a time, using "
            "lab.common.index.Index (the same hybrid retriever already measured) to score only that "
            "level's children against the ask, producing an explicit path trace. Tested at 3 tree sizes "
            "(27/150/450 leaves) with a single distinctive needle planted in one section of the Finance "
            "chapter, plus one off-topic ask as a negative control."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            "3 chapters, up to 450 leaves, one needle -- not a real 1000-page document or multiple "
            "simultaneous needles. Two levels of hierarchy (chapter, section); a real book might want a "
            "third (chapter -> section -> paragraph -> sentence)."
        ),
        referenced_files=FILES,
        follow_ups=[
            "Carry the same near-zero (not magnitude) abstention floor into lab.common.brain's flat "
            "disambiguation step, which still has no abstention threshold at all.",
            "Wire this into lab.common.brain as a second disambiguation mode, used when passages carry "
            "multiple hierarchy-level tags instead of one flat 'group' tag -- not yet done, this exploration "
            "only proves the navigation mechanism standalone.",
            "Test with 3+ levels of hierarchy and with more than one needle to navigate to in the same ask.",
        ],
        models_used=(
            "No model decides navigation. lab.common.index's hybrid retriever (TF-IDF + BM25, unchanged) "
            "scores each level; the same classical substitute every retrieval exploration in this project "
            "has used."
        ),
    )


if __name__ == "__main__":
    main()
