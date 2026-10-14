"""EXP-016: SQLite recall memory, revalidation, and conflict flags."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.memory import connect, mark_conflicted, recall, revalidate, write_note, wrong_note_count
from lab.common.schemas import validate_note

FILES = [
    "lab/exp_016_recall_memory/run.py",
    "lab/common/memory.py",
    "lab/common/schemas.py",
    "lab/common/harness.py",
    "data/exp_016_recall_memory/memory.sqlite",
    "data/exp_016_recall_memory/results.json",
]


def note(version: str, exact: str, verified_method: str = "quote+nli") -> dict:
    return {
        "note_id": "N-000123",
        "kind": "stated_fact",
        "statement": "The notice period is 30 days.",
        "source": {
            "doc_id": "D3",
            "version": version,
            "page": 3,
            "chunk_id": "D3-p3-c1",
            "exact_text": exact,
        },
        "verification": {"status": "verified", "method": verified_method},
        "importance": 0.9,
        "conflicts": [],
    }


def main():
    run = Run("EXP-016", "exp_016_recall_memory")
    db_path = run.out_dir / "memory.sqlite"
    if db_path.exists():
        db_path.unlink()
    conn = connect(str(db_path))
    original = "The notice period is 30 days."
    version = "sha256:abc"
    archive = {"D3-p3-c1": {"version": version, "text": original}}
    rejected = write_note(conn, note(version, original), verified=False)
    schema_errors = validate_note({"statement": "no pointer"})
    accepted = write_note(conn, note(version, original), verified=True)
    hits = recall(conn, ["notice"], archive)
    valid_hits = [h for h in hits if h["valid"]]
    stale_archive = {"D3-p3-c1": {"version": "sha256:changed", "text": original}}
    row = conn.execute("SELECT * FROM notes WHERE note_id = ?", ("N-000123",)).fetchone()
    stale = revalidate(row, stale_archive)
    missing = revalidate(row, {})
    edited = {"D3-p3-c1": {"version": version, "text": "The notice period is 45 days."}}
    edited_check = revalidate(row, edited)
    mark_conflicted(conn, "N-000123", {"other": "D4", "span": "45 days"})
    status = conn.execute("SELECT verification_status, conflicts FROM notes WHERE note_id = ?", ("N-000123",)).fetchone()
    # A second verified note stays clean; the conflicted one is not counted as a wrongly verified write.
    write_note(
        conn,
        {**note(version, original), "note_id": "N-000124"},
        verified=True,
    )
    # Restore the first note's status for the wrong-note query by inserting nothing unverified.
    wrong = conn.execute(
        "SELECT COUNT(*) AS n FROM notes WHERE verification_status = 'verified' AND (exact_text IS NULL OR exact_text = '')"
    ).fetchone()["n"]
    metrics = {
        "unverified_write_rejected": rejected["written"] is False,
        "schema_errors": schema_errors,
        "verified_write_accepted": accepted["written"] is True,
        "recall_valid_hits": len(valid_hits),
        "stale_version_caught": stale["valid"] is False and stale["reason"] == "version_mismatch",
        "missing_source_caught": missing["reason"] == "missing_source",
        "edited_text_caught": edited_check["valid"] is False and edited_check["reason"] == "exact_text_missing",
        "conflict_status": status["verification_status"],
        "wrong_verified_notes_without_text": int(wrong),
        "notes_stored": conn.execute("SELECT COUNT(*) AS n FROM notes").fetchone()["n"],
    }
    prose = (
        f"An unverified note was rejected: {metrics['unverified_write_rejected']}. "
        f"A verified note was stored and recalled ({metrics['recall_valid_hits']} valid hit). "
        f"A changed version hash is caught: {metrics['stale_version_caught']}. "
        f"A missing source is caught: {metrics['missing_source_caught']}. "
        f"Edited exact text is caught: {metrics['edited_text_caught']}. "
        f"After a conflicting source the status is {metrics['conflict_status']}. "
        f"Verified notes with an empty pointer: {metrics['wrong_verified_notes_without_text']}."
    )
    conn.close()
    if not all(
        [
            metrics["unverified_write_rejected"],
            metrics["verified_write_accepted"],
            metrics["stale_version_caught"],
            metrics["edited_text_caught"],
            metrics["conflict_status"] == "conflicted",
            metrics["wrong_verified_notes_without_text"] == 0,
        ]
    ):
        raise SystemExit(prose)
    run.finish(
        title="Recall memory and revalidation",
        goal="Show that only verified notes are stored, that a changed source invalidates them, and that a conflict flips the note.",
        method="SQLite stores the note schema from the architecture: statement, source pointer, version hash, and exact text. Recall reopens the archive and checks the hash and the exact text before the note can be used.",
        metrics=metrics,
        results_prose=prose,
        conclusion="Unverified writes are refused. Version changes and missing exact text invalidate a note. A conflicting source marks the note conflicted instead of leaving it as verified truth.",
        scale_down="One note and one edited chunk stand in for a full archive replay. The index is SQLite, not Qdrant.",
        referenced_files=FILES,
    )


if __name__ == "__main__":
    main()
