"""EXP-072: the no-context fallback (FORBIDDEN.md's narrow exception,
2026-10-16) -- answering from the bounded checkpoint's own knowledge only
when brain.reason gets literally zero passages, never when retrieval ran
and came up empty.

The critical thing this measures is not "can the model answer a general
question" -- it's the boundary: does a real retrieval-miss (passages given,
none of them relevant) still abstain exactly as before, completely
unaffected by this new branch? If that boundary leaked even slightly, this
exception would quietly become a way to dodge abstention whenever
retrieval struggles, which is exactly what FORBIDDEN.md's "No facts from
background alone" rule exists to prevent.

Three regimes:
  1. Zero passages (`[]`) -- the new path. Must return decision="ungrounded",
     a visible disclaimer, and never a bracketed citation marker (there is
     nothing to cite).
  2. Passages given, none relevant to the ask (a real retrieval miss) --
     must still return decision="inconclusive", ABSTAIN_TEXT, completely
     unchanged from before this branch existed.
  3. Passages given, genuinely relevant -- the existing evidence-grounded
     path, run as a regression check that the new branch didn't disturb it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run
from lab.common.verify import citation_markers

FILES = [
    "lab/tests/exp_072_no_context_fallback/run.py",
    "lab/common/open_domain.py",
    "lab/common/brain.py",
    "lab/common/prompt_contract.py",
    "FORBIDDEN.md",
    "data/exp_072_no_context_fallback/results.json",
]

NO_CONTEXT_ASKS = [
    "What is the capital of France?",
    "What is the boiling point of water in Celsius?",
    "Who wrote the play Romeo and Juliet?",
]

RETRIEVAL_MISS_PASSAGES = [
    {"id": "A1", "text": "The notice period is 30 days."},
    {"id": "A2", "text": "The security deposit is INR 50000."},
]
RETRIEVAL_MISS_ASK = "What is the capital of France?"

GENUINE_PASSAGES = [
    {"id": "B1", "text": "The notice period is 30 days."},
    {"id": "B2", "text": "The security deposit is INR 50000."},
]
GENUINE_ASK = "What is the notice period?"


def run_no_context_case(ask: str) -> dict:
    result = reason(ask, [])
    markers = citation_markers(result["text"])
    return {
        "ask": ask,
        "decision": result["decision"],
        "text": result["text"],
        "has_disclaimer": result["text"].startswith("[Not grounded"),
        "has_fabricated_citation": bool(markers),
        "correct": result["decision"] == "ungrounded" and result["text"].startswith("[Not grounded") and not markers,
    }


def run_retrieval_miss_case() -> dict:
    result = reason(RETRIEVAL_MISS_ASK, RETRIEVAL_MISS_PASSAGES)
    return {
        "ask": RETRIEVAL_MISS_ASK,
        "decision": result["decision"],
        "text": result["text"],
        "correct": result["decision"] == "inconclusive" and result["text"] == "Insufficient evidence.",
    }


def run_genuine_case() -> dict:
    result = reason(GENUINE_ASK, GENUINE_PASSAGES)
    return {
        "ask": GENUINE_ASK,
        "decision": result["decision"],
        "text": result["text"],
        "correct": result["decision"] == "supported" and "30 days" in result["text"],
    }


def main():
    run = Run("EXP-072", "exp_072_no_context_fallback")

    no_context_rows = [run_no_context_case(ask) for ask in NO_CONTEXT_ASKS]
    retrieval_miss_row = run_retrieval_miss_case()
    genuine_row = run_genuine_case()
    run.write_json(
        "items.json",
        {"no_context": no_context_rows, "retrieval_miss": retrieval_miss_row, "genuine": genuine_row},
    )

    no_context_correct = sum(r["correct"] for r in no_context_rows)
    metrics = {
        "no_context": {"n": len(no_context_rows), "correct": no_context_correct, "cases": no_context_rows},
        "retrieval_miss_still_abstains": retrieval_miss_row["correct"],
        "genuine_case_unaffected": genuine_row["correct"],
    }

    all_correct = no_context_correct == len(no_context_rows) and retrieval_miss_row["correct"] and genuine_row["correct"]

    prose = (
        f"No-context fallback: {no_context_correct}/{len(no_context_rows)} asks correctly answered with decision="
        f"'ungrounded', the fixed disclaimer, and no fabricated citation marker. The boundary check: a real "
        f"retrieval miss (passages given, none relevant) {'still correctly abstains' if retrieval_miss_row['correct'] else 'INCORRECTLY changed behavior'} "
        f"(decision={retrieval_miss_row['decision']!r}). The existing evidence-grounded path "
        f"{'is unaffected' if genuine_row['correct'] else 'REGRESSED'} (decision={genuine_row['decision']!r}, text={genuine_row['text']!r})."
    )

    conclusion = (
        (
            "The no-context fallback works and, critically, stays exactly where FORBIDDEN.md's exception draws "
            "the line: a genuinely empty passages list gets an explicitly disclaimed, ungrounded answer, while "
            "a real retrieval miss -- passages were given, just none of them relevant -- still abstains exactly "
            "as it did before this branch existed. The two cases are structurally distinguished (checked before "
            "any retrieval runs, not by a confidence score), so there is no way for a struggling retrieval to "
            "slide into the ungrounded path and dodge abstention."
            if all_correct
            else "At least one check failed -- see metrics for which. This is reported as found, not smoothed "
            "over: if the boundary between 'no context' and 'retrieval miss' leaked at all, that is a direct "
            "violation of FORBIDDEN.md's 'No facts from background alone' rule and must be fixed before this "
            "exception is trusted further."
        )
    )

    run.finish(
        title="The no-context fallback, and the boundary that keeps it from swallowing real abstention",
        goal=(
            "Prove lab.common.open_domain's no-context fallback (FORBIDDEN.md, 2026-10-16) answers correctly "
            "and visibly-disclaimed when passages is genuinely empty, and -- the more important check -- that "
            "a real retrieval miss (passages given, none relevant) is completely unaffected and still abstains "
            "the original way."
        ),
        method=(
            "3 genuinely-no-context asks through brain.reason(ask, []), checked for decision=='ungrounded', "
            "the fixed disclaimer prefix, and no fabricated citation marker. 1 retrieval-miss case (passages "
            "given, ask about something not in them) checked against the unchanged pre-existing abstain "
            "behavior. 1 genuine evidence-grounded case as a regression check on the existing path."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="3 no-context asks, 1 retrieval-miss case, 1 genuine case -- enough to prove the mechanism and its boundary, not a broad open-domain QA benchmark.",
        referenced_files=FILES,
        follow_ups=[
            "Only gemma3:270m via Ollama tested for this role; flan-t5-small (also permitted by the exception) not yet measured here.",
            "The citation-marker rejection has only been exercised when the model happens not to fabricate one; a case that reliably provokes a fabricated marker (to prove the rejection actually fires) has not been constructed.",
        ],
        models_used="gemma3:270m via Ollama, in the new no-context role (FORBIDDEN.md 2026-10-16) -- not the rewriter role, a third, separate, narrowly-scoped generative use.",
    )


if __name__ == "__main__":
    main()
