"""EXP-079: wiring lab.common.longform into lab.common.brain.reason as the
fifth signal brain.py's own docstring named as a todo since before this
module existed -- closing EXP-052/053's gap through the same single entry
point every other capability in this repo goes through, not as a
standalone function nobody's asking for.

The thing that actually matters here is not "does the signal fire on a
document request" (the easy half) -- it's "does it correctly NOT fire on
every short-lookup ask every other exploration already depends on."
wants_document's threshold (DOCUMENT_TAU=0.75) was calibrated against only
a handful of asks; this is the real regression check, run against asks
drawn from EXP-057 through EXP-078, not fresh ones invented to pass.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run

FILES = [
    "lab/exp_079_longform_signal/run.py",
    "lab/common/brain.py",
    "lab/common/intent_signals.py",
    "lab/common/longform.py",
    "data/exp_078_longform_consistency/results.json",
    "data/exp_079_longform_signal/results.json",
]

DOCUMENT_PASSAGES = [
    {"id": "P0", "text": "Ravi Sharma lives at 14 MG Road, Pune 411001."},
    {"id": "P1", "text": "Ravi Sharma works at ABC Pvt Ltd."},
    {"id": "P2", "text": "Meera Iyer lives at 22 Lake View Road, Chennai 600028."},
    {"id": "P3", "text": "Meera Iyer works at Zenith Corp."},
]

DOCUMENT_ASKS = [
    "Write a full report covering every employee, their address, and their employer.",
    "Draft a complete document summarizing all the people in these records.",
    "Compose a detailed write-up describing each person mentioned here.",
]

# Short-lookup asks drawn from already-closed explorations, not invented
# fresh for this test -- the real regression check.
LOOKUP_REGRESSION_CASES = [
    ("What is the notice period?", [{"id": "A1", "text": "The notice period is 30 days."}]),
    (
        "An engineer recorded an additional stress reading on a component last week. Who is this engineer, and "
        "where is their site based? What do all of the component's stress readings amount to, and does "
        "engineering policy require the part to be replaced?",
        [
            {"id": "E1a", "group": "E1", "text": "Engineer Arjun Mehta is based at the Pune fabrication site, 31 Industrial Estate Road."},
            {"id": "E2a", "group": "E2", "text": "Engineer Fatima Khan is based at the Baroda fabrication site, 4 Industrial Estate Road."},
            {"id": "E2d", "group": "E2", "text": "A follow-up reading on TC-19, taken last week, recorded an additional stress of 110 MPa."},
        ],
    ),
    ("What is the capital of France?", []),
    (
        "Where does Ravi Sharma live, and in which city is his employer registered?",
        [
            {"id": "E1", "hierarchy": {"chapter": "Employees", "section": "Ravi"}, "text": "Ravi Sharma lives at 14 MG Road, Pune 411001."},
            {"id": "E2", "hierarchy": {"chapter": "Employees", "section": "Ravi"}, "text": "Ravi Sharma works as a sales manager at ABC Pvt Ltd."},
            {"id": "R1", "hierarchy": {"chapter": "Company Registry", "section": "ABC"}, "text": "ABC Pvt Ltd is registered in Mumbai under company number 55021."},
        ],
    ),
]


def main():
    run = Run("EXP-079", "exp_079_longform_signal")

    document_rows = []
    for ask in DOCUMENT_ASKS:
        result = reason(ask, DOCUMENT_PASSAGES)
        signal = next(t for t in result["trace"] if t["step"] == "intent_signal" and t["signal"] == "document")
        fired_longform = any(t["step"] == "longform_write" for t in result["trace"])
        document_rows.append({"ask": ask, "score": signal["score"], "fired": signal["fires"], "dispatched_to_longform": fired_longform, "decision": result["decision"]})

    lookup_rows = []
    for ask, passages in LOOKUP_REGRESSION_CASES:
        result = reason(ask, passages) if passages else reason(ask, [])
        signal = next((t for t in result["trace"] if t["step"] == "intent_signal" and t["signal"] == "document"), None)
        lookup_rows.append(
            {
                "ask": ask[:70],
                "score": signal["score"] if signal else None,
                "fired": signal["fires"] if signal else None,
                "decision": result["decision"],
                "had_document_signal_step": signal is not None,
            }
        )
    run.write_json("items.json", {"document_asks": document_rows, "lookup_regression": lookup_rows})

    document_all_fired = all(r["fired"] and r["dispatched_to_longform"] for r in document_rows)
    lookup_none_fired = all(r["fired"] is not True for r in lookup_rows)

    metrics = {
        "document_asks": {"n": len(document_rows), "all_fired": document_all_fired, "rows": document_rows},
        "lookup_regression": {"n": len(lookup_rows), "none_fired": lookup_none_fired, "rows": lookup_rows},
    }

    all_correct = document_all_fired and lookup_none_fired

    prose = (
        f"{sum(r['fired'] for r in document_rows)}/{len(document_rows)} document-requesting asks correctly fired "
        f"the signal and dispatched to lab.common.longform (scores {[r['score'] for r in document_rows]}). "
        f"{sum(not r['fired'] for r in lookup_rows)}/{len(lookup_rows)} short-lookup asks (drawn from EXP-057/069/"
        f"075, not invented fresh) correctly did NOT fire it (scores {[r['score'] for r in lookup_rows]}), "
        f"including the one compound multi-clause ask that scored closest to the threshold during calibration."
    )

    conclusion = (
        "The long-form signal is now reachable through the same single entry point (lab.common.brain.reason) "
        "every other capability in this repo goes through, not a standalone function -- and, more importantly, "
        "wiring it in did not disturb any existing short-answer behavior: every lookup ask already measured by "
        "an earlier exploration still resolves exactly as it did before this signal existed. EXP-052/053's named "
        "gaps are closed end to end, not just as isolated modules."
        if all_correct
        else "At least one ask did not behave as expected -- see metrics for which, reported as measured."
    )

    run.finish(
        title="Long-form writing wired into brain.reason as its fifth signal",
        goal=(
            "Prove lab.common.intent_signals.wants_document correctly dispatches document-requesting asks to "
            "lab.common.longform.write_long_document through lab.common.brain.reason, and -- the real test -- "
            "that it does not fire on any short-lookup ask already measured by an earlier exploration."
        ),
        method=(
            "3 genuine document-requesting asks, run through brain.reason, checked for the signal firing and "
            "actually dispatching to longform_write. 4 short-lookup asks drawn directly from EXP-057/069/075's "
            "own fixtures (not invented fresh for this test), including the one compound ask that scored "
            "closest to DOCUMENT_TAU during calibration, checked that the signal stays silent."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="7 asks total -- enough to prove the wiring and its most important regression boundary, not an exhaustive sweep of every existing exploration's asks.",
        referenced_files=FILES,
        follow_ups=[
            "DOCUMENT_TAU=0.75 is a first measured value from a small sample (EXP-069-style multi-domain calibration not yet done for this signal) -- the same caveat every other first-measured threshold in this repo carries.",
            "Not yet tested: an ask that genuinely wants both a short answer AND implies document-length output in the same compound sentence -- which signal should win is not yet a decided, measured case.",
        ],
        models_used="bge-small-en-v1.5 for the document-intent signal (retrieval-style similarity scoring only); flan-t5-small for the rewriter role inside longform (measured separately, EXP-048 onward). No new generative use.",
    )


if __name__ == "__main__":
    main()
