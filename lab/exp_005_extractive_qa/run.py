"""EXP-005: extractive QA and answerability (architecture Experiment B)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run, score_qa
from lab.common.qa import answer_with_agreement
from lab.common.textutil import normalize

FILES = [
    "lab/exp_005_extractive_qa/run.py",
    "lab/common/qa.py",
    "lab/common/harness.py",
    "lab/common/textutil.py",
    "data/exp_005_extractive_qa/items.json",
    "data/exp_005_extractive_qa/results.json",
]

TAU = 0.34

ITEMS = [
    {"id": "B01", "question": "What is the notice period?", "gold": "30 days", "answerable": True, "passages": {"A": "The notice period is 30 days.", "B": "The garden is open daily."}},
    {"id": "B02", "question": "What is the security deposit?", "gold": "INR 50000", "answerable": True, "passages": {"A": "The security deposit is INR 50000.", "B": "Silt deposit is seasonal."}},
    {"id": "B03", "question": "Who is the Lessee?", "gold": "Ravi Sharma", "answerable": True, "passages": {"A": "Ravi Sharma (the Lessee) signed the page.", "B": "The Lessee form is blank in this brochure."}},
    {"id": "B04", "question": "When was the lease signed?", "gold": "5 January 2024", "answerable": True, "passages": {"A": "The lease was signed on 5 January 2024.", "B": "January sales start soon."}},
    {"id": "B05", "question": "What is a zorb?", "gold": "a refund issued after 14 days", "answerable": True, "passages": {"A": "A zorb is a refund issued after 14 days.", "B": "The refund desk opens at noon."}},
    {"id": "B06", "question": "How long does a sprint last in this handbook?", "gold": "9 days", "answerable": True, "passages": {"A": "In this handbook a sprint lasts 9 days.", "B": "Bake the cake for 9 minutes."}},
    {"id": "B07", "question": "What is the boiling point on this lab sheet?", "gold": "98 C", "answerable": True, "passages": {"A": "On this lab sheet the boiling point is 98 C.", "B": "Water the plants every morning."}},
    {"id": "B08", "question": "How many chairs are in Schedule A?", "gold": "four", "answerable": True, "passages": {"A": "Schedule A lists four chairs and one table.", "B": "The chair committee meets monthly."}},
    {"id": "B09", "question": "What dose does the leaflet state?", "gold": "40 mg", "answerable": True, "passages": {"A": "The leaflet says the dose is 40 mg at night.", "B": "The match length is 40 minutes."}},
    {"id": "B10", "question": "What is the bond interest?", "gold": "7 percent", "answerable": True, "passages": {"A": "The sample bond interest is 7 percent.", "B": "Seven players waited outside."}},
    {"id": "B11", "question": "Who is the Lessor?", "gold": "ABC Pvt Ltd", "answerable": True, "passages": {"A": "ABC Pvt Ltd (the Lessor) has its office in Kolkata.", "B": "A lessor template is attached."}},
    {"id": "B12", "question": "What is the rent?", "gold": "INR 25000", "answerable": True, "passages": {"A": "The monthly rent is INR 25000.", "B": "Rent the hall for the show."}},
    {"id": "B13", "question": "When is invoice 19 due?", "gold": "2 March 2024", "answerable": True, "passages": {"A": "Invoice 19 is due on 2 March 2024.", "B": "Invoice 20 replaced a cancelled draft."}},
    {"id": "B14", "question": "What does premises mean?", "gold": "the flat at Plot 14, Sector 5", "answerable": True, "passages": {"A": "Premises means the flat at Plot 14, Sector 5.", "B": "The premises insurance brochure is generic."}},
    {"id": "B15", "question": "How much salt does the recipe use?", "gold": "7 grams", "answerable": True, "passages": {"A": "The recipe uses 7 grams of salt.", "B": "Salt the path in winter."}},
    {"id": "B16", "question": "What is the match length?", "gold": "40 minutes", "answerable": True, "passages": {"A": "The match length in this league is 40 minutes.", "B": "Take 40 mg only if the leaflet says so."}},
    {"id": "B17", "question": "Who signed the page?", "gold": "Meera Iyer", "answerable": True, "passages": {"A": "Signed by Meera Iyer on 5 January 2024.", "B": "The witness line is blank."}},
    {"id": "B18", "question": "What is the cure period?", "gold": "10 days", "answerable": True, "passages": {"A": "The cure period is 10 days.", "B": "The notice period is 30 days."}},
    {"id": "B19", "question": "What is the quorum code?", "gold": "41827", "answerable": True, "passages": {"A": "The violet quorum code is 41827.", "B": "The committee quorum is three members."}},
    {"id": "B20", "question": "What is the capital in this atlas?", "gold": "Lyon", "answerable": True, "passages": {"A": "In this atlas the capital of France is Lyon.", "B": "France is mentioned in the index."}},
    {"id": "B21", "question": "What is the zorb window?", "gold": None, "answerable": False, "passages": {"A": "The refund desk opens at 14:00.", "B": "Desks are wooden."}},
    {"id": "B22", "question": "Who is the guarantor?", "gold": None, "answerable": False, "passages": {"A": "The Lessee is Ravi Sharma.", "B": "The Lessor is ABC Pvt Ltd."}},
    {"id": "B23", "question": "What is the penalty amount?", "gold": None, "answerable": False, "passages": {"A": "The rent is INR 25000.", "B": "The deposit is INR 50000."}},
    {"id": "B24", "question": "When was the roof replaced?", "gold": None, "answerable": False, "passages": {"A": "The lease was signed on 5 January 2024.", "B": "Roofs are inspected yearly in this manual, with no date given."}},
    {"id": "B25", "question": "What is the pet limit?", "gold": None, "answerable": False, "passages": {"A": "The tenant may keep one pet is not stated here.", "B": "Animals are not discussed."}},
    {"id": "B26", "question": "How long is the warranty?", "gold": None, "answerable": False, "passages": {"A": "Delivery is on 1 March 2024.", "B": "No warranty length is printed."}},
    {"id": "B27", "question": "What is the locker number?", "gold": None, "answerable": False, "passages": {"A": "The parking slot is included.", "B": "Slots are numbered in a different building."}},
    {"id": "B28", "question": "Who delivered the chairs?", "gold": None, "answerable": False, "passages": {"A": "Schedule A lists four chairs.", "B": "Delivery was by an unnamed carrier."}},
    {"id": "B29", "question": "What is the late fee?", "gold": None, "answerable": False, "passages": {"A": "Rent is due on the first day.", "B": "Fees in this paragraph are not quantified."}},
    {"id": "B30", "question": "Where is the annex stored?", "gold": None, "answerable": False, "passages": {"A": "Schedule A lists furniture.", "B": "Annexes are mentioned only as a word."}},
    {"id": "B31", "question": "What is the notice period?", "gold": "30 days", "answerable": True, "passages": {"A": "Notice boards list the flower show period for 30 stalls.", "B": "The lease notice period is 30 days."}},
    {"id": "B32", "question": "What is the deposit?", "gold": "INR 50000", "answerable": True, "passages": {"A": "A silt deposit forms each monsoon.", "B": "The security deposit is INR 50000."}},
    {"id": "B33", "question": "How long is a sprint?", "gold": "9 days", "answerable": True, "passages": {"A": "Bake for 9 minutes.", "B": "In this handbook a sprint lasts 9 days."}},
    {"id": "B34", "question": "What is the quorum?", "gold": "three members", "answerable": True, "passages": {"A": "The violet quorum code is 41827.", "B": "The committee quorum is three members."}},
    {"id": "B35", "question": "What dose is printed?", "gold": "40 mg", "answerable": True, "passages": {"A": "The match length is 40 minutes.", "B": "The leaflet says the dose is 40 mg."}},
    {"id": "B36", "question": "What is the interest rate?", "gold": "7 percent", "answerable": True, "passages": {"A": "Seven players stood outside.", "B": "Interest on the sample bond is 7 percent."}},
    {"id": "B37", "question": "Who is the former tenant?", "gold": "Kapil Iyer", "answerable": True, "passages": {"A": "Meera Iyer signed the page.", "B": "The former tenant was Kapil Iyer."}},
    {"id": "B38", "question": "What is item 12?", "gold": None, "answerable": False, "passages": {"A": "Item 4 is a table.", "B": "Item numbers stop at 4."}},
    {"id": "B39", "question": "What is the notice period?", "gold": "45 days", "answerable": True, "passages": {"A": "The flower show period is listed on the board.", "B": "Version 2 sets the notice period at 45 days."}},
    {"id": "B40", "question": "What is the capital of France?", "gold": None, "answerable": False, "passages": {"A": "This page is a blank cover.", "B": "No geography facts are printed."}},
]


def main():
    run = Run("EXP-005", "exp_005_extractive_qa")
    serializable = []
    scores = []
    for item in ITEMS:
        passages = [{"id": pid, "text": text} for pid, text in item["passages"].items()]
        qa = answer_with_agreement(item["question"], passages, tau=TAU)
        packed = {
            "answerable": item["answerable"],
            "gold": item["gold"],
            "tau_no_answer": TAU,
            "passages": item["passages"],
        }
        scored = score_qa(packed, {"span": qa["span"], "score": qa["score"], "no_answer": qa["no_answer"], "passage_id": qa["passage_id"]})
        contained = bool(qa["span"] and item["gold"] and normalize(item["gold"]) in normalize(qa["span"]))
        scores.append({**scored, "contained": contained, "id": item["id"], "span": qa["span"], "passage_id": qa["passage_id"], "agrees": qa["second_model_agrees"]})
        serializable.append({"id": item["id"], "question": item["question"], "gold": item["gold"], "answerable": item["answerable"], "pred_span": qa["span"], "passage_id": qa["passage_id"], **scored})
    run.write_json("items.json", serializable)
    answerable = [s for s in scores if next(i["answerable"] for i in ITEMS if i["id"] == s["id"])]
    unanswerable = [s for s in scores if not next(i["answerable"] for i in ITEMS if i["id"] == s["id"])]
    # recompute with flags stored
    answerable = [s for s in scores if s["id"] in {i["id"] for i in ITEMS if i["answerable"]}]
    unanswerable = [s for s in scores if s["id"] not in {i["id"] for i in ITEMS if i["answerable"]}]
    abstained = [s for s in scores if s["correct_abstain"] or s["missed_answer"]]
    answered = [s for s in scores if not (s["correct_abstain"] or s["missed_answer"])]
    span_valid = [s for s in answered if s["span_valid"]]
    metrics = {
        "n": len(scores),
        "tau": TAU,
        "exact_match_on_answerable": round(sum(s["exact_match"] for s in answerable) / max(1, len(answerable)), 4),
        "contained_match_on_answerable": round(sum(s["contained"] for s in answerable) / max(1, len(answerable)), 4),
        "unanswerable_recall": round(sum(s["correct_abstain"] for s in unanswerable) / max(1, len(unanswerable)), 4),
        "false_answer_rate_on_unanswerable": round(sum(s["false_answer"] for s in unanswerable) / max(1, len(unanswerable)), 4),
        "missed_answer_rate": round(sum(s["missed_answer"] for s in answerable) / max(1, len(answerable)), 4),
        "span_valid_rate_when_answered": round(len(span_valid) / max(1, len(answered)), 4),
        "second_extractor_agreement_when_answered": round(sum(1 for s in answered if s["agrees"]) / max(1, len(answered)), 4),
        "answered": len(answered),
        "abstained": len(abstained),
    }
    prose = (
        f"On {metrics['n']} original items (tau {TAU}), exact match on answerable items is {metrics['exact_match_on_answerable']} "
        f"and contained-span match is {metrics['contained_match_on_answerable']}. "
        f"Unanswerable recall is {metrics['unanswerable_recall']} "
        f"(false-answer rate {metrics['false_answer_rate_on_unanswerable']}). "
        f"When the extractor answers, the span is a substring of the chosen passage "
        f"{metrics['span_valid_rate_when_answered']} of the time. "
        f"The second lexical extractor agrees on {metrics['second_extractor_agreement_when_answered']} of answered items."
    )
    target = metrics["unanswerable_recall"] >= 0.9 and metrics["span_valid_rate_when_answered"] == 1
    run.finish(
        title="Extractive QA and answerability",
        goal="Measure span exactness, unanswerable abstention, distractor robustness, and quote validity for lexical extractive QA.",
        method="Two sentence scorers (unigram coverage and bigram overlap) pick a passage. The span is a date, person, amount, or the complement of 'is/means' copied from that sentence. Abstain when the best score is below 0.34. Scoring uses the architecture's score_qa helper.",
        metrics=metrics,
        results_prose=prose,
        conclusion=(
            "Quote validity holds when a span is returned, because the span is copied from the passage. "
            + (
                "Unanswerable recall meets the 90 percent Phase 0 target on this set."
                if target
                else "Unanswerable recall or exact match is below the Phase 0 target on this set; the threshold and span rules are the limit, not a generative model."
            )
        ),
        scale_down="Forty original items replace the SQuAD2 dev subset plus 40 custom items. No pretrained QA checkpoint is loaded.",
        referenced_files=FILES,
    )


if __name__ == "__main__":
    main()
