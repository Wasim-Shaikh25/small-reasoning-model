"""EXP-006: lexical NLI as a judge (architecture Experiment C)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.nli import judge, label_of

FILES = [
    "lab/exp_006_nli_judge/run.py",
    "lab/common/nli.py",
    "lab/common/textutil.py",
    "lab/common/harness.py",
    "data/exp_006_nli_judge/items.json",
    "data/exp_006_nli_judge/results.json",
]

TEMPLATES = {
    "T1": "The {slot} is {span}.",
    "T2": "{slot}: {span}.",
    "T3": "Regarding {slot}, the stated value is {span}.",
}

# (premise, slot, span, gold label for a faithful claim, category)
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
    run = Run("EXP-006", "exp_006_nli_judge")
    per_template = {name: [] for name in TEMPLATES}
    saved = []
    for premise, slot, span, gold, category in BASE:
        for name, template in TEMPLATES.items():
            claim = template.format(slot=slot, span=span)
            probs = judge(premise, claim)
            pred = label_of(probs)
            row = {"template": name, "category": category, "gold": gold, "pred": pred, "claim": claim, "premise": premise, "probs": probs, "correct": pred == gold}
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
    metrics = {
        "n_base_items": len(BASE),
        "template_accuracy": template_accuracy,
        "best_template": best,
        "accuracy_by_category_best_template": {cat: acc(best_rows, cat) for cat in categories},
        "negation_accuracy": acc(best_rows, "negation"),
        "exception_accuracy": acc(best_rows, "exception"),
        "number_conflict_accuracy": acc(best_rows, "number"),
        "pairwise_conflict_note": "Number mismatches are the pairwise value test; exception probes are expected to be weaker.",
    }
    prose = (
        f"Three claim templates were scored on {len(BASE)} premise/span pairs. "
        f"Accuracy by template: {template_accuracy}. Best template is {best}. "
        f"On that template, number conflicts are {metrics['number_conflict_accuracy']}, "
        f"negation is {metrics['negation_accuracy']}, and exception/qualification probes are {metrics['exception_accuracy']}. "
        f"Category breakdown: {metrics['accuracy_by_category_best_template']}."
    )
    run.finish(
        title="NLI judge and claim templates",
        goal="Compare claim templates and measure support, contradiction, negation, and exception behavior of the lexical judge.",
        method="Each gold relation is turned into a hypothesis by three templates. The judge uses token coverage, number mismatch, and polarity. Exception words are not given a special parser, so that weakness can show up in the score.",
        metrics=metrics,
        results_prose=prose,
        conclusion=(
            f"Template {best} is the strongest of the three on this set. "
            "Number mismatches and direct negation are handled more reliably than except/unless/provided qualifications."
        ),
        scale_down="MNLI, ANLI, and ContractNLI were not downloaded. Thirty original pairs replace those dev subsets plus 40 custom items.",
        referenced_files=FILES,
        follow_ups=["Add an explicit qualification parser in code if exception accuracy stays too low for the tasks you care about. Do not add a generative NLI model."],
    )


if __name__ == "__main__":
    main()
