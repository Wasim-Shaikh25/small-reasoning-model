"""EXP-105: lab.common.concept_tools (the teach-tool concept registry),
wired into lab.common.brain.reason as a dispatch checked ahead of
plan_stages, closing the gap its own original exploration left open:
"nothing here is wired into brain.reason ... it is a new, separate entry
point (lab.common.engine.run), not a replacement for the existing
pipeline."

Asked directly why it wasn't connected, given it answers through the
project's one stated single controller: `match_concept(ask, concepts)`
(concepts=None reads whatever is registered on disk under
lab/common/concepts/ -- empty by default, exactly like `lab.common.
engine.run` already does) is checked right before stage-planning. A
match (exact alias, or embedding above CONCEPT_TAU) dispatches straight
to `teach_and_run`, bypassing the ask-driven lookup/rule/document stages
below entirely -- the same "an explicit, more specific signal wins"
precedent `document_write`'s own intent signal already set. No match
(every ask today, since the shipped registry ships empty) falls straight
through to the completely normal pipeline, unchanged.

This exploration proves: a real taught concept (the shipped
`timeline.yaml` example) answers correctly through the real `reason()`
entry point, with citations derived from the concept result's own
`passage_id` fields; an ordinary lookup ask takes the completely normal
path when nothing is registered at all; and -- the part a shallow check
would get wrong -- an ordinary lookup ask ALSO takes the normal path
even when an unrelated concept IS registered (the taught concept's own
alias/embedding match correctly does not fire on an ask it was never
taught to answer, so registering one concept does not hijack every
other ask).

UPDATE (2026-11-11, same day, later): asked directly why brain.py called
`concept_tools.match_concept`/`teach_and_run` and `render.render_md`
directly instead of going through `lab.common.engine`, duplicating the
same match-execute-render sequence `engine.run` already implements.
Fixed: that sequence was pulled out of `engine.run` into `lab.common.
engine.answer_from_concepts`, and `brain.py` now calls that function
(the same one `engine.run` calls after resolving its own YAML
connector), instead of reaching past `engine.py` into its own
dependencies. Re-ran this exploration's own checks after the refactor --
byte-identical results (see `metrics` and the module's own checks below,
unchanged by this update).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import yaml

from lab.common.brain import reason
from lab.common.harness import Run

FILES = [
    "lab/tests/exp_105_concept_registry_wiring/run.py",
    "lab/common/brain.py",
    "lab/common/engine.py",
    "lab/common/concept_tools.py",
    "lab/common/render.py",
    "lab/common/concepts/examples/timeline.yaml",
    "data/exp_105_concept_registry_wiring/results.json",
]

TIMELINE_CONCEPT = yaml.safe_load((ROOT / "lab/common/concepts/examples/timeline.yaml").read_text(encoding="utf-8"))

TIMELINE_PASSAGES = [
    {"id": "P1", "text": "The purchase was made on 2 March 2024."},
    {"id": "P2", "text": "The notice was filed on 5 April 2024 under Section 12."},
    {"id": "P3", "text": "A second filing occurred on 1 January 2024 under Section 9."},
]

LOOKUP_ASK = "What is the notice period?"
LOOKUP_PASSAGES = [{"id": "Q1", "text": "The notice period is 30 days."}]


def main() -> None:
    run = Run("EXP-105", "exp_105_concept_registry_wiring")

    concept_result = reason("give me a timeline of events", TIMELINE_PASSAGES, concepts=[TIMELINE_CONCEPT])
    concept_step = next((t for t in concept_result["trace"] if t["step"] == "concept_match"), None)
    concept_nodes = [n for n in concept_result["dependency_tree"] if n["kind"] == "concept_match"]

    no_registry_baseline = reason(LOOKUP_ASK, LOOKUP_PASSAGES)

    registered_but_unrelated = reason(LOOKUP_ASK, LOOKUP_PASSAGES, concepts=[TIMELINE_CONCEPT])

    unknown_concept = reason("what is the emotional tone of this document", TIMELINE_PASSAGES, concepts=[TIMELINE_CONCEPT])

    concept_correct = (
        concept_result["decision"] == "supported"
        and concept_step is not None
        and concept_step["method"] == "alias"
        and len(concept_nodes) == 1
        and {"P1", "P2", "P3"} <= set(concept_result["citations"])
    )
    no_registry_correct = no_registry_baseline["decision"] == "supported" and no_registry_baseline["text"] == "30 days [Q1]" and "concept_match" not in [t["step"] for t in no_registry_baseline["trace"]]
    unrelated_correct = registered_but_unrelated["decision"] == "supported" and registered_but_unrelated["text"] == "30 days [Q1]"
    unknown_correct = unknown_concept["decision"] == "inconclusive"

    metrics = {
        "concept_match": {
            "decision": concept_result["decision"],
            "text": concept_result["text"],
            "trace_step": concept_step,
            "dependency_tree_node": concept_nodes,
            "citations": sorted(concept_result["citations"]),
            "correct": concept_correct,
        },
        "no_registry_baseline": {
            "decision": no_registry_baseline["decision"],
            "text": no_registry_baseline["text"],
            "correct": no_registry_correct,
        },
        "registered_but_unrelated_ask": {
            "decision": registered_but_unrelated["decision"],
            "text": registered_but_unrelated["text"],
            "correct": unrelated_correct,
        },
        "ask_matches_nothing_known_primitive": {
            "decision": unknown_concept["decision"],
            "correct": unknown_correct,
        },
    }
    run.write_json("items.json", metrics)

    all_correct = concept_correct and no_registry_correct and unrelated_correct and unknown_correct

    prose = (
        f"The shipped 'timeline' example concept, passed explicitly, answers 'give me a timeline of events' "
        f"through the real reason() entry point: decision={concept_result['decision']!r}, matched via "
        f"{concept_step['method']!r} (score {concept_step['score']}), citations={sorted(concept_result['citations'])} "
        f"-- all 3 source passages, derived from the concept result's own passage_id fields, not guessed. With "
        f"nothing registered at all (today's shipped default), an ordinary lookup ask takes the exact same path "
        f"as before this wiring existed: decision={no_registry_baseline['decision']!r}, zero concept_match step in "
        f"trace. With the timeline concept registered but the ask being an unrelated ordinary lookup, the concept's "
        f"own alias/embedding match correctly does not fire: decision={registered_but_unrelated['decision']!r}, "
        f"text unchanged -- registering one concept does not hijack every other ask. An ask matching no taught "
        f"concept and no registered primitive (concepts list given, but nothing aliases to it): "
        f"decision={unknown_concept['decision']!r}, the same abstain-don't-guess path, not a crash."
    )

    conclusion = (
        "lab.common.concept_tools is now reachable from lab.common.brain.reason (concepts=/records=, both default "
        "None, checked ahead of plan_stages, zero regression for every existing caller since the shipped registry "
        "ships empty). The dispatch is correctly scoped both ways: a genuine match answers through the real "
        "controller with real citations, and a non-match -- whether because nothing is registered or because the "
        "registered concept simply isn't what this particular ask is asking for -- falls straight through to the "
        "completely ordinary pipeline, never hijacking an unrelated ask just because some concept happens to be "
        "loaded."
        if all_correct
        else "At least one case did not behave as expected -- see metrics for exactly which, reported as "
        "measured, not assumed to work."
    )

    run.finish(
        title="lab.common.concept_tools wired into brain.reason ahead of plan_stages, a true no-op until a concept is actually taught",
        goal=(
            "Close the gap the concept-registry's own original exploration explicitly left open ('not wired into "
            "brain.reason ... a new, separate entry point, not a replacement for the existing pipeline'), asked "
            "directly: this is the project's own single stated controller, and a taught capability should be "
            "reachable through it, not only through the separate lab.common.engine.run."
        ),
        method=(
            "The shipped 'timeline' example concept (never auto-loaded by load_concepts(), passed explicitly here) "
            "answers a real timeline ask through reason(), checking decision, trace, dependency_tree, and derived "
            "citations. Three negative/boundary cases: nothing registered at all (today's shipped default); the "
            "concept registered but the ask is unrelated; and an ask matching no known concept or primitive."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="One shipped example concept (timeline), one real match, three negative cases -- a proof the dispatch, citation derivation, and fall-through all work correctly, not a benchmark of concept_tools' own matching accuracy at scale (CONCEPT_TAU's embedding fallback remains provisional, same status this module's own docstring already gives it).",
        referenced_files=FILES,
        follow_ups=[
            "records= (the ctx['records'] half of concept_tools' own input shape, for already-structured rows like party data) is threaded through but not exercised by this exploration -- only a passages-based concept (timeline) was tested; a records-based concept (e.g. parties_name_address) through reason() is a real, untested case.",
            "Dispatch priority when both a taught concept AND document_write's own wants_document() signal could plausibly apply to the same ask was not tested -- concept-matching runs first unconditionally in the current wiring, so a confident concept match always wins; whether that is the right priority for every future taught concept, versus e.g. letting an explicit template_id/notes= caller signal override it, is a judgment call for whoever teaches a concept that could overlap.",
            "lab.common.engine.run itself (the separate, still-live sibling entry point this closes part of the gap with) is untouched by this change -- a caller going through engine.run still gets its own connector_config/render output shapes; this wiring only adds a second way to reach concept_tools' own matching+execution, through reason(), not a merge of the two entry points.",
        ],
        models_used="None for alias matching (exact substring); bge_embed (dense similarity) only for the embedding fallback when no alias matches, same real model concept_tools already used standalone, unconditionally called by this wiring only when it would have been called anyway.",
    )

    print(
        "concept_correct:", concept_correct,
        "no_registry_correct:", no_registry_correct,
        "unrelated_correct:", unrelated_correct,
        "unknown_correct:", unknown_correct,
    )
    print("ALL CORRECT:", all_correct)


if __name__ == "__main__":
    main()
