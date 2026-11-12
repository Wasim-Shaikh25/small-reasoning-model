"""EXP-088: real-world validation of multi-exception scoping, with no
tuning this time.

EXP-085 proved the OR-combination mechanism (split_exceptions/
check_exceptions) on four hand-built cases, but its own context sentences
for the "exception holds" cases were written, scored against the real NLI
model, found too weak (entail 0.24-0.39), and then REWRITTEN to lexically
mirror the exception's own clause wording until they crossed tau --
reported honestly as a follow-up at the time, but still exactly the
objection the project owner raised: that is tuning to the test, not
real-world validation.

This exploration does the real-world version. Every context sentence
below is a worked example from the UK ICO's own published guidance (fetched
from ico.org.uk, 2026-10-18 -- see each case's "source" field), or from a
real GDPR enforcement decision, restated close to how the source itself
phrases it. None of them are reworded to mirror GDPR Art 9's own clause
language, and none were iterated against the model's score. Whatever
check_exceptions reports here is reported as measured, including a result
that does not cross tau -- that would be a real, not a hidden, finding
about how far this mechanism's entailment gate reaches past hand-tuned
fixtures.

Four cases:
  1. ICO's own consent example (a gym's facial-recognition access system,
     offered as a genuine choice) -- expected real-world conclusion:
     explicit consent condition holds.
  2. ICO's own vital-interests example (an unconscious, seriously injured
     employee; the employer discloses medication allergies to the
     ambulance crew) -- expected real-world conclusion: vital interests
     condition holds.
  3. ICO's own legal-claims example (an employer being sued following a
     workplace accident, sharing injury details with its solicitors) --
     expected real-world conclusion: legal claims condition holds.
  4. A real Spanish AEPD enforcement decision (Eurocollege Oxford English
     Institute, 2023/2024) where a school required medical/COVID
     certificates from students and visitors with no applicable Article 9
     exception, and was fined -- this scenario is a genuine GDPR Art 9
     violation, but it is about a *different* fact pattern than this
     exploration's own rule/fact and never mentions consent, vital
     interests, or legal claims at all. The honestly expected measured
     outcome here is NOT "not_holds" (that would require the model to
     confidently rule out specific exceptions nothing in this text
     addresses) -- it is "unknown", the same honest-abstention posture
     EXP-083 named for the single-exception case: absence of evidence
     about consent/vital-interests/legal-claims is not evidence that none
     of them could apply, even when the source text is itself a real
     violation finding about an unrelated fact pattern.

The underlying rule/fact/exception machinery (split_exceptions,
check_exceptions, forward_chain) is completely unchanged from EXP-085 --
this exploration only swaps in real validation data and removes the
tuning step.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.inference import forward_chain
from lab.common.rules import extract_fact_triple, parse_conditional_rule
from lab.tests.exp_085_multi_exception_scoping.run import FACT_TEXT, GDPR_ART9_EXCEPTIONS, RULE_TEXT

FILES = [
    "lab/tests/exp_088_real_world_validation/run.py",
    "lab/common/inference.py",
    "lab/tests/exp_085_multi_exception_scoping/run.py",
    "data/exp_085_multi_exception_scoping/results.json",
    "data/exp_088_real_world_validation/results.json",
]

CONSENT_EXCEPTION, VITAL_INTERESTS_EXCEPTION, LEGAL_CLAIMS_EXCEPTION = GDPR_ART9_EXCEPTIONS

CASES = {
    "consent_ico_gym": {
        "context": (
            "A gym introduced a facial recognition system to allow members access to its facilities. It "
            "offered members a choice rather than making it a condition of entry, and relied on explicit "
            "consent for processing the biometric facial scans of the members who indicated that they "
            "preferred that option."
        ),
        "target_index": 0,
        "target_label": "consent",
        "expected_real_world": "holds",
        "source": "https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/special-category-data/what-are-the-conditions-for-processing/ (ICO worked example, Article 9(2)(a))",
    },
    "vital_interests_ico_unconscious": {
        "context": (
            "A member of staff experienced an accident at work, sustained serious injuries, and was "
            "unconscious. Their employer could not obtain the employee's consent to give the ambulance "
            "crew details of the employee's medication allergies, and so relied on the vital interests "
            "condition for the processing."
        ),
        "target_index": 1,
        "target_label": "vital_interests",
        "expected_real_world": "holds",
        "source": "https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/special-category-data/what-are-the-conditions-for-processing/ (ICO worked example, Article 9(2)(c))",
    },
    "legal_claims_ico_tribunal": {
        "context": (
            "An employer was being sued by one of its employees following an accident at work. The "
            "employer shared the accident details, including injury information, with its solicitors to "
            "obtain legal advice and defend the claim."
        ),
        "target_index": 2,
        "target_label": "legal_claims",
        "expected_real_world": "holds",
        "source": "https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/special-category-data/what-are-the-conditions-for-processing/ (ICO worked example, Article 9(2)(f))",
    },
    "violation_aepd_eurocollege": {
        "context": (
            "A Spanish data protection authority fined an English-language school for requiring students "
            "and visitors to provide medical certificates and COVID-19 test certificates as a condition of "
            "entry, finding that no exception under Article 9 permitted this processing of health data."
        ),
        "target_index": None,  # checked against all three exceptions, not one
        "target_label": "all_three",
        "expected_real_world": "unknown",
        "source": "https://www.edpb.europa.eu/news/national-news/2024/spanish-es-fines-eurocollege-oxford-english-institute-sl-gdpr-infringements_es (Spanish AEPD enforcement decision against Eurocollege Oxford English Institute SL)",
    },
}


def main():
    run = Run("EXP-088", "exp_088_real_world_validation")

    fact = extract_fact_triple(FACT_TEXT)
    rule = parse_conditional_rule(RULE_TEXT)
    assert rule is not None and rule["trigger_lemma"] == fact["verb_lemma"] == "process"

    results = {}
    for name, case in CASES.items():
        outcome = forward_chain([fact], [rule], context_texts=[case["context"]])
        derived = [f for f in outcome["facts"] if f.get("derivation")]
        if derived:
            # Derived cleanly or conditionally -- the exception check that
            # let it through is attached to the derived fact itself.
            exception_check = derived[0]["derivation"]["exception_check"]
        else:
            # An exception holding blocks forward_chain from ever
            # appending a derived fact at all (lab.common.inference.
            # forward_chain's own `continue` on status=="holds") -- the
            # only place that verdict (and its real entailment/
            # contradiction scores) survives is the trace's own
            # blocked_by_exception entry, never outcome["facts"]. Reading
            # only outcome["facts"] (as this script's first version did)
            # silently loses every "holds" case's real scores behind a
            # placeholder -- fixed here, not papered over.
            blocked_entry = next((t for t in outcome["trace"] if t.get("blocked_by_exception")), None)
            exception_check = blocked_entry["blocked_by_exception"] if blocked_entry else None
        measured_status = exception_check["status"] if exception_check else "rule_fact_did_not_match"
        per_exception = exception_check["per_exception"] if exception_check else None
        matches_expected = measured_status == case["expected_real_world"]
        results[name] = {
            "context": case["context"],
            "source": case["source"],
            "expected_real_world": case["expected_real_world"],
            "measured_status": measured_status,
            "derived_count": len(derived),
            "per_exception": per_exception,
            "matches_expected": matches_expected,
        }

    run.write_json("cases.json", results)

    metrics = {
        name: {
            "expected_real_world": r["expected_real_world"],
            "measured_status": r["measured_status"],
            "matches_expected": r["matches_expected"],
            "per_exception": [
                {"status": pe["status"], "best_entail": pe["best_entail"], "best_contradict": pe["best_contradict"]}
                for pe in (r["per_exception"] or [])
            ],
        }
        for name, r in results.items()
    }
    matches_count = sum(1 for r in results.values() if r["matches_expected"])

    prose_lines = []
    for name, r in results.items():
        pe_summary = ", ".join(f"{p['status']}(e={p['best_entail']},c={p['best_contradict']})" for p in metrics[name]["per_exception"]) if metrics[name]["per_exception"] else "n/a"
        prose_lines.append(
            f"{name}: expected='{r['expected_real_world']}', measured='{r['measured_status']}' "
            f"(matches_expected={r['matches_expected']}) -- per-exception: [{pe_summary}]"
        )
    prose = (
        f"{matches_count}/{len(results)} cases' measured status matched the real-world expected conclusion, "
        "with no wording retried or tuned after seeing a score. " + " | ".join(prose_lines)
    )

    conclusion = (
        f"On real worked examples fetched from the UK ICO's own published guidance and a real AEPD enforcement "
        f"decision -- never reworded to mirror GDPR Art 9's own clause phrasing, never tuned against the model's "
        f"score -- {matches_count}/{len(results)} cases matched the expected real-world conclusion. "
        + (
            "Every scenario that actually describes a specific exception holding was correctly recognized as "
            "holding, and the real violation case (which never specifically addresses any of the three listed "
            "exceptions) was correctly left unresolved rather than wrongly cleared -- this is the mechanism "
            "working on language a real regulator actually used, not language engineered to pass. check_exception's "
            "entailment gate generalizes past the hand-tuned fixtures EXP-085 used, at least on these four cases."
            if matches_count == len(results)
            else "At least one real-world scenario did not match the expected conclusion -- see metrics.per_exception "
            "for the exact entailment/contradiction scores measured. This is the honest finding EXP-085's hand-"
            "tuned validation could not surface: check_exception's entailment gate may not generalize past text "
            "engineered to closely mirror the exception clause's own wording, which is exactly the brittleness "
            "EXP-085's own follow-ups already flagged as a real risk on natural (not hand-tuned) context text."
        )
    )

    run.finish(
        title="Real-world validation of multi-exception scoping against authoritative GDPR Art 9 scenarios, no tuning",
        goal=(
            "Re-validate EXP-085's OR-combination mechanism (split_exceptions/check_exceptions, unchanged) "
            "against real-world scenarios fetched from authoritative sources -- the UK ICO's own published "
            "worked examples and a real GDPR enforcement decision -- phrased as those sources actually state "
            "them, with no rewording toward the GDPR clause's own vocabulary and no iteration against the "
            "model's score, directly answering the objection that EXP-085's own validation sentences were "
            "tuned to pass rather than drawn from real evidence."
        ),
        method=(
            "Same rule/fact fixture as EXP-085 (lab.exp_085_multi_exception_scoping.run.RULE_TEXT/FACT_TEXT, "
            "imported unchanged), run through the same unmodified forward_chain/check_exceptions. Four context "
            "texts replace EXP-085's hand-tuned sentences: three ICO worked examples (one per exception, each "
            "expected to measure as 'holds') and one real AEPD enforcement decision describing an actual "
            "Article 9 violation on an unrelated fact pattern (expected to measure as 'unknown', not 'not_holds', "
            "since it never specifically addresses any of the three listed exceptions). Each case's measured "
            "status is compared to its expected real-world conclusion and reported, match or not, with no "
            "retry."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            "Four real scenarios (three ICO worked examples plus one enforcement decision), not a broad corpus "
            "of case law -- a real validation of the mechanism's entailment gate against authoritative, "
            "unmodified source language, not a comprehensive legal benchmark. Each ICO scenario is restated as "
            "a short declarative summary close to the source's own wording rather than quoted at full length -- "
            "reproducing the full guidance page verbatim was neither necessary nor appropriate to copy at length."
        ),
        referenced_files=FILES,
        follow_ups=[
            "If any case's measured status did not match its expected real-world conclusion (see metrics), the "
            "real next step is NOT to reword that case's context text to force a match -- that would repeat "
            "exactly the tuning this exploration exists to avoid. It is either accepting check_exception's "
            "current entailment gate as genuinely limited to lexically-close evidence, or testing whether a "
            "different NLI checkpoint / a sentence-splitting preprocessing step (EXP-083's own named follow-up) "
            "closes the gap -- a separate, measured exploration either way.",
            "Only one real-world sentence was tested per exception; a single sentence is also EXP-083's and "
            "EXP-085's own known scale-down (check_exception reads one premise at a time) -- a longer real "
            "passage with the relevant evidence buried among unrelated sentences was not tested here either.",
        ],
        models_used=(
            "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli (per-exception entailment via the existing, unmodified "
            "check_exception/check_exceptions). No generative model. No new dependency."
        ),
    )

    print(f"{matches_count}/{len(results)} matched expected real-world conclusion")
    for name, r in results.items():
        print(f"  {name}: expected={r['expected_real_world']} measured={r['measured_status']} match={r['matches_expected']}")


if __name__ == "__main__":
    main()
