"""EXP-078: long-form writing with an ask-derived outline (EXP-052) and
cross-page consistency checking (EXP-053) -- the two named gaps that sat
between "the architecture scales" (EXP-018, deterministic path, 42,506
words) and "the generative rewriter scales" (EXP-077, real degradation at
80 leaves, never checked for cross-page contradiction before this).

Two cases, built to need each piece specifically:
  1. A clean multi-page document (6 leaves, 3 real sections implied by
     the ask) -- proves the ask-derived section titles are real, and
     that writing many consistent pages produces zero false-positive
     consistency flags.
  2. The identical outline, except one later page deliberately restates
     an earlier page's fact about the same person with a different
     value (the same address-conflict shape lab.common.working_memory
     was built and debugged against) -- proves the flag actually fires,
     not just that it stays quiet when nothing is wrong.

Uses flan-t5-small (checkpoint="flan-t5-small", EXP-048's already-measured
~38% raw fidelity pass rate at this leaf size) through
lab.common.rewriter_backends, not a stubbed deterministic-only path --
real generation on real leaves, falling back per-leaf exactly the way
every other rewriter exploration already does on a fidelity-gate failure.
Deliberately few leaves (6-7, not EXP-077's 80), so this isolates the two
new mechanisms under test -- ask-derived titling and cross-page
consistency -- from the scale question EXP-077 already measured
separately.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.assemble import citation_integrity, coverage_report
from lab.common.harness import Run
from lab.common.longform import write_long_document

FILES = [
    "lab/exp_078_longform_consistency/run.py",
    "lab/common/longform.py",
    "lab/common/working_memory.py",
    "lab/common/rules.py",
    "lab/common/rewriter_backends.py",
    "data/exp_018_longform/results.json",
    "data/exp_077_generation_at_scale/results.json",
    "data/exp_078_longform_consistency/results.json",
]

ASK = "Where does each employee live, where do they work, and when did they sign?"

# Ravi gets 6 findings deliberately -- lab.common.longform's
# MAX_FINDINGS_PER_ENTITY_LEAF (4) splits him across two leaves/pages,
# which is the only way his own later finding can land on a genuinely
# different "page" from his first one for the cross-page check to have
# anything to compare. A first version of this fixture gave Ravi only 2
# findings; once the outline grouped by entity (the EXP-078 fix for the
# mismatched-title bug), both of his findings merged into one leaf and
# the conflict case stopped being a *cross-page* conflict at all.
CLEAN_FINDINGS = [
    {"finding_id": "F0", "statement": "Ravi Sharma lives at 14 MG Road, Pune 411001.", "citation": "C0"},
    {"finding_id": "F1", "statement": "Ravi Sharma works at ABC Pvt Ltd.", "citation": "C1"},
    {"finding_id": "F2", "statement": "Ravi Sharma signed on 5 January 2024.", "citation": "C2"},
    {"finding_id": "F3", "statement": "Ravi Sharma reports to Deepak Verma.", "citation": "C3"},
    {"finding_id": "F4", "statement": "Meera Iyer lives at 22 Lake View Road, Chennai 600028.", "citation": "C4"},
    {"finding_id": "F5", "statement": "Meera Iyer works at Zenith Corp.", "citation": "C5"},
    {"finding_id": "F6", "statement": "Priya Nair lives at 9 Residency Road, Bengaluru 560001.", "citation": "C6"},
    {"finding_id": "F7", "statement": "Priya Nair works at Globex Inc.", "citation": "C7"},
]

# Identical to CLEAN_FINDINGS, plus a 5th Ravi finding -- landing in
# Ravi's *second* leaf ("Ravi Sharma (2)") since his first 4 already
# filled leaf one -- that restates his address from F0 with a different
# value: the exact conflict shape to prove the flag fires, now a genuine
# cross-page case again.
CONFLICTING_FINDINGS = CLEAN_FINDINGS + [
    {"finding_id": "F8", "statement": "Ravi Sharma lives at 88 New Colony Road, Nagpur 440001.", "citation": "C8"},
]


def run_case(findings: list[dict], label: str) -> dict:
    result = write_long_document(ASK, findings, checkpoint="flan-t5-small", task="lookup")
    coverage = coverage_report(findings, result["document"])
    valid_ids = {f["citation"] for f in findings}
    citations = citation_integrity(result["document"], valid_ids)
    return {
        "label": label,
        "document": result["document"],
        "consistency_flags": result["consistency_flags"],
        "coverage": coverage["coverage"],
        "missing": coverage["missing"],
        "broken_citations": citations["broken"],
        "working_memory_pages": len(result["working_memory"]["pages"]),
    }


def main():
    run = Run("EXP-078", "exp_078_longform_consistency")

    clean = run_case(CLEAN_FINDINGS, "clean")
    conflicting = run_case(CONFLICTING_FINDINGS, "conflicting")
    run.write_json("items.json", {"clean": clean, "conflicting": conflicting})

    clean_correct = len(clean["consistency_flags"]) == 0 and clean["coverage"] == 1.0 and not clean["broken_citations"]
    conflict_detected = any(f["subject"] == "Ravi Sharma" and f["verb_lemma"] == "live" for f in conflicting["consistency_flags"])

    metrics = {
        "clean_case": {"consistency_flags": len(clean["consistency_flags"]), "coverage": clean["coverage"], "broken_citations": len(clean["broken_citations"]), "correct": clean_correct},
        "conflicting_case": {"consistency_flags": conflicting["consistency_flags"], "flag_fired": conflict_detected},
        "document_sample": clean["document"][:400],
    }

    all_correct = clean_correct and conflict_detected

    prose = (
        f"Clean 6-leaf document: {len(clean['consistency_flags'])} consistency flag(s) (expect 0), coverage "
        f"{clean['coverage']}, {len(clean['broken_citations'])} broken citation(s). Conflicting 7-leaf document "
        f"(identical, plus a later page restating Ravi Sharma's address with a different value): "
        f"{len(conflicting['consistency_flags'])} flag(s) -- {'the address conflict was caught' if conflict_detected else 'the address conflict was NOT caught'}: "
        f"{conflicting['consistency_flags']}."
    )

    conclusion = (
        "Both mechanisms work as intended: a genuinely consistent multi-page document produces zero false-"
        "positive flags, and a deliberately injected later-page contradiction about the same person and the "
        "same fact (address) is caught, naming exactly which earlier page it conflicts with and what the two "
        "values were -- not just 'something is wrong somewhere'. This closes EXP-053's gap directly: a check "
        "that previously did not exist at all for long-form writing, built on lab.common.working_memory's "
        "bounded 'RAM' (subject-verb-object triples only, never full page text kept once a page is behind it)."
        if all_correct
        else "At least one case did not behave as expected -- see metrics.conflicting_case for the exact flags "
        "produced, reported as measured rather than assumed to work."
    )

    run.finish(
        title="Long-form writing with cross-page consistency checking",
        goal=(
            "Prove lab.common.longform.write_long_document (EXP-052's ask-derived section titling, wired onto "
            "the existing deterministic outline/rewriter/document-writer pieces) produces a real multi-page "
            "document, and that lab.common.working_memory's cross-page consistency check (EXP-053) both stays "
            "silent on a genuinely consistent document and fires on a deliberately injected contradiction, "
            "naming the specific conflicting pages and values."
        ),
        method=(
            "Two 6-7 leaf documents from the same ask: one internally consistent, one identical except a later "
            "page restates an earlier page's fact about the same person with a different value. Both run "
            "through lab.common.longform.write_long_document end to end, checked for coverage, citation "
            "integrity, and the consistency flags lab.common.working_memory actually produced."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="6-7 leaves, one deliberately injected conflict -- a proof the mechanism works and stays quiet when it should, not a scale test (EXP-077 already measured generative fidelity at 80 leaves; this is a different mechanism, checked separately).",
        referenced_files=FILES,
        follow_ups=[
            "Not yet combined with EXP-077's scale (80 leaves): this exploration uses 6-7 leaves, enough to prove both mechanisms, not enough to also re-measure generative fidelity degradation -- a combined run (EXP-077's scale, with cross-page consistency checking turned on) is a natural next step.",
            "extract_fact_triple's prepositional-object fallback (this exploration's prerequisite fix) still misses some constructions -- a compound date ('5 January 2024') extracted as just '5' in one spot-check -- worth a dedicated pass if dates become a consistency-check target, not just addresses/employers.",
            "Not yet wired into lab.common.brain.reason as a signal -- this module is callable standalone, not yet reachable through the same entry point every other capability in this repo goes through.",
        ],
        models_used="flan-t5-small via lab.common.rewriter_backends (rewriter role only, fidelity-gated, falling back to deterministic text per leaf on any failure, exactly as EXP-048 measured) -- the pipeline is model-agnostic (EXP-076) and works with any registered checkpoint.",
    )


if __name__ == "__main__":
    main()
