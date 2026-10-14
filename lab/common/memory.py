"""SQLite recall memory. Notes store pointers and are revalidated before use."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    note_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    statement TEXT NOT NULL,
    doc_id TEXT,
    version_hash TEXT,
    page INTEGER,
    chunk_id TEXT,
    exact_text TEXT,
    verification_status TEXT,
    verification_method TEXT,
    importance REAL,
    conflicts TEXT,
    use_count INTEGER DEFAULT 0,
    created_at TEXT,
    last_used_at TEXT
);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def write_note(conn: sqlite3.Connection, note: dict, *, verified: bool) -> dict:
    if not verified:
        return {"written": False, "reason": "unverified"}
    if note.get("kind") not in {"stated_fact", "entity_fact", "inference"}:
        return {"written": False, "reason": "bad_kind"}
    source = note.get("source") or {}
    if not source.get("exact_text") or not source.get("chunk_id"):
        return {"written": False, "reason": "missing_pointer"}
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT OR REPLACE INTO notes (
            note_id, kind, statement, doc_id, version_hash, page, chunk_id,
            exact_text, verification_status, verification_method, importance,
            conflicts, use_count, created_at, last_used_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            note["note_id"],
            note["kind"],
            note["statement"],
            source.get("doc_id"),
            source.get("version"),
            source.get("page"),
            source.get("chunk_id"),
            source.get("exact_text"),
            "verified",
            (note.get("verification") or {}).get("method", "quote"),
            float(note.get("importance", 0.5)),
            json.dumps(note.get("conflicts") or []),
            int(note.get("use_count") or 0),
            now,
            now,
        ),
    )
    conn.commit()
    return {"written": True, "note_id": note["note_id"]}


def revalidate(row: sqlite3.Row, archive: dict) -> dict:
    """archive maps chunk_id -> {version, text}."""
    current = archive.get(row["chunk_id"])
    if current is None:
        return {"valid": False, "reason": "missing_source"}
    if current.get("version") != row["version_hash"]:
        return {"valid": False, "reason": "version_mismatch"}
    if row["exact_text"] not in (current.get("text") or ""):
        return {"valid": False, "reason": "exact_text_missing"}
    return {"valid": True, "reason": "ok"}


def recall(conn: sqlite3.Connection, query_terms: list[str], archive: dict) -> list[dict]:
    rows = conn.execute("SELECT * FROM notes").fetchall()
    hits = []
    for row in rows:
        statement = (row["statement"] or "").lower()
        if query_terms and not any(term.lower() in statement for term in query_terms):
            continue
        check = revalidate(row, archive)
        if not check["valid"]:
            hits.append({"note_id": row["note_id"], "valid": False, "reason": check["reason"]})
            continue
        conn.execute(
            "UPDATE notes SET use_count = use_count + 1, last_used_at = ? WHERE note_id = ?",
            (datetime.now(timezone.utc).isoformat(), row["note_id"]),
        )
        hits.append({"note_id": row["note_id"], "valid": True, "statement": row["statement"], "chunk_id": row["chunk_id"]})
    conn.commit()
    return hits


def mark_conflicted(conn: sqlite3.Connection, note_id: str, conflict: dict) -> None:
    row = conn.execute("SELECT conflicts FROM notes WHERE note_id = ?", (note_id,)).fetchone()
    if row is None:
        return
    current = json.loads(row["conflicts"] or "[]")
    current.append(conflict)
    conn.execute(
        "UPDATE notes SET conflicts = ?, verification_status = ? WHERE note_id = ?",
        (json.dumps(current), "conflicted", note_id),
    )
    conn.commit()


def wrong_note_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM notes WHERE verification_status != 'verified' OR exact_text IS NULL OR exact_text = ''"
    ).fetchone()
    return int(row["n"])
