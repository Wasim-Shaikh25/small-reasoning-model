"""EXP-110: lab.common.doc_tools.select_tool/select_template, wired into
brain.reason's document_write stage as an opt-in auto-selector.

template_id= already let a caller NAME a registered lab.common.doc_tools
template (2026-11-10) -- but omitting it always fell back to plain
entity-grouping, since nothing ever picked one FOR the caller.
select_tool/select_template (EXP-082's own entry point, moved to
lab.tests.support as test-only, moved back once this wiring existed) use
the SAME bge-similarity match assign_findings_to_sections already uses
to route findings within a chosen template -- applied here one level up,
to choose the template itself from the ask.

auto_select_template=False by default: a caller who already names a
template explicitly is completely unaffected: effective_template_id only
ever differs from the caller's own template_id when template_id was left
None AND auto_select_template=True.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run

FILES = [
    "lab/tests/exp_110_auto_select_template_wiring/run.py",
    "lab/common/brain.py",
    "lab/common/doc_tools.py",
    "lab/common/longform.py",
    "lab/common/templates/legal/_tool.json",
    "lab/common/templates/legal/legal_notice.json",
    "data/exp_110_auto_select_template_wiring/results.json",
]

ASK = "Draft a complete legal notice document summarizing all the unpaid rent findings."
PASSAGES = [
    {"id": "1", "text": "The tenant has not paid rent for three months, totaling Rs. 45,000."},
    {"id": "2", "text": "The landlord demands payment within 15 days of this notice."},
]


def main() -> None:
    run = Run("EXP-110", "exp_110_auto_select_template_wiring")

    off = reason(ASK, PASSAGES)
    on = reason(ASK, PASSAGES, auto_select_template=True)
    explicit = reason(ASK, PASSAGES, auto_select_template=True, template_id="legal_notice")

    auto_step = next((t for t in on["trace"] if t.get("step") == "auto_select_template"), None)
    off_has_auto_step = any(t.get("step") == "auto_select_template" for t in off["trace"])
    explicit_has_auto_step = any(t.get("step") == "auto_select_template" for t in explicit["trace"])

    off_correct = off["decision"] in ("supported", "supported_with_flags") and not off_has_auto_step
    on_correct = (
        on["decision"] in ("supported", "supported_with_flags")
        and auto_step is not None
        and auto_step["tool"] == "legal"
        and auto_step["template_id"] == "legal_notice"
    )
    explicit_correct = explicit["decision"] in ("supported", "supported_with_flags") and not explicit_has_auto_step

    metrics = {
        "auto_select_omitted_baseline": {"decision": off["decision"], "auto_select_fired": off_has_auto_step, "correct": off_correct},
        "auto_select_enabled": {
            "decision": on["decision"],
            "tool_selected": auto_step["tool"] if auto_step else None,
            "template_selected": auto_step["template_id"] if auto_step else None,
            "score": auto_step["score"] if auto_step else None,
            "correct": on_correct,
        },
        "explicit_template_id_takes_precedence": {"decision": explicit["decision"], "auto_select_fired": explicit_has_auto_step, "correct": explicit_correct},
    }
    run.write_json("items.json", metrics)
    all_correct = off_correct and on_correct and explicit_correct

    prose = (
        f"auto_select_template omitted (default): {off['decision']!r}, no auto_select_template trace step -- "
        f"today's exact behavior (outline from entity-grouping, no template). Enabled: {on['decision']!r}, "
        f"auto-selected tool={auto_step['tool']!r} template_id={auto_step['template_id']!r} "
        f"(score={auto_step['score']}) from the ask alone, no template named by the caller. Enabled BUT with "
        f"an explicit template_id also given: {explicit['decision']!r}, zero auto_select_template step -- the "
        f"caller's own explicit choice is never overridden."
    )
    conclusion = (
        "lab.common.doc_tools.select_tool/select_template -- EXP-082's own standalone entry point, never "
        "reachable from brain.reason -- now auto-selects a registered template for the document_write stage "
        "when the caller opts in (auto_select_template=True) and leaves template_id at its default. A caller "
        "who already names a template, or leaves the new flag at its default False, is completely unaffected."
        if all_correct else
        "At least one case did not behave as expected -- see metrics for exactly which."
    )
    run.finish(
        title="select_tool/select_template wired into document_write as an opt-in auto-selector for template_id",
        goal="Close the gap: template_id already lets a caller name a template, but nothing ever picked one FOR the caller from the ask itself.",
        method="A legal-notice-shaped ask run three ways: the new flag omitted (baseline, unaffected), enabled with no explicit template (auto-selects legal_notice), and enabled alongside an explicit template_id (the caller's own choice still wins, no auto-select step fires).",
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="Two registered templates (legal, study, per EXP-082's own registry), one ask -- a proof the dispatch/precedence wiring works end to end, not a benchmark of select_tool/select_template's own matching accuracy at a larger template catalog (already measured in EXP-082).",
        referenced_files=FILES,
        follow_ups=[
            "No minimum-score floor: a low-confidence match still gets auto-selected rather than falling back to entity-grouping. EXP-082 itself never needed one (its own fixture always had a real match); a caller relying on auto_select_template for an ask that matches no registered template well would get a weak pick instead of the old entity-grouping fallback.",
        ],
        models_used="lab.common.real_encoders.bge_embed (bge cosine similarity) -- same mechanism select_tool/select_template already used in EXP-082, unchanged.",
    )
    print("off_correct:", off_correct, "on_correct:", on_correct, "explicit_correct:", explicit_correct)
    print("ALL CORRECT:", all_correct)


if __name__ == "__main__":
    main()
