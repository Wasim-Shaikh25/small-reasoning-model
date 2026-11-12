"""EXP-102: lab.common.memory (SQLite recall-with-revalidation), wired
into lab.common.brain.reason as its persistent, cross-CALL memory.

memory.py (EXP-016) had zero real callers anywhere outside its own
module before this (confirmed by grep, not assumed) -- the project's
own "brain RAM... not bounded by context length" architecture question,
the persistent counterpart to lab.common.working_memory's ephemeral,
single-document-write-session memory. An earlier pass in this same
session deliberately did NOT force a shallow wiring: revalidate()'s
whole point is catching "the source document changed since this note
was written", which only means something if the "archive" it checks
against is real, not faked from whatever happens to be on hand.

The actual wiring (reason()'s new `memory_path=` param, default None):
only at the one place a fact maps cleanly onto memory.py's schema --
lookup_fallback's own already-quote_checked span, tied to exactly one
source passage. A "supported" lookup answer gets written as a verified
note, keyed by the source passage's own content hash. Before the main
signal chain runs, memory.recall checks any previously-written note
that's ask-relevant against THIS call's own passages (direct +
connector-fetched) and reports every hit -- valid or not -- in `trace`
as `"memory_recall"`. This exploration proves the full cycle: write,
recall-when-still-valid, and -- the part a shallow wiring would have
gotten wrong -- correctly refuse to trust a note when its source
passage is absent this call, or when that passage's text has changed,
rather than silently reusing stale cached text.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run

FILES = [
    "lab/tests/exp_102_memory_wiring/run.py",
    "lab/common/brain.py",
    "lab/common/memory.py",
    "data/exp_102_memory_wiring/results.json",
]

ASK = "What is the notice period?"
PASSAGE = {"id": "P1", "text": "The notice period is 30 days."}
CHANGED_PASSAGE = {"id": "P1", "text": "The notice period is 60 days now, updated policy."}


def _recall_hits(result: dict) -> list[dict]:
    steps = [t for t in result["trace"] if t["step"] == "memory_recall"]
    return steps[0]["hits"] if steps else []


def main() -> None:
    run = Run("EXP-102", "exp_102_memory_wiring")
    db_path = run.out_dir / "memory.db"
    db_path.unlink(missing_ok=True)

    write = reason(ASK, [PASSAGE], memory_path=str(db_path))
    recall_valid = reason(ASK, [PASSAGE], memory_path=str(db_path))
    recall_missing = reason(ASK, [], memory_path=str(db_path))
    recall_stale = reason(ASK, [CHANGED_PASSAGE], memory_path=str(db_path))
    # No memory_path at all -- today's existing behavior, must be
    # completely unaffected (no memory_recall step, no DB access).
    no_memory = reason(ASK, [PASSAGE])

    write_correct = write["decision"] == "supported" and "30 days" in write["text"]
    valid_hits = _recall_hits(recall_valid)
    valid_correct = bool(valid_hits) and valid_hits[0]["valid"] is True and valid_hits[0]["chunk_id"] == "P1"
    missing_hits = _recall_hits(recall_missing)
    missing_correct = bool(missing_hits) and missing_hits[0]["valid"] is False and missing_hits[0]["reason"] == "missing_source"
    stale_hits = _recall_hits(recall_stale)
    stale_correct = bool(stale_hits) and stale_hits[0]["valid"] is False and stale_hits[0]["reason"] == "version_mismatch"
    # Even with a stale note on file, the system must still answer
    # correctly from the NEW passage text, not from the cached note.
    stale_still_answers_fresh = recall_stale["decision"] == "supported" and "60 days" in recall_stale["text"]
    no_memory_correct = "memory_recall" not in [t["step"] for t in no_memory["trace"]] and no_memory["decision"] == "supported"

    metrics = {
        "write": {"decision": write["decision"], "text": write["text"], "correct": write_correct},
        "recall_valid": {"hits": valid_hits, "correct": valid_correct},
        "recall_missing_source": {"hits": missing_hits, "correct": missing_correct},
        "recall_version_mismatch": {"hits": stale_hits, "answer_text": recall_stale["text"], "stale_correct": stale_correct, "still_answers_fresh": stale_still_answers_fresh},
        "no_memory_path_unaffected": {"correct": no_memory_correct},
    }
    run.write_json("items.json", metrics)

    all_correct = write_correct and valid_correct and missing_correct and stale_correct and stale_still_answers_fresh and no_memory_correct

    prose = (
        f"Write: decision={write['decision']!r}, text={write['text']!r}. Recall with the same passage still "
        f"present and unchanged: {valid_hits} (valid={valid_correct}). Recall with the passage absent this "
        f"call: {missing_hits} (correctly missing_source={missing_correct}). Recall with the passage PRESENT "
        f"but its text CHANGED: {stale_hits} (correctly version_mismatch={stale_correct}) -- and the system "
        f"still answers correctly from the new text ({recall_stale['text']!r}), never from the stale cached "
        f"note. With memory_path omitted entirely: no memory_recall step at all, decision unaffected "
        f"({no_memory_correct})."
    )

    conclusion = (
        "lab.common.memory is now wired into lab.common.brain.reason as its persistent, cross-call memory "
        "(memory_path=, default None, zero regression for every existing caller), narrowly scoped to the one "
        "place a fact maps cleanly onto its schema (lookup_fallback's single verbatim span). The full cycle "
        "works end to end: a verified note is written, recalled correctly when its source is still present "
        "and unchanged, and -- the part that would have been wrong with a shallow wiring -- correctly refused "
        "when its source is absent or has changed, with the system falling back to fresh extraction rather "
        "than ever trusting a stale note blindly."
        if all_correct
        else "At least one case did not behave as expected -- see metrics for exactly which, reported as "
        "measured, not assumed to work."
    )

    run.finish(
        title="lab.common.memory wired into brain.reason as memory_path=, a persistent cross-call note cache that refuses to trust a stale or missing source",
        goal=(
            "Give lab.common.memory -- a confirmed-dormant module matching the project owner's 'brain RAM, "
            "not bounded by context length' architecture question -- its first real wiring into brain.reason, "
            "without faking the 'archive' revalidation depends on (the reason a shallow wiring was deliberately "
            "deferred earlier in this same session)."
        ),
        method=(
            "One fact, written once via a real lookup_fallback answer, then recalled under three conditions: "
            "its source passage still present and byte-identical (must revalidate); its source passage absent "
            "from the call entirely (must report missing_source, not reuse the note); its source passage "
            "present but with DIFFERENT text at the same id (must report version_mismatch AND still answer "
            "correctly from the new text). A fifth call with memory_path omitted checks zero behavior change "
            "for every existing caller."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="One fact, one passage id, three revalidation conditions -- a proof the write/recall/revalidate cycle is wired correctly and refuses to trust stale/missing sources, not a capacity or performance benchmark for the note store at scale.",
        referenced_files=FILES,
        follow_ups=[
            "Only wired at lookup_fallback's single-span-single-passage answer shape -- document_write, forward_chain, and rule-gate answers are not written as notes at all (their answer shape doesn't map onto memory.py's schema as directly); a dedicated design pass would be needed to decide what, if anything, those paths should write.",
            "memory.mark_conflicted is not wired -- nothing today compares a freshly-extracted answer against a still-valid recalled note and flags disagreement; this would parallel lab.common.working_memory's cross-page contradiction check but for cross-call facts instead.",
            "memory_recall is reported in trace only, never used to answer directly or skip extraction -- the same 'report, don't act on it yet' posture coherence_flags/contract_violations started with; a future pass could decide whether a valid, high-confidence recall should ever short-circuit re-extraction.",
        ],
        models_used="None -- memory.py's write/recall/revalidate is pure deterministic SQLite + string/hash comparison; the lookup_fallback answer it wraps uses whichever extractor the caller already selected (use_real_qa or the classical default), unchanged by this wiring.",
    )

    print("write_correct:", write_correct, "valid_correct:", valid_correct, "missing_correct:", missing_correct, "stale_correct:", stale_correct, "stale_still_answers_fresh:", stale_still_answers_fresh, "no_memory_correct:", no_memory_correct)
    print("ALL CORRECT:", all_correct)


if __name__ == "__main__":
    main()
