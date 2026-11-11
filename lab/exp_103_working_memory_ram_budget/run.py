"""EXP-103: lab.common.page_archive, wired into lab.common.working_memory
as a hard RAM cap on the controller's own cross-page "working memory"
while a long document is being written.

lab.common.working_memory already compresses every page down to a digest
(subject-verb-object triples, never full text) before keeping it, but
that digest list (`WorkingMemory.pages`) still grew by one entry per leaf
for as long as a document was being written, held entirely in RAM, with
no cap at all -- fine for the handful of leaves any existing fixture
writes, a real problem for a document long enough that "how many pages
so far" stops being small (the project owner's own concern: "brain ram
need some more compressing logic when things will get more longer it
might explode").

The fix mirrors how a person actually writes something long: a short,
recent working set stays actively in mind; everything older is filed
away as reference material and consulted again only on a specific
question ("did I already say something about this subject doing this
verb?"), never re-held or re-read start to finish. `ram_budget` (default
None, zero regression) caps how many pages `WorkingMemory` keeps in RAM;
once over budget, the oldest page is archived via `lab.common.
page_archive` to a SQLite file indexed on exact (subject, verb_lemma) --
a flat index, not a tree, because this is an exact-key lookup, the same
access pattern lab.common.memory's own notes table already uses, not the
semantic "what is this branch about" question lab.common.nested_index's
hierarchical navigation exists for (that module is for searching INPUT
documents by aboutness; this one is the controller's own exact-recall
question about what IT has already written, a different access pattern
that a tree would not serve any better than an indexed flat table does).

This exploration proves the part a shallow RAM cap would have gotten
wrong: a contradiction between a brand-new page and a page that aged out
of RAM many evictions ago is STILL caught, read back from disk, not
silently lost once a page leaves the active window -- and that every
page ever written, archived or not, still shows up in the document's own
provenance tree (dependency_tree).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run
from lab.common.working_memory import WorkingMemory

FILES = [
    "lab/exp_103_working_memory_ram_budget/run.py",
    "lab/common/working_memory.py",
    "lab/common/page_archive.py",
    "lab/common/longform.py",
    "lab/common/brain.py",
    "data/exp_103_working_memory_ram_budget/results.json",
]

ASK = "Write a document summarizing who signed the agreement and when."

PASSAGES = [
    {"id": "P0", "text": "Ravi Sharma signed the agreement on 1 January."},
    {"id": "P1", "text": "Meera Iyer signed the agreement on 2 January."},
    {"id": "P2", "text": "Kapil Nair signed the agreement on 3 January."},
    {"id": "P3", "text": "Anita Rao signed the agreement on 4 January."},
    {"id": "P4", "text": "Sunil Gupta signed the agreement on 5 January."},
]


def _unit_test(db_path: str) -> dict:
    """Direct WorkingMemory check: 5 pages, ram_budget=2, the 5th page's
    claim conflicts with the 1st -- long since evicted to disk by then."""
    mem = WorkingMemory(ram_budget=2, overflow_path=db_path)
    pages = [
        ("L0", "Ravi worked at ABC."),
        ("L1", "Meera worked at XYZ."),
        ("L2", "Kapil worked at DEF."),
        ("L3", "Anita worked at GHI."),
        ("L4", "Ravi worked at PQR."),
    ]
    flags = []
    for leaf_id, text in pages:
        flags.extend(mem.check_and_remember_page(leaf_id, text, citation_ids=[leaf_id]))
    tree = mem.dependency_tree()
    archived_conflict = any(f["conflicts_with_leaf_id"] == "L0" for f in flags)
    return {
        "final_ram_pages": [p["leaf_id"] for p in mem.pages],
        "ram_budget_respected": len(mem.pages) <= 2,
        "archived_page_count": mem.to_dict()["archived_page_count"],
        "flags": flags,
        "archived_page_contradiction_caught": archived_conflict,
        "dependency_tree_leaf_count": len(tree),
        "dependency_tree_covers_all_pages": len(tree) == len(pages),
    }


def main() -> None:
    run = Run("EXP-103", "exp_103_working_memory_ram_budget")
    db_path = str(run.out_dir / "page_archive.db")
    Path(db_path).unlink(missing_ok=True)

    unit = _unit_test(db_path)

    db_path_e2e = str(run.out_dir / "page_archive_e2e.db")
    Path(db_path_e2e).unlink(missing_ok=True)
    budgeted = reason(ASK, PASSAGES, working_memory_ram_budget=2, working_memory_overflow_path=db_path_e2e)
    baseline = reason(ASK, PASSAGES)

    budgeted_step = next(t for t in budgeted["trace"] if t["step"] == "longform_write")
    baseline_step = next(t for t in baseline["trace"] if t["step"] == "longform_write")
    budgeted_wm = budgeted_step["working_memory"]
    baseline_wm = baseline_step["working_memory"]
    budgeted_leaf_nodes = [n for n in budgeted["dependency_tree"] if n["kind"] == "document_leaf"]
    baseline_leaf_nodes = [n for n in baseline["dependency_tree"] if n["kind"] == "document_leaf"]

    e2e = {
        "budgeted_decision": budgeted["decision"],
        "budgeted_ram_budget": budgeted_wm["ram_budget"],
        "budgeted_in_ram_pages": len(budgeted_wm["pages"]),
        "budgeted_archived_page_count": budgeted_wm["archived_page_count"],
        "budgeted_dependency_tree_leaf_count": len(budgeted_leaf_nodes),
        "baseline_decision": baseline["decision"],
        "baseline_ram_budget": baseline_wm["ram_budget"],
        "baseline_in_ram_pages": len(baseline_wm["pages"]),
        "baseline_archived_page_count": baseline_wm["archived_page_count"],
        "baseline_dependency_tree_leaf_count": len(baseline_leaf_nodes),
    }

    e2e_ram_capped = e2e["budgeted_in_ram_pages"] <= 2 and e2e["budgeted_archived_page_count"] >= 3
    e2e_provenance_complete = e2e["budgeted_dependency_tree_leaf_count"] == e2e["budgeted_archived_page_count"] + e2e["budgeted_in_ram_pages"]
    e2e_baseline_unaffected = e2e["baseline_ram_budget"] is None and e2e["baseline_archived_page_count"] == 0 and e2e["baseline_in_ram_pages"] == e2e["baseline_dependency_tree_leaf_count"]

    metrics = {
        "unit_test": unit,
        "end_to_end_via_brain_reason": e2e,
        "e2e_ram_capped": e2e_ram_capped,
        "e2e_provenance_complete": e2e_provenance_complete,
        "e2e_baseline_unaffected": e2e_baseline_unaffected,
    }
    run.write_json("items.json", metrics)

    all_correct = (
        unit["ram_budget_respected"]
        and unit["archived_page_contradiction_caught"]
        and unit["dependency_tree_covers_all_pages"]
        and e2e_ram_capped
        and e2e_provenance_complete
        and e2e_baseline_unaffected
    )

    prose = (
        f"Direct unit test: 5 pages, ram_budget=2 -- RAM never holds more than {len(unit['final_ram_pages'])} pages "
        f"at once ({unit['final_ram_pages']}), {unit['archived_page_count']} archived to disk. Page L4's claim "
        f"conflicts with L0 (ram-evicted 3 pages earlier) -- correctly still caught: "
        f"{unit['archived_page_contradiction_caught']}. dependency_tree reports all "
        f"{unit['dependency_tree_leaf_count']} pages, archived or not. Through the real lab.common.brain.reason "
        f"entry point, 5 entity leaves with working_memory_ram_budget=2: RAM capped at "
        f"{e2e['budgeted_in_ram_pages']} pages, {e2e['budgeted_archived_page_count']} archived, decision="
        f"{e2e['budgeted_decision']!r}. With the parameter omitted entirely (today's existing behavior): RAM holds "
        f"all {e2e['baseline_in_ram_pages']} pages, zero archived, decision={e2e['baseline_decision']!r} -- "
        f"unaffected."
    )

    conclusion = (
        "lab.common.page_archive is now wired into lab.common.working_memory as working_memory_ram_budget= / "
        "working_memory_overflow_path= (both default None, zero regression for every existing caller), bounding "
        "the one place the controller's own cross-page memory grew without limit for the duration of a document-"
        "write call. The part a shallow cap would have gotten wrong is proven directly: a contradiction against a "
        "page that aged out of RAM onto disk many evictions ago is still caught, and that page still appears in "
        "the document's own provenance tree -- archiving a page changes WHERE it lives, never whether this "
        "project's own checks can still see it."
        if all_correct
        else "At least one case did not behave as expected -- see metrics for exactly which, reported as "
        "measured, not assumed to work."
    )

    run.finish(
        title="lab.common.page_archive wired into lab.common.working_memory as a disk-backed RAM cap on cross-page memory",
        goal=(
            "Bound lab.common.working_memory.WorkingMemory's own in-RAM page list, which grew by one digest per "
            "leaf for as long as a document was being written with no cap at all -- the project owner's own named "
            "concern that this would 'explode' on a long enough document -- the same way a person writing "
            "something long keeps a short active working set in mind and files everything older away as reference "
            "material, not held or re-read in full."
        ),
        method=(
            "A direct WorkingMemory unit test (5 pages, ram_budget=2, the 5th page's claim deliberately conflicts "
            "with the 1st, long since evicted) checking the RAM cap holds, the archived-page contradiction is "
            "still caught, and dependency_tree still covers every page. Then the identical mechanism exercised "
            "through the real lab.common.brain.reason entry point (5 real entity leaves, working_memory_ram_"
            "budget=2 vs. the parameter omitted) checking the cap, the archive count, and that omitting the "
            "parameter leaves today's behavior completely unchanged."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="5 pages, ram_budget=2 -- a proof the cap, archive, and recall-from-disk cycle work correctly end to end and preserve provenance, not a capacity or performance benchmark for a genuinely long (hundreds/thousands-of-leaf) document.",
        referenced_files=FILES,
        follow_ups=[
            "Only WorkingMemory.pages (the controller's cross-page digest list) is bounded by this -- write_long_document's own `rendered_units` list (every leaf's full rendered text, held in RAM until joined into one `document_text` string at the end) is NOT touched here; that is a separate, larger architectural question (brain.reason's document_write branch returns that full text as the answer itself, so eliminating it would change what a caller gets back, not just how it's held internally) and was deliberately not forced into this scoped change.",
            "page_archive's lookup is an exact (subject, verb_lemma) key match, the same access pattern lab.common.memory's notes table already uses -- it deliberately does not use lab.common.nested_index's hierarchical/semantic navigation, which answers a different question (what is this branch ABOUT) that cross-page consistency checking has never needed. If a future need arises to search archived pages by topic rather than by exact claim, that is a real, separate extension, not implied by this one.",
            "No eviction policy beyond strict oldest-first exists (no 'pin this page' concept, unlike lab.common.paged.WorkingSet's relevance-based eviction for retrieval) -- for cross-page consistency checking specifically, recency is not actually the right signal (an old page is exactly as able to conflict with a new one as a recent page is), but the archive's exact-key lookup already makes that largely moot: an archived page is still fully checkable, just not held in RAM, so no page's claim is ever truly lost regardless of eviction order.",
        ],
        models_used="None -- page_archive is deterministic SQLite with an index on (subject, verb_lemma); no model of any kind is involved in archiving or recall.",
    )

    print(
        "unit_ram_ok:", unit["ram_budget_respected"],
        "unit_archived_conflict_caught:", unit["archived_page_contradiction_caught"],
        "unit_provenance_ok:", unit["dependency_tree_covers_all_pages"],
        "e2e_ram_capped:", e2e_ram_capped,
        "e2e_provenance_complete:", e2e_provenance_complete,
        "e2e_baseline_unaffected:", e2e_baseline_unaffected,
    )
    print("ALL CORRECT:", all_correct)


if __name__ == "__main__":
    main()
