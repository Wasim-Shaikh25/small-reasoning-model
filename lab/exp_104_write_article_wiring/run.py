"""EXP-104: lab.common.article_tool.write_article_tool, wired into
lab.common.brain.reason as `notes=`, closing brain.py's own stated design
principle ("one controller, not a dispatcher to separate task-type
engines") against a real gap: EXP-098's own follow_ups explicitly named
write_article_tool as "not reachable from lab.common.brain.reason -- it
answers a different question shape (write a document from notes) than
reason() does (answer a question from documents)" and suggested, if ever
wired, it belongs as a sibling entry point, not a brain.reason stage.

Revisited and wired in anyway, as directly asked: `notes` (raw, possibly
messy free text) is a hard, explicit dispatch signal, not something
inferred from `ask`'s own wording the way document_write's own intent
signal is -- when given, `_reason_once` goes straight to
`write_article_tool`, `ask` is never read by it, and every stage-
planning/connector-fetch/working_set/memory-recall mechanism below is
skipped entirely, since none of them answer this mode's actual question.
Passages become `write_article_tool`'s own `sources` verbatim -- nothing
is added to or filtered from that list on this mode's behalf, the same
"don't search, just use exactly what was given" contract write_article_
tool itself already has standalone.

This exploration proves: a real multi-source article is produced through
the real `reason()` entry point with correct coverage and citations; a
genuine relationship cycle in the input notes is surfaced as
`"supported_with_flags"`, not silently dropped; malformed input (empty
notes) abstains cleanly (`"inconclusive"`) through the exact same
`_finish` path every other abstention in this module already uses,
instead of crashing or guessing; and every existing caller that never
sets `notes` takes the exact same path as before this parameter existed.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run

FILES = [
    "lab/exp_104_write_article_wiring/run.py",
    "lab/common/brain.py",
    "lab/common/article_tool.py",
    "lab/common/write_article.py",
    "lab/common/relationship_graph.py",
    "lab/common/notes_to_findings.py",
    "data/exp_104_write_article_wiring/results.json",
]

SOURCES = [
    {"id": "S1", "text": "Ravi Sharma is the Lessee of the Pune flat."},
    {"id": "S2", "text": "ABC Pvt Ltd is the Lessor."},
    {"id": "S3", "text": "Ravi paid ABC a deposit. ABC paid Meera a referral fee. Meera paid Ravi a finder's fee."},
]

NOTES = (
    "Ravi Sharma is the Lessee. ABC Pvt Ltd is the Lessor. "
    "Ravi paid ABC a deposit. ABC paid Meera a referral fee. Meera paid Ravi a finder's fee."
)

LOOKUP_ASK = "What is the notice period?"
LOOKUP_PASSAGES = [{"id": "P1", "text": "The notice period is 30 days."}]


def main() -> None:
    run = Run("EXP-104", "exp_104_write_article_wiring")

    article_result = reason("unused ask", SOURCES, notes=NOTES)
    write_step = next((t for t in article_result["trace"] if t["step"] == "write_article_result"), None)
    article_dep_nodes = [n for n in article_result["dependency_tree"] if n["kind"] == "write_article"]

    bad_result = reason("unused ask", SOURCES, notes="   ")
    bad_step = next((t for t in bad_result["trace"] if t["step"] == "write_article"), None)

    baseline = reason(LOOKUP_ASK, LOOKUP_PASSAGES)

    article_correct = (
        article_result["decision"] == "supported_with_flags"
        and {"S1", "S2", "S3"} <= set(article_result["citations"])
        and write_step is not None
        and write_step["coverage"]["coverage"] == 1.0
        and len(write_step["relationships"]["cycles"]) >= 1
        and len(article_dep_nodes) == 1
    )
    bad_input_correct = bad_result["decision"] == "inconclusive" and bad_step is not None and bad_step["ok"] is False
    baseline_unaffected = baseline["decision"] == "supported" and baseline["text"] == "30 days [P1]" and "write_article" not in [t["step"] for t in baseline["trace"]]

    metrics = {
        "article_mode": {
            "decision": article_result["decision"],
            "citations": sorted(article_result["citations"]),
            "coverage": write_step["coverage"] if write_step else None,
            "cycles_found": len(write_step["relationships"]["cycles"]) if write_step else 0,
            "dependency_tree_nodes": article_dep_nodes,
            "correct": article_correct,
        },
        "malformed_input": {
            "decision": bad_result["decision"],
            "errors": bad_step["errors"] if bad_step else None,
            "correct": bad_input_correct,
        },
        "notes_omitted_baseline": {
            "decision": baseline["decision"],
            "text": baseline["text"],
            "correct": baseline_unaffected,
        },
    }
    run.write_json("items.json", metrics)

    all_correct = article_correct and bad_input_correct and baseline_unaffected

    prose = (
        f"notes= given with 3 real sources (one containing a 3-way payment cycle): decision="
        f"{article_result['decision']!r}, citations={sorted(article_result['citations'])}, coverage="
        f"{metrics['article_mode']['coverage']['coverage']}, {metrics['article_mode']['cycles_found']} relationship "
        f"cycle(s) found and correctly surfaced as supported_with_flags, not silently dropped. Malformed input "
        f"(empty notes): decision={bad_result['decision']!r}, same abstain-don't-guess path every other failure "
        f"in this module already takes, not a crash or a guess. notes= omitted entirely (today's existing "
        f"behavior, a plain lookup ask): decision={baseline['decision']!r}, text={baseline['text']!r}, zero "
        f"write_article step in trace -- completely unaffected."
    )

    conclusion = (
        "lab.common.article_tool.write_article_tool is now reachable from lab.common.brain.reason (notes=, "
        "default None, zero regression for every existing caller), closing the gap brain.py's own docstring "
        "claims to close ('one controller, not a dispatcher to separate task-type engines') against a real, "
        "previously-undispatched capability. The part that matters is the dispatch is honest about the shape "
        "difference EXP-098 already identified: notes= is a hard signal on the caller's own input, not inferred "
        "from `ask`, and bypasses every ask-driven mechanism (stage planning, connector fetch, working_set, "
        "memory recall) that doesn't apply to this question shape at all, rather than forcing this capability "
        "through machinery built for a different one."
        if all_correct
        else "At least one case did not behave as expected -- see metrics for exactly which, reported as "
        "measured, not assumed to work."
    )

    run.finish(
        title="lab.common.article_tool wired into brain.reason as notes=, a hard dispatch to a genuinely different question shape",
        goal=(
            "Close the gap EXP-098 itself named and left open: write_article_tool existed, worked, and was "
            "schema-checked, but had no path through lab.common.brain.reason, the project's own stated single "
            "controller -- revisited on the project owner's own direct instruction rather than left as a "
            "'maybe a sibling entry point' follow-up."
        ),
        method=(
            "Three real sources (one containing a genuine 3-way payment relationship cycle) plus matching notes, "
            "passed to reason(notes=...) -- checking decision, citations, coverage, and that the cycle is "
            "surfaced, not dropped. Empty notes, checking the same abstain path (not a crash) every other "
            "malformed-input case in this module already uses. notes= omitted entirely on an ordinary lookup "
            "ask, checking that path is completely unaffected."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="3 sources, 1 relationship cycle, one malformed-input case -- a proof the dispatch, citation extraction, and cycle-flagging work correctly end to end through the real reason() entry point, not a benchmark of write_article_tool's own article quality at scale (already separately measured by EXP-098).",
        referenced_files=FILES,
        follow_ups=[
            "check_contradiction/retrieve_budget (reason()'s own retry/cross-passage-contradiction options) are not specially guarded against notes= -- both are opt-in and off by default, and retrieve_budget's retry loop only ever fires when connector is not None, so the combination is inert today, but a caller that deliberately sets both was not tested here.",
            "The decision label 'supported_with_flags' is reused for a relationship-cycle flag here, the same label document_write's own consistency_flags use for a different kind of flag (cross-page contradiction) -- both mean 'answered, but look closer', which is correct, but a caller inspecting trace needs to check which stage ran (write_article vs longform_write) to know which kind of flag it actually is, not just the top-level decision string.",
            "write_article_tool's own CLI entry point (reading a JSON payload from stdin/argv) is untouched and still works standalone -- this wiring only adds a second way to reach the same function, through reason(), without removing or changing the first.",
        ],
        models_used="None -- write_article_tool's own pipeline (notes_to_findings, the one-finding-at-a-time deterministic splice, assemble, relationship_graph's cycle detection) is fully deterministic as of 2026-11-11 (rewriter_backends's module docstring); no model of any kind is involved in this dispatch.",
    )

    print(
        "article_correct:", article_correct,
        "bad_input_correct:", bad_input_correct,
        "baseline_unaffected:", baseline_unaffected,
    )
    print("ALL CORRECT:", all_correct)


if __name__ == "__main__":
    main()
