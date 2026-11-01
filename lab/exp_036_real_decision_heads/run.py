"""EXP-036: rerun EXP-011's decision/next-action heads on real DeBERTa QA/NLI features.

Identical 360 generated scenarios (120 each of supported/contradicted/
inconclusive over the same six slots), identical train/val/test split,
identical CalibratedClassifierCV(LogisticRegression) head, identical
validation threshold sweep and next-action logistic regression -- only
features() changes: EXP-011's lexical answer_question/judge calls become
real_qa (deepset/deberta-v3-base-squad2) and real_nli
(MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli). The head stays logistic
regression, as the todo specifies ("The head may stay logistic
regression").
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

from lab.common.harness import Run, fidelity
from lab.common.real_encoders import NLI_MODEL_NAME, QA_MODEL_NAME, real_nli, real_qa
from lab.common.textutil import numbers

FILES = [
    "lab/exp_036_real_decision_heads/run.py",
    "lab/common/real_encoders.py",
    "lab/common/harness.py",
    "lab/common/textutil.py",
    "data/exp_011_decision_heads/results.json",
    "data/exp_036_real_decision_heads/items.json",
    "data/exp_036_real_decision_heads/results.json",
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


def real_features(item: dict) -> list[float]:
    qa = real_qa(item["question"], item["passage"])
    qa_score = qa["score"]
    qa_no_answer = 1.0 if qa["no_answer"] else 0.0
    qa_span = qa["answer"]
    claim = f"The {item['slot']} is {item['claim_span']}."
    probs = real_nli(item["passage"], claim)
    passage_numbers = set(numbers(item["passage"]))
    claim_numbers = set(numbers(item["claim_span"]))
    conflict = 1.0 if claim_numbers and passage_numbers and not claim_numbers.issubset(passage_numbers) else 0.0
    return [
        probs["entail"],
        probs["neutral"],
        probs["contradict"],
        probs["entail"],
        probs["contradict"],
        qa_score,
        qa_no_answer,
        qa_score,
        1.0 if qa_span else 0.0,
        conflict,
        1.0 if qa_span else 0.0,
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
    run = Run("EXP-036", "exp_036_real_decision_heads")
    rng = random.Random(11)
    items = []
    for kind in ("supported", "contradicted", "inconclusive"):
        for _ in range(120):
            items.append(scenario(rng, kind))
    x = [real_features(item) for item in items]
    y = [item["label"] for item in items]
    x_train, x_temp, y_train, y_temp = train_test_split(x, y, test_size=0.3, random_state=11, stratify=y)
    x_val, x_test, y_val, y_test = train_test_split(x_temp, y_temp, test_size=0.5, random_state=11, stratify=y_temp)
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
    abstain_precision_den = [i for i, p in enumerate(test_p) if p < threshold]
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
        "aggregation_check": real_nli("The rent is INR 10.", "The rent is INR 10.")["entail"],
    }
    exp011_path = ROOT / "data" / "exp_011_decision_heads" / "results.json"
    if exp011_path.exists():
        import json

        exp011 = json.loads(exp011_path.read_text())["metrics"]
        metrics["vs_exp_011_lexical"] = {
            "exp_011_test_accuracy": exp011["test_accuracy"],
            "exp_036_test_accuracy": metrics["test_accuracy"],
            "exp_011_next_action_accuracy": exp011["next_action_accuracy"],
            "exp_036_next_action_accuracy": metrics["next_action_accuracy"],
        }
    prose = (
        f"With features built from {QA_MODEL_NAME} and {NLI_MODEL_NAME} instead of the lexical QA/NLI pair, "
        f"decision head test accuracy is {metrics['test_accuracy']} on {metrics['test']} items "
        f"(EXP-011's lexical features scored {metrics.get('vs_exp_011_lexical', {}).get('exp_011_test_accuracy')}). "
        f"Validation selected threshold {threshold} (target met: {met}). At that threshold the test "
        f"unsupported-claim rate among assertions is {metrics['test_unsupported_claim_rate_when_asserted']} and "
        f"supported coverage is {metrics['test_supported_coverage']}. Next-action head accuracy is "
        f"{metrics['next_action_accuracy']} "
        f"(EXP-011 scored {metrics.get('vs_exp_011_lexical', {}).get('exp_011_next_action_accuracy')})."
    )
    run.finish(
        title="Decision and next-action heads rerun on real DeBERTa QA/NLI features",
        goal="Re-measure EXP-011 with features taken from the real DeBERTa QA and NLI pipeline. The head may stay logistic regression.",
        method=(
            "Identical 360 generated scenarios, split, and CalibratedClassifierCV(LogisticRegression, "
            "sigmoid) head as EXP-011. features() is replaced with real_qa (deepset/deberta-v3-base-squad2) "
            "and real_nli (MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli) in place of the lexical "
            "answer_question/judge pair; the feature vector's shape and the remaining constant slots are "
            "unchanged so the same head architecture applies."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=(
            "The head and the validation-threshold procedure are unchanged; only the sentences each feature "
            "is computed from come from the real encoders now, so this isolates how much of EXP-011's "
            "accuracy was coming from the lexical QA/NLI pair's own feature quality versus the generated "
            "scenario's own templated regularity (truth/other pulled from a small, fixed value list per slot, "
            "which both the lexical and real checkpoints can latch onto similarly)."
        ),
        scale_down="Same generated 360-scenario set as EXP-011 (six slots, not MNLI/ANLI/FEVER/SQuAD2/HotpotQA).",
        referenced_files=FILES,
        models_used=(
            f"{QA_MODEL_NAME} (extractive QA feature), {NLI_MODEL_NAME} (NLI feature). Local checkpoints, not "
            "API calls. Logistic regression (with Platt/sigmoid calibration) is the unchanged classical head."
        ),
    )


if __name__ == "__main__":
    main()
