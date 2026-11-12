"""EXP-113: lab.common.store.ingest_and_store/ingest_and_upsert, wired
into brain.reason as an opt-in ingest_text= parameter.

EXP-099 named the gap directly: "No caller in this repo builds a Store
from real documents yet -- lab.common.ingest.chunk_document + Store.build/
ingest_and_store exist and are callable, but nothing in lab/ does this
outside this exploration's own fixture." ingest_and_store/ingest_and_upsert
themselves had zero callers anywhere in the committed codebase.

ingest_text=None by default (only meaningful together with a Store
connector): when given, the raw text is chunked and ingested into that
Store BEFORE the normal connector-fetch/retrieval runs -- ingest_and_store
for a collection with nothing persisted yet, ingest_and_upsert for one that
already has a persisted index, mirroring Store.exists()'s own
first-build-vs-append distinction.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run
from lab.common.store import Store

FILES = [
    "lab/tests/exp_113_store_ingest_wiring/run.py",
    "lab/common/brain.py",
    "lab/common/store.py",
    "lab/common/ingest.py",
    "data/exp_113_store_ingest_wiring/results.json",
]


def main() -> None:
    run = Run("EXP-113", "exp_113_store_ingest_wiring")

    base_dir = tempfile.mkdtemp()
    try:
        # Case 1: ingest_text into a brand-new, never-built collection --
        # ingest_and_store's own first-build path.
        fresh_store = Store("coll_113_fresh", base_dir=base_dir)
        fresh = reason(
            "What is the notice period?",
            [],
            connector=fresh_store,
            ingest_text="The notice period under this lease is 45 days.",
        )

        # Case 2: ingest_text into a collection that ALREADY has a
        # persisted index -- ingest_and_upsert's own append path. The
        # newly-ingested fact must be reachable alongside the original
        # seed passage, not replacing it.
        seeded_store = Store("coll_113_seeded", base_dir=base_dir).build([{"id": "S1", "text": "The security deposit is 20000 rupees."}])
        upserted = reason(
            "What is the notice period?",
            [],
            connector=Store("coll_113_seeded", base_dir=base_dir).load(),
            ingest_text="The notice period under this lease is 60 days.",
        )
        seed_still_reachable = reason("What is the security deposit?", [], connector=Store("coll_113_seeded", base_dir=base_dir).load())

        # Case 3: ingest_text omitted entirely -- zero behavior change for
        # a connector-only caller that never ingests anything.
        Store("coll_113_baseline", base_dir=base_dir).build([{"id": "B1", "text": "The notice period is 30 days."}])
        baseline = reason("What is the notice period?", [], connector=Store("coll_113_baseline", base_dir=base_dir).load())

        fresh_correct = fresh["decision"] == "supported" and "45 days" in fresh["text"]
        fresh_ingest_step = next((t for t in fresh["trace"] if t.get("step") == "ingest_text"), None)
        upserted_correct = upserted["decision"] == "supported" and "60 days" in upserted["text"]
        seed_correct = seed_still_reachable["decision"] == "supported" and "20000" in seed_still_reachable["text"]
        baseline_correct = baseline["decision"] == "supported" and "30 days" in baseline["text"] and not any(t.get("step") == "ingest_text" for t in baseline["trace"])

        metrics = {
            "ingest_into_fresh_collection": {"decision": fresh["decision"], "text": fresh["text"], "ingest_step": fresh_ingest_step, "correct": fresh_correct},
            "ingest_upserted_into_existing_collection": {"decision": upserted["decision"], "text": upserted["text"], "correct": upserted_correct},
            "original_seed_still_reachable_after_upsert": {"decision": seed_still_reachable["decision"], "text": seed_still_reachable["text"], "correct": seed_correct},
            "ingest_text_omitted_baseline": {"decision": baseline["decision"], "text": baseline["text"], "correct": baseline_correct},
        }
        run.write_json("items.json", metrics)
        all_correct = fresh_correct and upserted_correct and seed_correct and baseline_correct

        prose = (
            f"A brand-new, never-built collection with ingest_text given: {fresh['decision']!r}, "
            f"{fresh['text']!r} -- the raw text was chunked and built into a fresh Store "
            f"(ingest_and_store's own path), then immediately queryable in the same call. A collection "
            f"ALREADY seeded with a different fact: ingesting new text via ingest_and_upsert reaches "
            f"{upserted['text']!r}, and the ORIGINAL seeded fact is still separately reachable afterward "
            f"({seed_still_reachable['text']!r}) -- append, not replace. ingest_text omitted entirely on an "
            f"ordinary connector-only call: {baseline['text']!r}, zero ingest_text trace step -- completely "
            f"unaffected."
        )
        conclusion = (
            "lab.common.store.ingest_and_store/ingest_and_upsert -- present with zero callers anywhere, the "
            "exact gap EXP-099 named directly -- are now reachable from lab.common.brain.reason itself via "
            "ingest_text=, choosing the first-build vs. append path the same way Store.exists() already "
            "would. Every caller that never sets it takes the exact same path as before this wiring existed."
            if all_correct else
            "At least one case did not behave as expected -- see metrics for exactly which."
        )
        run.finish(
            title="ingest_and_store/ingest_and_upsert wired into brain.reason as an opt-in ingest_text= parameter",
            goal="Close EXP-099's own named gap: nothing in lab/ builds a Store from a real raw document before querying it -- every existing caller already has passages/a pre-built connector in hand.",
            method="Raw text ingested into a brand-new collection (first-build path) and immediately queried in the same call. Raw text ingested into an already-seeded collection (append path), checking both the new and the original fact are independently reachable afterward. ingest_text omitted on an ordinary connector-only call, checking zero behavior change.",
            metrics=metrics,
            results_prose=prose,
            conclusion=conclusion,
            scale_down="One short document per case -- a proof the ingest-then-query sequencing and first-build/append dispatch work end to end, not a benchmark of chunk_document's own chunking quality at real-document scale (already exercised in EXP-081/088).",
            referenced_files=FILES,
            follow_ups=[
                "A multi-round retrieve_budget retry never re-ingests (ingest_text is explicitly passed as None on every retried _reason_once call) -- deliberate, to avoid upserting the same text more than once, but means a retry round cannot ingest MORE text mid-retry even if that were ever wanted.",
            ],
            models_used="None by default (the lexical Index leg) -- Store.build/upsert's own use_bge/use_graph opt-ins are unused here, unchanged from how Store already worked.",
        )
        print("fresh_correct:", fresh_correct, "upserted_correct:", upserted_correct, "seed_correct:", seed_correct, "baseline_correct:", baseline_correct)
        print("ALL CORRECT:", all_correct)
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
