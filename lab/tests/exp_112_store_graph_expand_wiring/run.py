"""EXP-112: lab.common.store.Store.expand_entity, wired into brain.reason's
graph_expand stage as an opt-in merge alongside the existing in-memory
expansion.

graph_expand's own ephemeral entity graph (lab.common.graph_index.
build_entity_graph) is rebuilt fresh from THIS call's own in-memory
`passages` every time -- it can never reach further than what is already
in hand. Store.expand_entity walks a graph PERSISTED ON DISK for a
connector's whole collection instead (built once, at Store.build(...,
use_graph=True) time, over every passage ever ingested), so it can reach
an entity hop the in-memory graph never saw at all.

expand_via_store_graph=False by default: the Store-graph lookup is only
ever attempted when the caller opts in AND connector is a Store with a
persisted graph; merged with (never replacing) the existing in-memory
expansion.
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
    "lab/tests/exp_112_store_graph_expand_wiring/run.py",
    "lab/common/brain.py",
    "lab/common/store.py",
    "lab/common/graph_index.py",
    "data/exp_112_store_graph_expand_wiring/results.json",
]

PASSAGES = [
    {"id": "G1", "text": "Ravi Sharma works at ABC Pvt Ltd."},
    {"id": "G2", "text": "ABC Pvt Ltd is located in Pune."},
]
ASK = "Where does Ravi Sharma work, and where is that located?"


def main() -> None:
    run = Run("EXP-112", "exp_112_store_graph_expand_wiring")

    base_dir = tempfile.mkdtemp()
    try:
        store = Store("coll_112", base_dir=base_dir).build(PASSAGES, use_graph=True)
        # connector_top_k=0 isolates the graph-only path: the connector's
        # own generic text search (fetch_context_passages' default branch,
        # unrelated to graph_expand) contributes nothing, so any passage
        # reached beyond G1 can only have come through entity-graph
        # expansion -- in-memory, Store-persisted, or both.
        off = reason(ASK, [PASSAGES[0]], connector=store, connector_top_k=0, expand_via_store_graph=False)
        on = reason(ASK, [PASSAGES[0]], connector=store, connector_top_k=0, expand_via_store_graph=True)

        no_graph_store = Store("coll_112_nograph", base_dir=base_dir).build(PASSAGES, use_graph=False)
        no_graph = reason(ASK, [PASSAGES[0]], connector=no_graph_store, connector_top_k=0, expand_via_store_graph=True)

        off_reached_g2 = "G2" in off["citations"]
        on_reached_g2 = "G2" in on["citations"]
        graph_expand_step = next((t for t in on["trace"] if t.get("step") == "graph_expand"), None)

        off_correct = off["decision"] == "supported" and not off_reached_g2
        on_correct = on["decision"] == "supported" and on_reached_g2 and graph_expand_step is not None
        no_graph_correct = no_graph["decision"] == "supported" and "G2" not in no_graph["citations"]

        metrics = {
            "expand_via_store_graph_omitted_baseline": {"citations": sorted(off["citations"]), "reached_g2": off_reached_g2, "correct": off_correct},
            "expand_via_store_graph_enabled": {
                "decision": on["decision"],
                "text": on["text"],
                "citations": sorted(on["citations"]),
                "reached_g2": on_reached_g2,
                "correct": on_correct,
            },
            "enabled_but_store_has_no_persisted_graph": {"citations": sorted(no_graph["citations"]), "reached_g2": "G2" in no_graph["citations"], "correct": no_graph_correct},
        }
        run.write_json("items.json", metrics)
        all_correct = off_correct and on_correct and no_graph_correct

        prose = (
            f"Only G1 given directly, connector_top_k=0 (no generic-search contribution): with "
            f"expand_via_store_graph omitted (default), the in-memory-only expansion reaches citations="
            f"{sorted(off['citations'])} -- G2 unreached, since the ephemeral graph built from G1 alone has "
            f"nowhere to hop to. Enabled: citations={sorted(on['citations'])}, text={on['text']!r} -- G2 "
            f"reached purely through Store.expand_entity's walk of the PERSISTED graph (built at Store.build "
            f"time over both passages). The same flag against a Store built WITHOUT use_graph=True correctly "
            f"reaches nothing extra -- Store.graph is None, so the new code path is a no-op, not an error."
        )
        conclusion = (
            "lab.common.store.Store.expand_entity -- present since the Store module existed with zero "
            "callers anywhere -- now extends brain.reason's graph_expand stage beyond what the in-memory "
            "ephemeral graph alone can reach, when the caller opts in (expand_via_store_graph=True) and the "
            "connector is a Store with a persisted graph. Every other caller (flag omitted, or no persisted "
            "graph) takes the exact same path as before this wiring existed."
            if all_correct else
            "At least one case did not behave as expected -- see metrics for exactly which."
        )
        run.finish(
            title="Store.expand_entity wired into graph_expand, opt-in via expand_via_store_graph=, merged with the existing in-memory expansion",
            goal="Close the gap: graph_expand's in-memory graph is rebuilt fresh from whatever passages are already in hand every call, so it can never reach an entity hop beyond that -- Store.expand_entity walks a graph persisted over the WHOLE collection instead, and had zero callers anywhere.",
            method="connector_top_k=0 isolates the graph-only path (no generic search contribution) so any passage reached beyond the one directly given can only come from entity-graph expansion. Checked with the flag omitted (in-memory only, G2 unreached), enabled (G2 reached via the persisted Store graph), and enabled against a Store with no persisted graph at all (correct no-op, not an error).",
            metrics=metrics,
            results_prose=prose,
            conclusion=conclusion,
            scale_down="One entity, one hop, two passages -- a proof the merge/dispatch/citation wiring works end to end, not a benchmark of graph_index.expand_from_entity's own multi-hop precision at a larger real graph (already exercised in EXP-075).",
            referenced_files=FILES,
            follow_ups=[],
            models_used="None -- graph traversal and lexical span extraction, both deterministic.",
        )
        print("off_correct:", off_correct, "on_correct:", on_correct, "no_graph_correct:", no_graph_correct)
        print("ALL CORRECT:", all_correct)
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
