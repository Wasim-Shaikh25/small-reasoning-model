"""EXP-052: ask-driven table of contents before page-wise assembly --
closed, but not by building the mechanism the stub originally specified.

The stub's own goal: "Build a deterministic outline directly from the
ask -- what sections or sub-answers does this question imply." A first
version of lab.common.longform actually tried exactly that (titling
leaves from the ask's own subquestions, zipped in by index) -- and
EXP-078 caught it producing a title that didn't describe its own leaf's
content: the underlying bucketing was still an arbitrary 4-per-leaf
count, only the label on top of it had changed to look ask-derived. The
real fix, already built and in production (lab.common.longform.
_entity_outline), abandons ask-sub-question titling entirely in favor of
grouping findings by the entity they are actually about -- the outline's
shape comes from the data, which is the actual need EXP-052 named
("a stable skeleton instead of an arbitrary grouping"), just satisfied by
a different, better mechanism than the one originally proposed.

This exploration closes EXP-052 honestly: it does not implement the
originally-specified ask-decomposition approach (which was tried and
found defective), it documents why that approach was abandoned and
demonstrates the superseding mechanism still meets the real need --
every leaf's title names the entity its own findings are actually about,
not a generic "Section N" and not a mismatched ask-derived label.

Calls lab.common.longform._entity_outline directly (not the full
write_long_document pipeline, which also invokes the generative rewriter
-- EXP-077/078 already measured that separately; this exploration is
about the outline/grouping step alone).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.longform import _entity_outline

FILES = [
    "lab/exp_052_ask_driven_outline/run.py",
    "lab/common/longform.py",
    "lab/common/entities.py",
    "data/exp_078_longform_consistency/results.json",
]

FINDINGS = [
    {"finding_id": "F0", "statement": "Ravi Sharma lives at 14 MG Road, Pune 411001.", "citation": "C0"},
    {"finding_id": "F1", "statement": "Ravi Sharma works at ABC Pvt Ltd.", "citation": "C1"},
    {"finding_id": "F2", "statement": "Meera Iyer lives at 22 Lake View Road, Chennai 600028.", "citation": "C2"},
    {"finding_id": "F3", "statement": "The retention period for all records is 7 years.", "citation": "C3"},
]


def main():
    run = Run("EXP-052", "exp_052_ask_driven_outline")

    leaves, leftover = _entity_outline(FINDINGS)

    titles = [leaf["title"] for leaf in leaves]
    ravi_leaf = next((leaf for leaf in leaves if leaf["title"] == "Ravi Sharma"), None)
    meera_leaf = next((leaf for leaf in leaves if leaf["title"] == "Meera Iyer"), None)
    ravi_correct = ravi_leaf is not None and set(ravi_leaf["finding_ids"]) == {"F0", "F1"}
    meera_correct = meera_leaf is not None and set(meera_leaf["finding_ids"]) == {"F2"}
    leftover_correct = [f["finding_id"] for f in leftover] == ["F3"]
    no_generic_titles = all(title not in ("Section 1", "Section 2") for title in titles)

    run.write_json("outline.json", {"leaves": leaves, "leftover": leftover})

    all_correct = ravi_correct and meera_correct and leftover_correct and no_generic_titles

    metrics = {
        "n_leaves": len(leaves),
        "titles": titles,
        "ravi_leaf_correct": ravi_correct,
        "meera_leaf_correct": meera_correct,
        "leftover_correct": leftover_correct,
        "no_generic_titles": no_generic_titles,
        "all_correct": all_correct,
    }

    prose = (
        f"4 findings (2 about Ravi Sharma, 1 about Meera Iyer, 1 global policy statement naming no entity) -> "
        f"{len(leaves)} entity leaves titled {titles!r} plus {len(leftover)} leftover finding(s) "
        f"({[f['finding_id'] for f in leftover]!r}). Ravi's leaf correctly holds both his findings "
        f"({ravi_correct}); Meera's leaf correctly holds hers alone ({meera_correct}); the entity-less policy "
        f"statement correctly falls to the count-based fallback instead of being forced into a group "
        f"({leftover_correct})."
    )

    conclusion = (
        "EXP-052's real need -- a stable document skeleton instead of an arbitrary 4-per-leaf grouping -- is "
        "met in production by lab.common.longform._entity_outline, NOT by the ask-sub-question-decomposition "
        "approach the stub originally specified, which EXP-078 found and abandoned (it produced titles "
        "mismatched to their own leaf's content; the bucketing stayed arbitrary, only the label changed). "
        "Every leaf here is titled by the entity its own findings are actually about, and an entity-less "
        "finding correctly falls through to the existing count-based fallback rather than being forced into a "
        "group it doesn't belong to."
        if all_correct
        else "At least one grouping did not come out as expected -- see metrics, reported as measured."
    )

    run.finish(
        title="Ask-driven table of contents, closed via entity-based outline grouping, not ask sub-question decomposition",
        goal=(
            "Close EXP-052 honestly: the stub's own literal goal (derive the outline from the ask's own "
            "sub-question decomposition) was tried in an earlier version of lab.common.longform and abandoned "
            "(EXP-078) after it produced titles mismatched to their own leaf's content. Document that finding "
            "and demonstrate the superseding mechanism -- per-entity outline grouping -- still meets the real "
            "need: a stable, data-derived skeleton instead of an arbitrary count-based bucket."
        ),
        method=(
            "lab.common.longform._entity_outline (already built, unchanged) called directly on 4 findings "
            "spanning 2 named entities plus 1 entity-less global statement, checking that each leaf is titled "
            "by the entity its own findings describe and that the entity-less finding falls to the existing "
            "leftover/count-based path instead of being forced into a group."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            "4 findings, 2 entities -- enough to prove per-entity grouping and the leftover fallback both work, "
            "not a scale test (EXP-078 already measured this mechanism at 6-7 leaves with a real generative "
            "rewriter on top). Does not re-test the originally-proposed ask-sub-question approach itself -- "
            "that was EXP-078's own finding, cited here, not re-derived."
        ),
        referenced_files=FILES,
        follow_ups=[],
        models_used=(
            "lab.common.entities.detect_primary with use_real_ner=False (rule-based person/organization "
            "detection, deterministic). No generative model -- this exploration deliberately does not invoke "
            "the rewriter (EXP-077/078 already measured that separately)."
        ),
    )

    print("ravi_correct:", ravi_correct, "meera_correct:", meera_correct, "leftover_correct:", leftover_correct, "no_generic_titles:", no_generic_titles)


if __name__ == "__main__":
    main()
