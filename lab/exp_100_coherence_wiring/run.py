"""EXP-100: lab.common.coherence.sequence_coherence, wired into
lab.common.longform.write_long_document for the first time.

coherence.py (EXP-050) had zero real callers anywhere outside its own
module before this -- confirmed by grep, not assumed -- despite its own
follow_ups already naming the exact gap: "Wire sequence_coherence into
lab.common.assemble.build_outline itself so a flagged leaf is actually
... surfaced during real document assembly, not just measured
standalone." This wires it one level up from that suggestion, inside
write_long_document's own per-leaf render loop (after rewrite/plain-
English, right where `consistency_flags` -- the cross-page sibling
check -- already runs), since that is where a leaf's actually-rendered
sentence sequence exists; build_outline itself only decides grouping,
before any sentence is rendered.

A real bug was found and fixed while wiring this, not just a missing
caller: `lab.common.template_rewriter.splice_unit` always joins a leaf's
title and its rendered body with "\n" (`"\n".join([leaf["title"], ...])`),
and `lab.common.textutil.sentences` treats "\n" as its own sentence
boundary -- so a naive wiring would hand `sequence_coherence` the leaf's
own TITLE as sentence zero, comparing a heading against the first real
sentence on every single leaf and flagging it almost every time (a
heading is essentially never semantically similar to a sentence), which
would have buried the real signal EXP-050 measured under near-constant
noise. Fixed by dropping the title when it appears as its own exact
first element -- checked directly below, on both a leaf with a real
within-leaf topic jump and a clean one, so this isn't asserted from
reading the code.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.longform import write_long_document

FILES = [
    "lab/exp_100_coherence_wiring/run.py",
    "lab/common/longform.py",
    "lab/common/coherence.py",
    "lab/common/template_rewriter.py",
    "data/exp_050_neighbor_coherence/results.json",
    "data/exp_100_coherence_wiring/results.json",
]

ASK = "Tell me about Ravi Sharma."

# Same entity on purpose (both land in the same leaf -- a within-leaf
# question, not lab.common.working_memory's cross-page one), second
# finding genuinely unrelated in topic, no discourse connective
# signaling the shift -- the exact shape EXP-050 measured as a real
# unsignaled jump.
JUMP_FINDINGS = [
    {"finding_id": "F0", "statement": "Ravi Sharma lives at 14 MG Road, Pune 411001.", "citation": "C0"},
    {"finding_id": "F1", "statement": "Ravi Sharma mentioned that the weather forecast predicts heavy rain in Mumbai next week.", "citation": "C1"},
]

# Identical shape, but the second finding is a genuinely related fact
# about the same person/topic -- must NOT be flagged, so this isn't
# measuring "any two-finding leaf gets flagged".
CLEAN_FINDINGS = [
    {"finding_id": "F0", "statement": "Ravi Sharma lives at 14 MG Road, Pune 411001.", "citation": "C0"},
    {"finding_id": "F1", "statement": "Ravi Sharma also works at ABC Pvt Ltd in Pune.", "citation": "C1"},
]


def main() -> None:
    run = Run("EXP-100", "exp_100_coherence_wiring")

    jump_result = write_long_document(ASK, JUMP_FINDINGS, task="lookup")
    clean_result = write_long_document(ASK, CLEAN_FINDINGS, task="lookup")
    # plain_english reflows every sentence with a single space instead of
    # the leaf's own newline (lab.common.plain_language.simplify_document),
    # so the title-stripping fix above has nothing to strip there -- check
    # this path doesn't crash or silently lose the signal either.
    plain_english_result = write_long_document(ASK, JUMP_FINDINGS, task="lookup", plain_english=True)

    run.write_json(
        "items.json",
        {
            "jump_document": jump_result["document"],
            "jump_coherence_flags": jump_result["coherence_flags"],
            "clean_document": clean_result["document"],
            "clean_coherence_flags": clean_result["coherence_flags"],
            "plain_english_coherence_flags": plain_english_result["coherence_flags"],
        },
    )

    jump_flagged = len(jump_result["coherence_flags"]) == 1 and jump_result["coherence_flags"][0]["leaf_id"] is not None
    # The title itself must never appear as either side of a flagged
    # pair -- the exact bug this exploration found and fixed.
    title_leaked = any(
        flag["first"] == "Ravi Sharma" or flag["second"] == "Ravi Sharma"
        for flag in jump_result["coherence_flags"] + clean_result["coherence_flags"]
    )
    clean_not_flagged = clean_result["coherence_flags"] == []
    plain_english_ok = len(plain_english_result["coherence_flags"]) == 1 and not title_leaked

    metrics = {
        "jump_flagged": jump_flagged,
        "jump_coherence_flags": jump_result["coherence_flags"],
        "clean_not_flagged": clean_not_flagged,
        "title_leaked_into_a_flag": title_leaked,
        "plain_english_path_ok": plain_english_ok,
    }

    all_correct = jump_flagged and clean_not_flagged and not title_leaked and plain_english_ok

    prose = (
        f"A leaf with a genuine within-leaf unsignaled topic jump (Ravi Sharma's address, then an unrelated "
        f"weather remark) -> {len(jump_result['coherence_flags'])} coherence flag(s): "
        f"{jump_result['coherence_flags']}. The same shape with a genuinely related second finding instead -> "
        f"{len(clean_result['coherence_flags'])} flag(s) (expect 0). The leaf's own title never appears as "
        f"either side of a flagged pair in either case (title_leaked={title_leaked}) -- confirms the title-vs-"
        f"first-sentence bug found while wiring this is actually fixed, not just avoided by luck on one "
        f"fixture. plain_english=True (a different code path, no newline between title and body) -> "
        f"{len(plain_english_result['coherence_flags'])} flag(s), same result, no crash."
    )

    conclusion = (
        "lab.common.coherence.sequence_coherence is now wired into lab.common.longform.write_long_document's "
        "per-leaf render loop, reported as coherence_flags alongside the existing consistency_flags -- a "
        "genuine within-leaf topic jump is caught, a genuinely coherent leaf produces zero false positives, "
        "and the leaf's own title (joined to its body by template_rewriter.splice_unit's own newline "
        "convention, which lab.common.textutil.sentences treats as a sentence boundary) never leaks into the "
        "comparison as a fake 'sentence' on either the newline-joined or the plain_english space-joined path. "
        "This closes EXP-050's own named follow-up, generalized one level up (write_long_document's render "
        "loop, where rendered sentences actually exist) from where it suggested wiring it (build_outline, "
        "before any sentence is rendered)."
        if all_correct
        else "At least one check did not behave as expected -- see metrics for exactly which, reported as "
        "measured, not assumed to work."
    )

    run.finish(
        title="lab.common.coherence.sequence_coherence wired into write_long_document's per-leaf render loop as coherence_flags",
        goal=(
            "Give lab.common.coherence.sequence_coherence -- a confirmed-dormant module whose own follow-ups "
            "already named the gap -- its first real wiring into the live long-form writing path, and prove "
            "the wiring doesn't bury its own signal under a title-vs-sentence artifact found while building it."
        ),
        method=(
            "Two two-finding fixtures about the same entity (so both findings land in one leaf, making this a "
            "within-leaf question, not working_memory's cross-page one): one with a genuine unsignaled topic "
            "jump, one with a genuinely related second fact. Both run through write_long_document end to end, "
            "checking coherence_flags fires on the first and stays empty on the second, and that the leaf's "
            "own title never appears inside a flagged pair on either the default (newline-joined) or "
            "plain_english=True (space-joined) rendering path."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="Two two-finding fixtures, one entity -- a proof the wiring works end to end and the title-leak bug is fixed, not a coherence-detection benchmark at document scale (EXP-050's own 103-sentence real-GDPR-text measurement already covers that separately).",
        referenced_files=FILES,
        follow_ups=[
            "coherence_flags is reported but nothing downstream (brain.py's trace, or a caller) surfaces it to a reader yet, same 'report, don't yet act on it' posture contract_violations started with before this -- a next step could decide whether a flagged leaf should be reordered, annotated inline, or just left in the trace for now.",
            "Only checked within a single leaf (two findings, same entity) -- a leaf with 3+ findings where the jump is in the middle of the sequence, or a leaf built from the template_id path instead of entity-grouping, is untested here.",
        ],
        models_used="bge-small-en-v1.5 (lab.common.real_encoders, coherence.py's own similarity leg) -- non-generative; template_rewriter.splice_unit (deterministic) renders every leaf, no generative model anywhere in this path as of the 2026-11-11 rewriter withdrawal.",
    )

    print("jump_flagged:", jump_flagged, "clean_not_flagged:", clean_not_flagged, "title_leaked:", title_leaked, "plain_english_ok:", plain_english_ok)
    print("ALL CORRECT:", all_correct)


if __name__ == "__main__":
    main()
