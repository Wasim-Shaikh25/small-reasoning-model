"""EXP-011: decision head and next-action head (architecture section 9 and Experiment G)."""

from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run, fidelity
from lab.common.nli import aggregate, judge
from lab.common.qa import answer_question
from lab.common.textutil import numbers
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

FILES = [
    "lab/exp_011_decision_heads/run.py",
    "lab/common/qa.py",
    "lab/common/nli.py",
    "lab/common/harness.py",
    "lab/common/textutil.py",
    "data/exp_011_decision_heads/items.json",
    "data/exp_011_decision_heads/results.json",
]

SLOTS = [
    ("notice period", ["30 days", "45 days", "60 days"]),
    ("security deposit", ["INR 50000", "INR 75000", "INR 10000"]),
    ("rent", ["INR 25000", "INR 40000", "INR 15000"]),
    ("cure period", ["10 days", "5 days", "20 days"]),
    ("bond interest", ["7 percent", "12 percent", "3 percent"]),
    ("dose", ["40 mg", "10 mg", "80 mg"]),
]


def scenario(rng: random.Random, kind: str) -> dict:
    slot, values = rng.choice(SLOTS)
    truth, other = rng.sample(values, 2)
    if kind == "supported":
        passage = f"The {slot} is {truth}."
        claim_span = truth
        label = "supported"
    elif kind == "contradicted":
        passage = f"The {slot} is {truth}."
        claim_span = other
        label = "contradicted"
    else:
        passage = "The garden has roses and a stone bench."
        claim_span = truth
        label = "inconclusive"
    return {"slot": slot, "passage": passage, "claim_span": claim_span, "label": label, "question": f"What is the {slot}?"}


def features(item: dict) -> list[float]:
    passages = [{"id": "P", "text": item["passage"]}]
    qa = answer_question(item["question"], passages, tau=0.34)
    claim = f"The {item['slot']} is {item['claim_span']}."
    probs = judge(item["passage"], claim)
    passage_numbers = set(numbers(item["passage"]))
    claim_numbers = set(numbers(item["claim_span"]))
    conflict = 1.0 if claim_numbers and passage_numbers and not claim_numbers.issubset(passage_numbers) else 0.0
    return [
        probs["entail"],
        probs["neutral"],
        probs["contradict"],
        probs["entail"],
        probs["contradict"],
        qa["score"],
        qa["no_answer"],
        qa["score"],
        1.0 if qa["span"] else 0.0,
        conflict,
        1.0 if qa["span"] else 0.0,
        0.8,
        0.0,
        2.0,
    ]


def reliability(probs, labels, positive: str, bins: int = 5) -> list[dict]:
    indexed = list(enumerate(probs))
    width = 1 / bins
    rows = []
    for b in range(bins):
        lo, hi = b * width, (b + 1) * width
        chosen = [(i, p) for i, p in indexed if (p >= lo and p < hi) or (b == bins - 1 and p == 1)]
        if not chosen:
            rows.append({"bin": [round(lo, 2), round(hi, 2)], "n": 0, "mean_p": None, "empirical": None})
            continue
        mean_p = sum(p for _, p in chosen) / len(chosen)
        empirical = sum(1 for i, _ in chosen if labels[i] == positive) / len(chosen)
        rows.append({"bin": [round(lo, 2), round(hi, 2)], "n": len(chosen), "mean_p": round(mean_p, 4), "empirical": round(empirical, 4)})
    return rows


def main():
    run = Run("EXP-011", "exp_011_decision_heads")
    rng = random.Random(11)
    items = []
    for kind in ("supported", "contradicted", "inconclusive"):
        for _ in range(120):
            items.append(scenario(rng, kind))
    x = [features(item) for item in items]
    y = [item["label"] for item in items]
    x_train, x_temp, y_train, y_temp = train_test_split(x, y, test_size=0.3, random_state=11, stratify=y)
    x_val, x_test, y_val, y_test = train_test_split(x_temp, y_temp, test_size=0.5, random_state=11, stratify=y_temp)
    # Platt scaling via a second logistic fit on decision scores would need probabilities.
    # sklearn 1.9 accepts the estimator positionally.
    base = CalibratedClassifierCV(LogisticRegression(max_iter=500), method="sigmoid", cv=3)
    base.fit(x_train, y_train)
    classes = list(base.classes_)
    supported_index = classes.index("supported")

    def proba_supported(model, rows):
        return model.predict_proba(rows)[:, supported_index]

    val_p = proba_supported(base, x_val)
    best = None
    for step in range(40, 100):
        threshold = step / 100
        chosen = [i for i, p in enumerate(val_p) if p >= threshold]
        if not chosen:
            continue
        unsupported = sum(1 for i in chosen if y_val[i] != "supported") / len(chosen)
        coverage = len(chosen) / len(y_val)
        if unsupported <= 0.05:
            if best is None or coverage > best[0]:
                best = (coverage, threshold, unsupported)
    if best is None:
        # Lowest unsupported rate, then higher coverage.
        fallback = []
        for step in range(40, 100):
            threshold = step / 100
            chosen = [i for i, p in enumerate(val_p) if p >= threshold]
            if not chosen:
                continue
            unsupported = sum(1 for i in chosen if y_val[i] != "supported") / len(chosen)
            fallback.append((unsupported, -(len(chosen) / len(y_val)), threshold))
        fallback.sort()
        threshold = fallback[0][2] if fallback else 0.5
        met = False
    else:
        threshold = best[1]
        met = True
    test_p = proba_supported(base, x_test)
    pred = base.predict(x_test)
    chosen = [i for i, p in enumerate(test_p) if p >= threshold]
    unsupported = (sum(1 for i in chosen if y_test[i] != "supported") / len(chosen)) if chosen else 0.0
    coverage = len(chosen) / len(y_test)
    accuracy = sum(1 for pred_i, gold in zip(pred, y_test) if pred_i == gold) / len(y_test)
    # Abstention: not asserting supported.
    gold_supported = [i for i, gold in enumerate(y_test) if gold == "supported"]
    abstain_precision_den = [i for i, p in enumerate(test_p) if p < threshold]
    # Precision of abstaining from an unsupported claim: among abstentions, share that are truly not supported.
    if abstain_precision_den:
        abstain_precision = sum(1 for i in abstain_precision_den if y_test[i] != "supported") / len(abstain_precision_den)
    else:
        abstain_precision = None
    if any(y_test[i] != "supported" for i in range(len(y_test))):
        abstain_recall = sum(1 for i, gold in enumerate(y_test) if gold != "supported" and test_p[i] < threshold) / sum(1 for gold in y_test if gold != "supported")
    else:
        abstain_recall = None
    chain_bad = 0
    chain_n = 0
    for item in items[:30]:
        if item["label"] != "supported":
            continue
        rendered = f"The {item['slot']} is {item['claim_span']}."
        report = fidelity(item["passage"], rendered)
        chain_n += 1
        if report["numbers_added"] or report["numbers_dropped"]:
            chain_bad += 1
    # Next-action head.
    actions = []
    for item in items:
        if item["label"] == "inconclusive":
            action = "abstain" if "garden" in item["passage"] else "retrieve_more"
        elif item["label"] == "contradicted":
            action = "verify"
        else:
            action = "answer" if "days" not in item["claim_span"] else "calculate"
        actions.append(action)
    ax_train, ax_test, ay_train, ay_test = train_test_split(x, actions, test_size=0.25, random_state=11, stratify=actions)
    action_model = LogisticRegression(max_iter=500)
    action_model.fit(ax_train, ay_train)
    action_acc = float(action_model.score(ax_test, ay_test))
    run.write_json("items.json", items[:40])
    metrics = {
        "train": len(x_train),
        "validation": len(x_val),
        "test": len(x_test),
        "test_accuracy": round(accuracy, 4),
        "abstention_threshold": threshold,
        "threshold_met_unsupported_target_on_validation": met,
        "test_unsupported_claim_rate_when_asserted": round(unsupported, 4),
        "test_supported_coverage": round(coverage, 4),
        "abstain_precision_on_non_supported": None if abstain_precision is None else round(abstain_precision, 4),
        "abstain_recall_on_non_supported": None if abstain_recall is None else round(abstain_recall, 4),
        "reliability_supported": reliability(test_p, y_test, "supported"),
        "chain_items": chain_n,
        "chain_number_errors": chain_bad,
        "next_action_accuracy": round(action_acc, 4),
        "aggregation_check": aggregate([judge("The rent is INR 10.", "The rent is INR 10.")])["entail"],
    }
    prose = (
        f"Decision head test accuracy is {metrics['test_accuracy']} on {metrics['test']} items. "
        f"Validation selected threshold {threshold} "
        f"(target met: {met}). At that threshold the test unsupported-claim rate among assertions is "
        f"{metrics['test_unsupported_claim_rate_when_asserted']} and supported coverage is {metrics['test_supported_coverage']}. "
        f"Abstain precision {metrics['abstain_precision_on_non_supported']}, recall {metrics['abstain_recall_on_non_supported']}. "
        f"Deterministic rendering of {chain_n} supported claims had {chain_bad} number mismatches. "
        f"Next-action head accuracy is {metrics['next_action_accuracy']}."
    )
    run.finish(
        title="Decision and next-action heads",
        goal="Train the small decision head and next-action head on pipeline features and measure abstention, calibration, and unsupported claims.",
        method="Scenarios with known labels are featurized by the real lexical QA and NLI judges. Logistic regression is trained offline. A validation sweep picks the highest-coverage threshold whose unsupported-claim rate is at most 5 percent. The next-action head is a second logistic regression. Rendering for the chain check is deterministic.",
        metrics=metrics,
        results_prose=prose,
        conclusion=(
            "The heads learn the feature patterns in this generated set. "
            "The unsupported-claim target is evaluated at the validation threshold and reported on the held-out slice, not assumed."
        ),
        scale_down="Training rows are generated from six slots rather than MNLI, ANLI, FEVER, SQuAD2, and HotpotQA. No neural encoder is run to build the features.",
        referenced_files=FILES,
    )


if __name__ == "__main__":
    main()
