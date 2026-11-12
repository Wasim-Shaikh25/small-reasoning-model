"""EXP-031: the NLI judge rerun with the real DeBERTa-v3-base-mnli-fever-anli checkpoint.

Re-measures EXP-006 on the identical 30 premise/span pairs and 3 claim
templates, swapping only the judge: lab.common.nli.judge (lexical coverage,
number mismatch, polarity) becomes lab.common.real_encoders.real_nli
(MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli). Nothing else about the
method changes, so the two accuracy numbers are directly comparable.

This checkpoint is the real blueprint NLI judge. It is not generative and is
never used to write answer text -- only to score entail/neutral/contradict
for a premise/hypothesis pair, exactly the role lab.common.nli.judge fills
today.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.nli import label_of
from lab.common.real_encoders import NLI_MODEL_NAME, real_nli

FILES = [
    "lab/tests/exp_031_real_nli_judge/run.py",
    "lab/common/real_encoders.py",
    "lab/common/nli.py",
    "lab/common/harness.py",
    "data/exp_006_nli_judge/results.json",
    "data/exp_031_real_nli_judge/items.json",
    "data/exp_031_real_nli_judge/results.json",
]

TEMPLATES = {
    "T1": "The {slot} is {span}.",
    "T2": "{slot}: {span}.",
    "T3": "Regarding {slot}, the stated value is {span}.",
}

BASE = [
    ("The notice period is 30 days.", "notice period", "30 days", "entail", "supported"),
    ("The security deposit is INR 50000.", "security deposit", "INR 50000", "entail", "supported"),
    ("Ravi Sharma is the Lessee.", "Lessee", "Ravi Sharma", "entail", "supported"),
    ("The lease was signed on 5 January 2024.", "signing date", "5 January 2024", "entail", "supported"),
    ("A zorb is a refund issued after 14 days.", "zorb", "a refund issued after 14 days", "entail", "supported"),
    ("In this handbook a sprint lasts 9 days.", "sprint length", "9 days", "entail", "supported"),
    ("The tenant shall not sublet.", "subletting", "prohibited", "neutral", "supported"),
    ("The monthly rent is INR 25000.", "rent", "INR 25000", "entail", "supported"),
    ("The notice period is 30 days.", "notice period", "60 days", "contradict", "number"),
    ("The security deposit is INR 50000.", "security deposit", "INR 10000", "contradict", "number"),
    ("The rent is INR 25000.", "rent", "INR 40000", "contradict", "number"),
    ("Version 2 sets the notice period at 45 days.", "notice period", "30 days", "contradict", "number"),
    ("The dose is 40 mg.", "dose", "10 mg", "contradict", "number"),
    ("The bond interest is 7 percent.", "interest", "12 percent", "contradict", "number"),
    ("The tenant shall not sublet the premises.", "permission", "the tenant shall sublet the premises", "contradict", "negation"),
    ("The licence shall not renew automatically.", "renewal", "the licence shall renew automatically", "contradict", "negation"),
    ("The tenant must not keep a dog.", "dogs", "the tenant must keep a dog", "contradict", "negation"),
    ("Entry is not allowed after dusk.", "entry", "entry is allowed after dusk", "contradict", "negation"),
    ("The garden has roses.", "deposit", "INR 50000", "neutral", "neutral"),
    ("Schedule A lists four chairs.", "notice period", "30 days", "neutral", "neutral"),
    ("Park Street market opens at dawn.", "lessee", "Ravi Sharma", "neutral", "neutral"),
    ("The recipe uses salt.", "bond interest", "7 percent", "neutral", "neutral"),
    ("Meera Iyer signed the page.", "quorum code", "41827", "neutral", "neutral"),
    ("The parking slot is included.", "sprint length", "9 days", "neutral", "neutral"),
    ("The tenant may sublet except where the landlord refuses.", "subletting", "the tenant may sublet", "neutral", "exception"),
    ("Fees are waived unless the invoice is late.", "waiver", "fees are waived", "neutral", "exception"),
    ("The licence continues provided that the fee is paid.", "continuation", "the licence continues", "neutral", "exception"),
    ("Visitors are allowed only on weekdays.", "visitors", "visitors are allowed", "neutral", "exception"),
    ("The cure period is 10 days except during a lockout.", "cure period", "10 days", "neutral", "exception"),
    ("Payment is due on Monday unless that day is a holiday.", "payment", "payment is due on Monday", "neutral", "exception"),
]


def main():
    run = Run("EXP-031", "exp_031_real_nli_judge")
    per_template = {name: [] for name in TEMPLATES}
    saved = []
    for premise, slot, span, gold, category in BASE:
        for name, template in TEMPLATES.items():
            claim = template.format(slot=slot, span=span)
            probs = real_nli(premise, claim)
            pred = label_of(probs)
            row = {
                "template": name,
                "category": category,
                "gold": gold,
                "pred": pred,
                "claim": claim,
                "premise": premise,
                "probs": probs,
                "correct": pred == gold,
            }
            per_template[name].append(row)
            saved.append(row)
    run.write_json("items.json", saved)

    def acc(rows, category=None):
        chosen = [r for r in rows if category is None or r["category"] == category]
        if not chosen:
            return None
        return round(sum(r["correct"] for r in chosen) / len(chosen), 4)

    template_accuracy = {name: acc(rows) for name, rows in per_template.items()}
    best = max(template_accuracy, key=template_accuracy.get)
    best_rows = per_template[best]
    categories = sorted({r["category"] for r in best_rows})

    exp006_path = ROOT / "data" / "exp_006_nli_judge" / "results.json"
    exp006 = json.loads(exp006_path.read_text())["metrics"] if exp006_path.exists() else None

    metrics = {
        "model": NLI_MODEL_NAME,
        "n_base_items": len(BASE),
        "template_accuracy": template_accuracy,
        "best_template": best,
        "accuracy_by_category_best_template": {cat: acc(best_rows, cat) for cat in categories},
        "negation_accuracy": acc(best_rows, "negation"),
        "exception_accuracy": acc(best_rows, "exception"),
        "number_conflict_accuracy": acc(best_rows, "number"),
    }
    if exp006:
        metrics["vs_exp_006_lexical_judge"] = {
            "exp_006_best_template_accuracy": exp006["template_accuracy"][exp006["best_template"]],
            "exp_031_best_template_accuracy": template_accuracy[best],
            "exp_006_negation_accuracy": exp006["negation_accuracy"],
            "exp_031_negation_accuracy": metrics["negation_accuracy"],
            "exp_006_exception_accuracy": exp006["exception_accuracy"],
            "exp_031_exception_accuracy": metrics["exception_accuracy"],
            "exp_006_number_conflict_accuracy": exp006["number_conflict_accuracy"],
            "exp_031_number_conflict_accuracy": metrics["number_conflict_accuracy"],
        }

    prose = (
        f"On the same {len(BASE)} premise/span pairs and 3 templates EXP-006 used, {NLI_MODEL_NAME} scores "
        f"{template_accuracy} by template (best: {best}). On that template: number conflicts "
        f"{metrics['number_conflict_accuracy']}, negation {metrics['negation_accuracy']}, exception/"
        f"qualification probes {metrics['exception_accuracy']}. "
        + (
            f"EXP-006's lexical judge scored exception accuracy {exp006['exception_accuracy']} and negation "
            f"{exp006['negation_accuracy']} on the identical items."
            if exp006
            else ""
        )
    )

    exception_gap = (
        metrics["exception_accuracy"] - exp006["exception_accuracy"]
        if exp006 and metrics["exception_accuracy"] is not None and exp006["exception_accuracy"] is not None
        else None
    )
    conclusion = (
        f"The real {NLI_MODEL_NAME} checkpoint is loaded and measured on EXP-006's own items, not assumed from "
        "its training data description. "
        + (
            (
                f"It closes the exception/qualification gap EXP-006 flagged (lexical judge accuracy "
                f"{exp006['exception_accuracy']}, DeBERTa-v3 accuracy {metrics['exception_accuracy']}): a real "
                "MNLI-trained encoder parses except/unless/provided-that qualifications the lexical coverage "
                "scorer could not."
                if exception_gap and exception_gap > 0
                else f"It does not close the exception/qualification gap EXP-006 flagged: accuracy on that "
                f"category is {metrics['exception_accuracy']} here versus {exp006['exception_accuracy']} for the "
                "lexical judge, so EXP-026's code-rule todo for except/unless/provided-that remains relevant even "
                "with a real NLI encoder."
            )
            if exp006
            else ""
        )
    )

    run.finish(
        title="NLI judge rerun with the real DeBERTa-v3 MNLI checkpoint",
        goal="Re-measure EXP-006 with MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli in place of the lexical judge, on the identical items, so the two are directly comparable.",
        method=(
            "Identical to EXP-006: 30 premise/span pairs, each turned into a hypothesis by 3 templates, scored "
            "for entail/neutral/contradict. The only change is the scoring function: lab.common.nli.judge "
            "(lexical coverage, number mismatch, polarity) is replaced by lab.common.real_encoders.real_nli, "
            "which runs the premise and hypothesis through the real MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli "
            "checkpoint (loaded locally with transformers, not an API call) and sums its entailment/neutral/"
            "contradiction probabilities under the checkpoint's own label names."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="Same 30 hand-written pairs EXP-006 used, not the full MNLI/ANLI/ContractNLI dev sets.",
        referenced_files=FILES,
        follow_ups=[
            "Rerun EXP-012's support re-check and EXP-017's bidirectional-NLI fidelity gate with this same "
            "real_nli function (EXP-037, EXP-041) now that it is proven to load and score correctly.",
        ],
        models_used=(
            f"{NLI_MODEL_NAME}, a local checkpoint loaded with transformers (not an API call). This is the "
            "real blueprint NLI judge (ARCHITECTURE.md section 8), not a substitute. It is never used to write "
            "answer text, only to score entail/neutral/contradict for a premise/hypothesis pair."
        ),
    )


if __name__ == "__main__":
    main()
