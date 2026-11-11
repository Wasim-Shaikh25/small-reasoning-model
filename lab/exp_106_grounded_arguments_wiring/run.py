"""EXP-106: "list every grounded argument across the whole passage set",
ported from the deleted lab.common.method_teaching._list_grounded_arguments
and wired directly into lab.common.brain.reason as list_arguments=.

method_teaching.py itself was deleted on 2026-11-10 (commit 84cd228,
"zero fan-in, superseded by concept_tools.py") -- correctly, for every
capability it had EXCEPT this one. Every other primitive it offered
(extract_dates/persons/organizations/amounts, group_by_sentence,
sort_chronological, count) is a special case of concept_tools' own
generic, data-parameterized primitives (extract_by_label(label),
filter_by_condition(field, operator, value), ...) -- genuinely
superseded. list_grounded_arguments is not: it is not a label or a
field to parameterize, it is a second MODE of lab.common.rules.apply_rule
itself -- match every verb rule against every fact across the whole
passage set, instead of resolving one targeted rule for one specific
ask the way rule_application's own stage already does. Nothing in
concept_tools replaces that, and it is not expressible as a concept
YAML's recipe either (concept_tools' primitives operate on `ctx`, not on
rules.py's own rule/fact parsing). Asked directly to add this feature
back, in brain itself.

Wired as `list_arguments=` (default False, zero regression): an explicit
caller flag, checked ahead of the concept registry and plan_stages, same
"an explicit flag beats an ask-inferred signal" precedent `notes` already
set in this module. Scans the FULL passage set (direct + connector-
fetched, after working_set_budget's eviction), unlike `notes`'s own mode
-- this is squarely an "evidence scanning" operation, so it should see
whatever a connector already added, the same as the normal
rule_application stage would.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run

FILES = [
    "lab/exp_106_grounded_arguments_wiring/run.py",
    "lab/common/brain.py",
    "lab/common/rules.py",
    "lab/common/render.py",
    "data/exp_106_grounded_arguments_wiring/results.json",
]

PASSAGES = [
    {"id": "R1", "text": "If someone murders a person, it is a punishable crime."},
    {"id": "R2", "text": "If a person steals property, it is a punishable offense."},
    {"id": "F1", "text": "Arjun murdered Neha."},
    {"id": "F2", "text": "Vikram stole a car."},
    {"id": "F3", "text": "Priya resigned from her job."},  # matches neither rule -- must be excluded
]

LOOKUP_ASK = "Arjun murdered Neha, did that violate a rule?"


def main() -> None:
    run = Run("EXP-106", "exp_106_grounded_arguments_wiring")

    result = reason("list every argument", PASSAGES, list_arguments=True)
    step = next((t for t in result["trace"] if t["step"] == "list_grounded_arguments"), None)
    arg_nodes = [n for n in result["dependency_tree"] if n["kind"] == "grounded_argument"]

    no_match = reason("list every argument", [{"id": "F3", "text": "Priya resigned from her job."}], list_arguments=True)
    no_match_step = next((t for t in no_match["trace"] if t["step"] == "list_grounded_arguments"), None)

    baseline = reason(LOOKUP_ASK, PASSAGES)

    main_correct = (
        result["decision"] == "supported"
        and step is not None
        and step["found"] == 2
        and {"R1", "R2", "F1", "F2"} <= set(result["citations"])
        and "F3" not in result["citations"]
        and len(arg_nodes) == 2
    )
    no_match_correct = no_match["decision"] == "inconclusive" and no_match_step is not None and no_match_step["found"] == 0
    baseline_correct = baseline["decision"] == "supported" and "list_grounded_arguments" not in [t["step"] for t in baseline["trace"]]

    metrics = {
        "list_arguments_true": {
            "decision": result["decision"],
            "text": result["text"],
            "citations": sorted(result["citations"]),
            "found": step["found"] if step else None,
            "dependency_tree_argument_nodes": len(arg_nodes),
            "correct": main_correct,
        },
        "no_grounded_arguments_found": {
            "decision": no_match["decision"],
            "found": no_match_step["found"] if no_match_step else None,
            "correct": no_match_correct,
        },
        "list_arguments_omitted_baseline": {
            "decision": baseline["decision"],
            "correct": baseline_correct,
        },
    }
    run.write_json("items.json", metrics)

    all_correct = main_correct and no_match_correct and baseline_correct

    prose = (
        f"list_arguments=True over 2 rules, 2 matching facts, and 1 unrelated fact: decision="
        f"{result['decision']!r}, {step['found']} grounded arguments found, citations="
        f"{sorted(result['citations'])} -- the unrelated fact (F3) correctly excluded from both the result and "
        f"the citations. The same flag over only the unrelated fact (no rule at all, no match possible): "
        f"decision={no_match['decision']!r}, found={no_match_step['found']} -- an honest abstain, not a crash or "
        f"a guess. The flag omitted entirely, on an ordinary single-rule ask: decision={baseline['decision']!r}, "
        f"zero list_grounded_arguments step in trace -- completely unaffected."
    )

    conclusion = (
        "lab.common.rules.apply_rule's 'list every grounded argument across the whole passage set' mode -- "
        "ported from the deleted lab.common.method_teaching, the one capability it had that concept_tools did "
        "NOT supersede -- is now reachable directly from lab.common.brain.reason (list_arguments=, default "
        "False, zero regression for every existing caller). Unlike every other capability wired into brain.reason "
        "this session, this one needed no sibling module at all: it is built entirely from functions "
        "rule_application's own stage already imports and uses (parse_conditional_rule, extract_fact_triple, "
        "apply_rule), just run in a different mode (every pair, not the first match)."
        if all_correct
        else "At least one case did not behave as expected -- see metrics for exactly which, reported as "
        "measured, not assumed to work."
    )

    run.finish(
        title="'List every grounded argument', ported from the deleted method_teaching.py, wired into brain.reason as list_arguments=",
        goal=(
            "Restore the one capability method_teaching.py had that concept_tools.py did not actually supersede "
            "when that module was deleted (2026-11-10) -- enumerating every (rule, fact) match across a whole "
            "passage set, a second mode of apply_rule itself, not a data-parameterizable primitive -- directly "
            "into brain.reason, asked for by name."
        ),
        method=(
            "A fixture with 2 verb rules and 3 facts (2 that ground a rule, 1 that grounds neither), checking "
            "decision, the found-argument count, and that the unrelated fact never appears in the result or "
            "citations. A second case with only the unrelated fact, checking the honest-abstain path. A third "
            "case with the flag omitted on an ordinary single-rule ask, checking zero behavior change."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="2 rules, 3 facts -- a proof the dispatch, matching, and citation/dependency-tree bookkeeping work correctly end to end, not a benchmark of apply_rule's own lemma-match precision at a larger corpus scale (already a known, documented limitation of apply_rule itself, unchanged by this wiring).",
        referenced_files=FILES,
        follow_ups=[
            "Scoped the same way the original method_teaching version was: verb-triggered rules only (parse_conditional_rule), apply_rule's exact lemma match, and no check_exceptions/split_exceptions exception-gating -- a listed argument's consequence may still be blocked by an unlisted exception elsewhere in the same passages. Extending this to threshold rules, semantic_apply_rule's paraphrase-robust NLI match, or exception-gating is a real, separate scope decision, not done here.",
            "No citation-count or corpus-size limit exists on this path -- a very large passage set with many rules and many facts does an O(rules x facts) scan; working_set_budget (if a connector is in play) bounds how many passages reach this point at all, but there is no independent cap on the scan itself.",
        ],
        models_used="None -- parse_conditional_rule/extract_fact_triple/apply_rule are all deterministic (regex + dependency parse + lemma comparison); render_md (lab.common.render) formats the result, no model involved.",
    )

    print("main_correct:", main_correct, "no_match_correct:", no_match_correct, "baseline_correct:", baseline_correct)
    print("ALL CORRECT:", all_correct)


if __name__ == "__main__":
    main()
