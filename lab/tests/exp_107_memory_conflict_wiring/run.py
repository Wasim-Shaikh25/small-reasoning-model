"""EXP-107: memory.mark_conflicted, wired into lab.common.brain.reason's
existing memory_path= mechanism.

brain.py's own docstring (and EXP-102's own note) named this gap directly:
memory_recall already found and reported a prior valid note on every call,
but nothing ever compared that note against what the CURRENT call just
found -- mark_conflicted existed in lab.common.memory since 2026-11-11 with
zero callers anywhere. Asked directly to wire it in.

Wired at the one place a fresh fact and a recalled note are both already in
hand: lookup_fallback's own span extraction, right before it writes its OWN
new note. Any recalled hit that is still VALID (its source chunk present
and unchanged) but comes from a DIFFERENT passage than the one that just
answered this ask, and whose stored statement NLI-contradicts the fresh
passage text (lab.common.nli.judge, contradict >= 0.45 -- the same
threshold _check_cross_passage_contradiction already uses), is marked
conflicted on the OLDER note. No new parameter: this rides entirely on the
existing memory_path= opt-in, since it is completing that mechanism, not
adding a new capability surface.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run

FILES = [
    "lab/tests/exp_107_memory_conflict_wiring/run.py",
    "lab/common/brain.py",
    "lab/common/memory.py",
    "lab/common/nli.py",
    "data/exp_107_memory_conflict_wiring/results.json",
]

ASK = "What is the notice period?"


def _notes(db_path: str) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT note_id, verification_status, conflicts FROM notes").fetchall()
    conn.close()
    return rows


def main() -> None:
    run = Run("EXP-107", "exp_107_memory_conflict_wiring")

    db_path = tempfile.mktemp(suffix=".db")
    call1 = reason(ASK, [{"id": "P1", "text": "The notice period is 30 days."}], memory_path=db_path)
    # The SAME source passage (P1) is still supplied here alongside a NEW,
    # directly conflicting one (P2) -- P1 must still be present for its
    # note to revalidate as "valid" at all; a note whose source vanished
    # is correctly "missing_source" (unchanged, untouched by this wiring),
    # not a case this feature can or should act on.
    call2 = reason(ASK, [{"id": "P1", "text": "The notice period is 30 days."}, {"id": "P2", "text": "The notice period is 6 months."}], memory_path=db_path)
    conflict_steps = [t for t in call2["trace"] if t.get("step") == "memory_conflict_detected"]
    rows_after = _notes(db_path)
    p1_row = next((r for r in rows_after if r[1] == "conflicted"), None)

    db_path_no_conflict = tempfile.mktemp(suffix=".db")
    recall1 = reason(ASK, [{"id": "P1", "text": "The notice period is 30 days."}], memory_path=db_path_no_conflict)
    recall2 = reason(ASK, [{"id": "P1", "text": "The notice period is 30 days."}], memory_path=db_path_no_conflict)
    no_conflict_steps = [t for t in recall2["trace"] if t.get("step") == "memory_conflict_detected"]
    rows_no_conflict = _notes(db_path_no_conflict)

    baseline = reason(ASK, [{"id": "P1", "text": "The notice period is 30 days."}])

    conflict_correct = (
        call1["decision"] == "supported"
        and call2["decision"] == "supported"
        and len(conflict_steps) == 1
        and p1_row is not None
        and '"conflicting_chunk_id": "P2"' in p1_row[2]
    )
    no_conflict_correct = (
        len(no_conflict_steps) == 0
        and all(r[1] == "verified" for r in rows_no_conflict)
    )
    baseline_correct = baseline["decision"] == "supported" and "memory_conflict_detected" not in [t["step"] for t in baseline["trace"]]

    metrics = {
        "genuine_conflict": {
            "call1_decision": call1["decision"],
            "call2_decision": call2["decision"],
            "conflict_steps_found": len(conflict_steps),
            "note_marked_conflicted": p1_row is not None,
            "correct": conflict_correct,
        },
        "repeated_agreeing_recall": {
            "conflict_steps_found": len(no_conflict_steps),
            "all_notes_still_verified": all(r[1] == "verified" for r in rows_no_conflict),
            "correct": no_conflict_correct,
        },
        "memory_path_omitted_baseline": {
            "decision": baseline["decision"],
            "correct": baseline_correct,
        },
    }
    run.write_json("items.json", metrics)
    all_correct = conflict_correct and no_conflict_correct and baseline_correct

    prose = (
        f"Call 1 writes a verified note from P1 (30 days). Call 2 supplies P1 again plus a directly "
        f"conflicting P2 (6 months) for the same ask: {call2['decision']!r}, with exactly "
        f"{len(conflict_steps)} memory_conflict_detected trace step(s), and P1's own note flips to "
        f"verification_status='conflicted' in the SQLite store. A second scenario recalling the SAME "
        f"unchanged fact twice (no real disagreement) produces zero conflict steps and leaves every note "
        f"'verified' -- the mechanism does not fire on agreement. memory_path omitted entirely: zero "
        f"behavior change, no memory_conflict_detected step possible."
    )
    conclusion = (
        "lab.common.memory.mark_conflicted -- present since 2026-11-11 with zero callers anywhere -- is now "
        "wired into lab.common.brain.reason's existing memory_path= lookup_fallback path. A genuine "
        "disagreement between a still-valid recalled note and a freshly extracted answer for the same ask is "
        "recorded on the older note, not silently dropped or silently overwritten; an ordinary repeated, "
        "agreeing recall is correctly left untouched."
        if all_correct else
        "At least one case did not behave as expected -- see metrics for exactly which."
    )
    run.finish(
        title="memory.mark_conflicted wired into brain.reason's existing memory_path= mechanism",
        goal="Close the named gap: memory_recall already reports a prior valid note every call, but nothing ever compared it against what THIS call found. Wire mark_conflicted so a genuine disagreement is recorded, not silently dropped.",
        method="Two reason() calls sharing one SQLite memory store: the second supplies the first's own source passage again plus a directly conflicting new one, checking the conflict is detected and recorded. A second pair of calls recalls the SAME fact twice (no disagreement), checking the mechanism stays silent. A third, memory_path-omitted baseline checks zero behavior change for every existing caller.",
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="One fact, one conflicting fact, two calls -- a proof the detection/recording wiring works end to end, not a measurement of lab.common.nli.judge's own contradiction-detection precision at scale (already a known, documented limitation of the classical judge, unchanged by this wiring).",
        referenced_files=FILES,
        follow_ups=[
            "mark_conflicted records the conflict on the note but memory.recall's own hit shape does not yet surface a note's conflicts list back to the caller -- a later recall of a conflicted note still reports it the same way as any other valid hit, just with a DB-side verification_status='conflicted' a caller would have to query separately to see.",
        ],
        models_used="lab.common.nli.judge (classical, deterministic: token coverage + number/polarity checks) -- no generative or real pretrained model involved.",
    )
    print("conflict_correct:", conflict_correct, "no_conflict_correct:", no_conflict_correct, "baseline_correct:", baseline_correct)
    print("ALL CORRECT:", all_correct)


if __name__ == "__main__":
    main()
