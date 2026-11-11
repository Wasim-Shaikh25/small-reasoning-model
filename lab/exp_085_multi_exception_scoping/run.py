"""EXP-085: multi-exception (OR-combined) rule scoping, measured on GDPR
Article 9's own real exceptions, not a restated single-exception toy rule.

EXP-083 proved exception handling for exactly one "unless <condition>"
clause (self-defense), in all three of its honest states (unresolved,
holds, does not hold), and named its own scale-down directly: "Not yet
tested on a rule with more than one exception combined by OR (GDPR Art 9's
actual shape ... any one of which blocks the prohibition) -- split_exception
only handles a single trailing 'unless' clause, not a disjunction of
several." This exploration closes exactly that gap.

lab.common.inference.split_exceptions and check_exceptions (new, plural)
generalize split_exception/check_exception (both left unchanged) from one
exception condition to a list of alternatives combined by OR. check_exception
itself still makes the same single bounded NLI judgment per condition it
always made; check_exceptions only combines that existing three-way verdict
across more than one alternative:
  - any alternative holds -> the rule's consequence is blocked.
  - none holds and every alternative is unknown -> still derived, but
    marked conditional=True (EXP-083's honest-abstention posture, now
    proven across several alternatives, not just one).
  - none holds and at least one is confidently not_holds -> derived
    cleanly, conditional=False.

The three exception conditions used here are not retyped by hand -- they
are pulled out of lab.exp_081_real_document_pipeline.run's own GDPR_TEXT
fixture (the real ~2,400-word, 13-article GDPR excerpt already in this
repo) with a regex over its three "This prohibition shall not apply if
..." sentences, and the script asserts exactly three are found. Correction
to this project's own prior record: EXPLORATIONS.md's EXP-085 entry (added
in commit 21528ff) describes this as "GDPR Art 9's actual four exceptions"
-- as embedded in the repo's own fixture, Art 9 has three listed exceptions
(consent; vital interests; legal claims or judicial capacity), not four.
Real GDPR Art 9 does have a fourth paragraph (processing by a non-profit
body for its own members), which this project's own fixture does not
include -- reported here as measured against the fixture that actually
exists, not against the uncaptured fourth paragraph.

parse_conditional_rule only supports one sentence shape, "If <subject>,
<verb phrase>, <consequence>." -- it does not parse the real GDPR Art 9
text's own multi-sentence shape (one "...shall be prohibited." sentence
followed by three separate "This prohibition shall not apply if..."
sentences). Rebuilding a general prohibition+exception sentence parser is
a separate, larger piece of work (closer to EXP-087's Flint-role scope)
and not required to prove the OR-combination mechanism itself. So, exactly
as EXP-083 built EXCEPTION_RULE_TEXT by hand in the one shape this parser
supports, this exploration builds one hand-composed rule sentence in that
same shape, using the three exception conditions verbatim from GDPR_TEXT,
joined with ";" -- the only separator split_exceptions treats as "a new
alternative starts here" (a bare "," or "or" is deliberately left alone,
since the real exception text is itself full of both: "the establishment,
exercise or defence of legal claims or whenever courts are acting in
their judicial capacity" is ONE alternative, not three).

No generative model anywhere in this mechanism, same as EXP-083: spaCy's
dependency parser (rule/fact extraction, unchanged) and the real
DeBERTa-v3 MNLI checkpoint (lab.common.real_encoders.real_nli, unchanged,
called once per exception alternative via the existing check_exception).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.inference import forward_chain
from lab.common.rules import extract_fact_triple, parse_conditional_rule
from lab.common.fixtures import GDPR_TEXT

FILES = [
    "lab/exp_085_multi_exception_scoping/run.py",
    "lab/common/inference.py",
    "lab/common/rules.py",
    "lab/common/fixtures.py",
    "lab/exp_083_symbolic_inference/run.py",
    "data/exp_083_symbolic_inference/results.json",
    "data/exp_085_multi_exception_scoping/results.json",
]

_EXCEPTION_SENTENCE_RE = re.compile(r"This prohibition shall not apply if (.+?)\.")
GDPR_ART9_EXCEPTIONS = _EXCEPTION_SENTENCE_RE.findall(GDPR_TEXT)
assert len(GDPR_ART9_EXCEPTIONS) == 3, (
    f"Expected exactly 3 'This prohibition shall not apply if ...' sentences in the repo's own "
    f"GDPR_TEXT fixture, found {len(GDPR_ART9_EXCEPTIONS)} -- the fixture changed; re-check before trusting this run."
)
CONSENT_EXCEPTION, VITAL_INTERESTS_EXCEPTION, LEGAL_CLAIMS_EXCEPTION = GDPR_ART9_EXCEPTIONS

FACT_TEXT = "MedCorp processed Aisha."
RULE_TEXT = (
    f"If anyone processes special category data, it is unlawful, unless "
    f"{CONSENT_EXCEPTION}; {VITAL_INTERESTS_EXCEPTION}; or {LEGAL_CLAIMS_EXCEPTION}."
)


def _signature_set(facts: list[dict]) -> set[tuple]:
    return {(f["subject"], f["verb_lemma"], f.get("object")) for f in facts if f.get("subject")}


def _per_exception_statuses(derived: list[dict]) -> list[str] | None:
    if not derived:
        return None
    return [r["status"] for r in derived[0]["derivation"]["exception_check"]["per_exception"]]


def main():
    run = Run("EXP-085", "exp_085_multi_exception_scoping")

    fact = extract_fact_triple(FACT_TEXT)
    rule = parse_conditional_rule(RULE_TEXT)
    assert rule is not None and rule["trigger_lemma"] == fact["verb_lemma"] == "process"

    # Case 1: no context either way -- every one of the three alternatives
    # must come back unknown, and the derivation must still happen but
    # marked conditional, never silently treated as "no exception applies".
    case1 = forward_chain([fact], [rule], context_texts=[])
    case1_derived = [f for f in case1["facts"] if f.get("derivation")]
    case1_status = case1_derived[0]["derivation"]["exception_check"]["status"] if case1_derived else None
    case1_correct = len(case1_derived) == 1 and case1_derived[0]["conditional"] is True and case1_status == "unknown"

    # Case 2: context affirms the FIRST alternative (consent) -- blocked.
    # Deliberately near-verbatim (tuned against the real NLI model
    # beforehand, scored entail=0.9941): a lexically close restatement of
    # the exception condition itself, not a loosely paraphrased story --
    # DeBERTa-v3 MNLI's entailment score for this exception condition
    # dropped sharply with even modest paraphrasing (a named-entity version
    # mentioning "Aisha" instead of "the data subject" scored only 0.39,
    # well under tau), so the context text stays close to the condition's
    # own wording on purpose.
    case2 = forward_chain(
        [fact],
        [rule],
        context_texts=["The data subject has given explicit consent to the processing of those personal data for one or more specified purposes."],
    )
    case2_derived = [f for f in case2["facts"] if f.get("derivation")]
    case2_correct = len(case2_derived) == 0

    # Case 3: context affirms a DIFFERENT alternative (vital interests) --
    # also blocked. Proves the OR-combination genuinely checks every listed
    # alternative, not just the first one case 2 happened to use. Same
    # near-verbatim tuning as case 2 (tested entail=0.9075); a paraphrased
    # version naming Aisha and restructuring the sentence scored only
    # 0.24, well under tau.
    case3 = forward_chain(
        [fact],
        [rule],
        context_texts=[
            "Processing was necessary to protect the vital interests of the data subject or of another natural "
            "person where the data subject was physically or legally incapable of giving consent."
        ],
    )
    case3_derived = [f for f in case3["facts"] if f.get("derivation")]
    case3_correct = len(case3_derived) == 0

    # Case 4: context confidently rules out only ONE alternative (consent);
    # the other two are never mentioned, so they stay unknown. None holds,
    # and at least one is confidently not_holds, so the consequence must
    # still derive cleanly (conditional=False) -- the engine does not need
    # every alternative individually ruled out, only that none holds and
    # at least one is confidently ruled out.
    case4 = forward_chain(
        [fact],
        [rule],
        context_texts=["Aisha never gave any consent at all for this processing."],
    )
    case4_derived = [f for f in case4["facts"] if f.get("derivation")]
    case4_status = case4_derived[0]["derivation"]["exception_check"]["status"] if case4_derived else None
    case4_correct = len(case4_derived) == 1 and case4_derived[0]["conditional"] is False and case4_status == "not_holds"

    run.write_json(
        "cases.json",
        {
            "case1_all_unknown": case1,
            "case2_holds_via_consent": case2,
            "case3_holds_via_vital_interests": case3,
            "case4_not_holds_one_contradicted": case4,
        },
    )

    all_correct = case1_correct and case2_correct and case3_correct and case4_correct

    metrics = {
        "gdpr_art9_exceptions_found": len(GDPR_ART9_EXCEPTIONS),
        "case1_all_unknown": {"correct": case1_correct, "status": case1_status, "per_exception": _per_exception_statuses(case1_derived)},
        "case2_holds_via_consent": {"correct": case2_correct, "derived_count": len(case2_derived)},
        "case3_holds_via_vital_interests": {"correct": case3_correct, "derived_count": len(case3_derived)},
        "case4_not_holds_one_contradicted": {"correct": case4_correct, "status": case4_status, "per_exception": _per_exception_statuses(case4_derived)},
        "all_correct": all_correct,
    }

    prose = (
        f"Rule: 3 OR-combined exceptions pulled verbatim from the repo's own GDPR_TEXT fixture (found "
        f"{metrics['gdpr_art9_exceptions_found']}, not the 4 EXPLORATIONS.md's own prior EXP-085 entry claimed). "
        f"Case 1 (no context, all 3 unknown): per-exception statuses {metrics['case1_all_unknown']['per_exception']}, "
        f"overall '{case1_status}', derived-but-conditional -- correct={case1_correct}. Case 2 (context affirms the "
        f"consent alternative): {metrics['case2_holds_via_consent']['derived_count']} facts derived (blocked) -- "
        f"correct={case2_correct}. Case 3 (context affirms the DIFFERENT vital-interests alternative): "
        f"{metrics['case3_holds_via_vital_interests']['derived_count']} facts derived (also blocked) -- "
        f"correct={case3_correct}, proving the OR-combination checks every listed alternative, not just whichever "
        f"one case 2 happened to use. Case 4 (context only contradicts the consent alternative; the other two stay "
        f"unknown): per-exception statuses {metrics['case4_not_holds_one_contradicted']['per_exception']}, overall "
        f"'{case4_status}', derived cleanly (conditional=False) -- correct={case4_correct}."
    )

    conclusion = (
        "Multi-exception OR-combination works on GDPR Art 9's own real exception text, not just a restated "
        "single-exception toy rule: any one of several listed alternatives blocks the consequence when it holds "
        "(proven on two different alternatives, not only the first), the consequence still derives -- visibly "
        "flagged conditional -- when every alternative is genuinely unresolved, and it derives cleanly once none "
        "holds and at least one alternative is confidently ruled out, without needing every alternative "
        "individually ruled out first. check_exception's own per-exception judgment is unchanged; check_exceptions "
        "only combines its existing three-way verdict across more than one condition, split on ';' so that a "
        "single alternative's own internal commas and 'or's (common in real statutory text) are never mistaken "
        "for a boundary between alternatives."
        if all_correct
        else "At least one case did not behave as expected -- see metrics for exactly which, reported as measured, "
        "not assumed to work."
    )

    run.finish(
        title="Multi-exception (OR-combined) rule scoping, measured on GDPR Art 9's actual three exceptions",
        goal=(
            "Extend lab.common.inference's single-exception handling (EXP-083) to a disjunction of several "
            "alternative exceptions combined by OR, each still checked by the existing, unmodified "
            "check_exception/NLI mechanism, and prove the OR-combination's three honest states (any holds blocks; "
            "all unknown still derives but conditional; none holds with at least one confidently ruled out derives "
            "cleanly) on the real motivating case this gap was found against -- GDPR Article 9, not a restated "
            "single-exception rule."
        ),
        method=(
            "lab.common.inference.split_exceptions (new) generalizes split_exception's single trailing 'unless "
            "<condition>' clause to a list of alternatives, split only on ';' so a single alternative's own "
            "internal commas/or's are preserved. lab.common.inference.check_exceptions (new) calls the existing, "
            "unmodified check_exception once per alternative and OR-combines the three-way verdict. forward_chain "
            "now calls split_exceptions/check_exceptions in place of the singular functions -- a one-item list "
            "degenerates to the exact same behavior the singular path always had, confirmed by re-running EXP-083 "
            "after this change (data/exp_083_symbolic_inference/results.json, re-rendered, unchanged). The rule "
            "itself is one hand-composed sentence in parse_conditional_rule's one supported shape, its three "
            "exception alternatives pulled verbatim (by regex, with an assertion on the count) from lab."
            "exp_081_real_document_pipeline.run's own real ~2,400-word GDPR fixture, not retyped by hand and not a "
            "new document."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            "One hand-composed rule sentence (parse_conditional_rule's one supported shape), not an automatic "
            "parse of GDPR Art 9's own real multi-sentence prohibition+exception wording -- that would need a "
            "genuinely different rule-sentence parser (closer to EXP-087's Flint-role scope), a separate and much "
            "larger piece of work, not required to prove the OR-combination mechanism itself. The repo's own "
            "GDPR_TEXT fixture has 3 listed exceptions for Art 9, not the 4 this project's own prior EXP-085 "
            "todo entry claimed (real GDPR Art 9 has a 4th paragraph, covering non-profit-body members' data, "
            "that this fixture does not include) -- measured against the fixture that actually exists in this "
            "repo, corrected here rather than restated uncritically. Four hand-built cases proving each named "
            "combination state, not a broad benchmark across many multi-exception rules."
        ),
        referenced_files=FILES,
        follow_ups=[
            "Not tested on a rule where TWO OR MORE alternatives simultaneously hold at once (only one alternative "
            "holding at a time was exercised here) -- the any()-based combination should be unaffected, but this "
            "specific case was not run.",
            "GDPR Art 9's real 4th paragraph (non-profit bodies processing their own members' data) is not in this "
            "repo's GDPR_TEXT fixture at all -- extending that fixture, or fetching the complete Art 9 text, is a "
            "real follow-up before calling this fixture complete.",
            "Automatically parsing GDPR Art 9's own real sentence shape (one prohibition sentence, followed by "
            "several separate 'This prohibition shall not apply if...' sentences) directly, instead of hand-"
            "composing a single parse_conditional_rule-shaped sentence from its extracted exception clauses, "
            "needs a genuinely different rule-sentence parser -- not built here.",
            "check_exceptions's NLI call still reads one context sentence as one premise per alternative, the "
            "same known limit EXP-083 already named for the single-exception case -- a longer passage with one "
            "alternative's evidence buried among many unrelated clauses was not tested.",
            "The real DeBERTa-v3 MNLI checkpoint's entailment score for these two exception conditions (consent; "
            "vital interests) was measured to be sharply sensitive to lexical distance from the condition's own "
            "wording: a context sentence naming the specific data subject and restructuring the sentence (e.g. "
            "'Processing was necessary to protect the vital interests of Aisha, who was physically incapable of "
            "giving consent.') scored entail=0.24-0.39, well under tau=0.75, while a near-verbatim restatement of "
            "the same fact (only tense-shifted) scored 0.91-0.99. Cases 2 and 3's context texts were tuned against "
            "the real model for exactly this reason, not picked blind. check_exception's entailment gate works "
            "only when the given context stays close to the exception's own phrasing -- a real document's evidence "
            "almost never will -- so this is a real brittleness, not an artifact of this exploration's fixtures, "
            "and a genuine blocker before trusting this mechanism on natural (not hand-tuned) context text.",
        ],
        models_used=(
            "spaCy en_core_web_sm dependency parser (fact/rule extraction, unchanged, non-generative) + "
            "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli (per-exception entailment via the existing, unmodified "
            "check_exception, one bounded judgment per alternative, non-generative). No generative model anywhere "
            "in this exploration."
        ),
    )

    print(
        "case1:", case1_correct,
        "case2:", case2_correct,
        "case3:", case3_correct,
        "case4:", case4_correct,
    )


if __name__ == "__main__":
    main()
