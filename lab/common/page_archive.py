"""Disk-backed overflow for lab.common.working_memory.WorkingMemory.

The gap this closes: WorkingMemory already compresses each page down to a
digest (subject-verb-object triples, never full text) before keeping it,
but that digest list (`self.pages`) still grows by one entry per leaf for
as long as a document is being written, held entirely in RAM, with no
cap -- fine for the handful of leaves every existing exploration writes,
not fine for a document long enough that "how many pages have been
written so far" stops being a small number.

The fix is not a smarter in-RAM structure -- it's the same thing a human
writer actually does: keep a short, recent working set actively in mind,
and file everything older away as reference material, consulted again
only on a specific, exact question ("did I already say something about
this subject doing this verb?"), not re-read start to finish. SQLite with
an index on (subject, verb_lemma) is a real index for exactly that
question -- an exact-key lookup, not a semantic search -- so it is used
here directly rather than wrapping it in a tree lab.common.nested_index's
own hierarchical navigation is built for a different access pattern
(searching by what a branch is *about*, via the hybrid retriever) that
this module does not need and should not force.
"""

from __future__ import annotations

import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS archived_pages (
    leaf_id TEXT PRIMARY KEY,
    triples_json TEXT NOT NULL,
    citation_ids_json TEXT NOT NULL,
    archive_order INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS archived_triples (
    leaf_id TEXT NOT NULL,
    subject_lower TEXT NOT NULL,
    verb_lemma TEXT NOT NULL,
    triple_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_archived_triples_subject_verb
    ON archived_triples (subject_lower, verb_lemma);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def archive_page(conn: sqlite3.Connection, leaf_id: str, triples: list[dict], citation_ids: list[str]) -> None:
    """Persists one page's digest and drops out of the caller's own RAM
    budget -- called only once a page is about to be evicted from
    WorkingMemory.pages, never for a page still in the active window."""
    order = conn.execute("SELECT COALESCE(MAX(archive_order), -1) + 1 FROM archived_pages").fetchone()[0]
    conn.execute(
        "INSERT OR REPLACE INTO archived_pages (leaf_id, triples_json, citation_ids_json, archive_order) VALUES (?, ?, ?, ?)",
        (leaf_id, json.dumps(triples), json.dumps(citation_ids), order),
    )
    conn.execute("DELETE FROM archived_triples WHERE leaf_id = ?", (leaf_id,))
    for triple in triples:
        if not triple.get("subject"):
            continue
        conn.execute(
            "INSERT INTO archived_triples (leaf_id, subject_lower, verb_lemma, triple_json) VALUES (?, ?, ?, ?)",
            (leaf_id, triple["subject"].lower(), triple.get("verb_lemma"), json.dumps(triple)),
        )
    conn.commit()


def find_claims(conn: sqlite3.Connection, subject: str, verb_lemma: str) -> list[dict]:
    """The one question this archive is actually asked: every earlier,
    now-archived page's triple with this exact (subject, verb) -- same
    shape WorkingMemory.find_prior_claims's in-RAM scan already returns,
    so a caller can merge the two lists without caring which page is
    still in RAM and which was filed away."""
    rows = conn.execute(
        "SELECT leaf_id, triple_json FROM archived_triples WHERE subject_lower = ? AND verb_lemma = ?",
        (subject.lower(), verb_lemma),
    ).fetchall()
    return [{"leaf_id": row["leaf_id"], "triple": json.loads(row["triple_json"])} for row in rows]


def all_pages(conn: sqlite3.Connection) -> list[dict]:
    """Every archived page's own digest, in the order it was archived --
    for WorkingMemory.dependency_tree to report a complete provenance
    tree (one node per page ever written, not just the ones still in
    RAM) without needing every page's triples held in memory at once."""
    rows = conn.execute("SELECT leaf_id, triples_json, citation_ids_json FROM archived_pages ORDER BY archive_order").fetchall()
    return [{"leaf_id": row["leaf_id"], "triples": json.loads(row["triples_json"]), "citation_ids": json.loads(row["citation_ids_json"])} for row in rows]
