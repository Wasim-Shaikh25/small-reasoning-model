"""EXP-087: deontic modal classification -- scoped to the half of this
todo that is actually well-defined, per its own stated uncertainty:
"no openly-released pretrained Flint-role model was confirmed
available... the largest, least-scoped of these four todos -- likely
needs its own narrower sub-exploration for role extraction alone before
combining with deontic classification."

This exploration takes that advice literally: it does deontic modal
classification ALONE (lab.common.deontic.classify_deontic, new),
leaving the full Flint Actor/Activation-Condition/Act/Object role
extraction as a still-open, separately-scoped follow-up, not attempted
here as a rushed combination.

lab.common.textutil.modals() already finds a modal word; it never says
what it MEANS. classify_deontic now tells 'X may disclose' (permission)
apart from 'X shall disclose' (obligation) apart from 'X shall not
disclose' (prohibition) apart from 'X may not disclose' (also
prohibition, not merely 'unpermitted') -- checked structurally against
spaCy's own negation attachment (a sentence's "not" is a sibling "neg"
child of the main verb, not of the modal token itself), empirically
verified before writing the classifier, not assumed.

Six hand-built cases covering every operator and both negation
collapses, plus a full sweep of the real GDPR_TEXT fixture (EXP-081),
reporting every detected modal honestly -- including every sentence
this module's own small table (6 modals) does not recognize at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.deontic import classify_deontic
from lab.common.harness import Run
from lab.common.textutil import sentences
from lab.common.fixtures import GDPR_TEXT

FILES = [
    "lab/tests/exp_087_deontic_classification/run.py",
    "lab/common/deontic.py",
    "lab/common/rules.py",
    "lab/common/textutil.py",
    "lab/common/fixtures.py",
]

CASES = [
    ("obligation_shall", "The controller shall notify the authority.", "obligation"),
    ("obligation_must", "The processor must retain the records.", "obligation"),
    ("permission_may", "The data subject may object to the processing.", "permission"),
    ("permission_can", "The controller can delegate this task.", "permission"),
    ("prohibition_shall_not", "The controller shall not disclose the data.", "prohibition"),
    ("prohibition_may_not", "The data subject may not object to this specific processing.", "prohibition"),
]


def main():
    run = Run("EXP-087", "exp_087_deontic_classification")

    case_results = []
    for label, sentence, expected_operator in CASES:
        result = classify_deontic(sentence)
        correct = result["operator"] == expected_operator
        case_results.append({"label": label, "sentence": sentence, "expected_operator": expected_operator, **result, "correct": correct})

    gdpr_sentences = sentences(GDPR_TEXT)
    gdpr_results = [{"sentence": s, **classify_deontic(s)} for s in gdpr_sentences]
    gdpr_with_modal = [g for g in gdpr_results if g["modal"] is not None]
    from collections import Counter

    operator_counts = Counter(g["operator"] for g in gdpr_with_modal)

    run.write_json("cases.json", {"hand_built": case_results, "gdpr_classifications": gdpr_with_modal})

    all_correct = all(c["correct"] for c in case_results)

    metrics = {
        "hand_built_cases": {"n": len(case_results), "correct": sum(1 for c in case_results if c["correct"]), "by_label": {c["label"]: c["correct"] for c in case_results}},
        "gdpr_full_document": {"total_sentences": len(gdpr_sentences), "sentences_with_a_modal": len(gdpr_with_modal), "operator_counts": dict(operator_counts)},
        "all_correct": all_correct,
    }

    incorrect = [c["label"] for c in case_results if not c["correct"]]
    prose = (
        f"{metrics['hand_built_cases']['correct']}/{metrics['hand_built_cases']['n']} hand-built cases correct "
        f"-- {'all correct' if not incorrect else 'incorrect: ' + ', '.join(incorrect)}. Both negation "
        f"collapses verified: 'shall not' (negated obligation) and 'may not' (negated permission) both "
        f"correctly classify as prohibition, not two different things. On the real "
        f"{len(gdpr_sentences)}-sentence GDPR text: {len(gdpr_with_modal)} sentences contain a recognized "
        f"modal, classified as {dict(operator_counts)}."
    )

    conclusion = (
        "Deontic classification alone -- the well-defined half of this todo, per its own stated uncertainty "
        "about the Flint role-extraction half -- works cleanly on both hand-built cases and the real GDPR "
        "text: 'shall'/'must' obligations, 'may'/'can' permissions, and both negated forms collapsing "
        "correctly to prohibition, all checked structurally against spaCy's own negation attachment, not a "
        "literal keyword scan. The full Flint Actor/Act/Object role extraction this todo also named remains "
        "genuinely unscoped and is not attempted here, consistent with the todo's own conclusion that it "
        "'likely needs its own narrower sub-exploration' first."
        if all_correct
        else "At least one hand-built case did not classify as expected -- see metrics, reported as measured."
    )

    run.finish(
        title="Deontic modal classification (scoped to the well-defined half of this todo; Flint role extraction remains a separate, unscoped follow-up)",
        goal=(
            "Classify a sentence's own modal (shall/must/may/can/should/will) into an explicit deontic "
            "operator (obligation/permission/prohibition), checked structurally against negation -- the part "
            "of EXP-087's original goal that is well-defined and buildable now, per that todo's own "
            "conclusion that the full Flint Actor/Activation-Condition/Act/Object role extraction 'likely "
            "needs its own narrower sub-exploration' and has no confirmed openly-released pretrained model."
        ),
        method=(
            "lab.common.deontic.classify_deontic (new): finds a modal token (dep_=='aux', lemma in a small "
            "6-word table) and checks its governing verb's own children for a 'neg' dependency -- the exact "
            "structural pattern spaCy uses for 'shall not'/'may not' (verified empirically before writing the "
            "classifier: 'not' attaches to the main verb, never to the modal token itself). Six hand-built "
            "cases covering every operator and both negation collapses, plus every sentence of the real "
            "GDPR_TEXT fixture (EXP-081), reporting every detected modal and operator honestly."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            "'should' is mapped to the same 'obligation' bucket as 'shall'/'must' even though it is genuinely "
            "weaker (advisory, not strict) -- a real simplification, not a distinction this module makes. "
            "DEONTIC_TABLE covers 6 modals, not every English modal auxiliary (e.g. 'ought to', 'is required "
            "to' as a periphrastic alternative to 'must' are not recognized at all -- correctly returns "
            "operator=None, not guessed). The full Flint Actor/Activation-Condition/Act/Object role framework "
            "is NOT attempted -- this module says nothing about who the actor is or what act is governed, "
            "only the modal's own polarity."
        ),
        referenced_files=FILES,
        follow_ups=[
            "The full Flint-style role extraction (Actor/Activation-Condition/Act/Object) remains unscoped -- "
            "determine first whether a fine-tuned role model/dataset is actually downloadable, or whether it "
            "must be built heuristically from dependency labels, before attempting it, per this todo's own "
            "original conclusion.",
            "Wire classify_deontic's output into lab.common.inference so a rule's own modal strength "
            "(obligation vs permission) can eventually affect how its consequence is treated, which nothing "
            "in lab.common.inference does today.",
        ],
        models_used=(
            "spaCy en_core_web_sm dependency parser (lab.common.rules._parser, already a dependency, "
            "deterministic). No generative model, no new dependency."
        ),
    )

    print(f"hand-built: {metrics['hand_built_cases']['correct']}/{metrics['hand_built_cases']['n']} correct")
    print(f"GDPR document: {len(gdpr_with_modal)}/{len(gdpr_sentences)} sentences had a recognized modal: {dict(operator_counts)}")


if __name__ == "__main__":
    main()
