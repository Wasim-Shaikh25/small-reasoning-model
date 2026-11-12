"""EXP-080: dslim/bert-base-NER, actually measured -- EXP-033's own named
follow-up ("if huggingface.co access is ever granted, rerun with GLiNER
and dslim/bert-base-NER and compare against this spaCy result"), picked
up now that it is. The checkpoint has been loaded in
lab.common.real_encoders since EXP-033/034's era but nothing in this
repo ever actually called it for the entity-detection role it was loaded
for -- lab.common.real_ner (new) is that missing call, and this is its
first real measurement, not assumed from the model card.

Identical 12-sentence, 19-span GOLD fixture EXP-033 used (verbatim, not
re-picked), so this is a genuine three-way comparison: the rule tagger
(EXP-008, lease-fixture patterns), spaCy's OntoNotes NER (EXP-033, the
substitute used when HF was blocked), and dslim/bert-base-NER (this
exploration, the actual blueprint-named checkpoint, now that HF is
reachable).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.entities import agreement, detect_primary, detect_secondary
from lab.common.harness import Run
from lab.common.real_encoders import model_card
from lab.common.real_ner import detect_real
from lab.common.textutil import normalize
from lab.tests.exp_033_real_entities.run import GOLD

FILES = [
    "lab/tests/exp_080_real_ner_rerun/run.py",
    "lab/common/real_ner.py",
    "lab/common/real_encoders.py",
    "lab/common/entities.py",
    "lab/tests/exp_033_real_entities/run.py",
    "data/exp_033_real_entities/gold.json",
    "data/exp_033_real_entities/results.json",
    "data/exp_080_real_ner_rerun/results.json",
]


def _rule_tagger_spans(sentence: str) -> set[str]:
    mentions = agreement(detect_primary(sentence), detect_secondary(sentence))
    return {normalize(m["text"]) for m in mentions if m["label"] in ("person", "organization")}


def _dslim_spans(sentence: str) -> set[str]:
    mentions = detect_real(sentence)
    return {normalize(m["text"]) for m in mentions if m["label"] in ("person", "organization")}


def _contains_match(pred: set[str], gold_text: str) -> bool:
    g = normalize(gold_text)
    return any(g == p or g in p or p in g for p in pred)


def _prf(tp, fp, fn):
    p = tp / max(1, tp + fp)
    r = tp / max(1, tp + fn)
    f = 2 * p * r / max(1e-9, p + r)
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4), "tp": tp, "fp": fp, "fn": fn}


def main():
    run = Run("EXP-080", "exp_080_real_ner_rerun")

    rule_tp = rule_fp = rule_fn = 0
    dslim_tp = dslim_fp = dslim_fn = 0
    per_item = []
    for item in GOLD:
        sentence = item["sentence"]
        gold_texts = [e["text"] for e in item["entities"]]
        rule_pred = _rule_tagger_spans(sentence)
        dslim_pred = _dslim_spans(sentence)

        rule_hits = [g for g in gold_texts if _contains_match(rule_pred, g)]
        dslim_hits = [g for g in gold_texts if _contains_match(dslim_pred, g)]
        rule_tp += len(rule_hits)
        rule_fn += len(gold_texts) - len(rule_hits)
        rule_fp += max(0, len(rule_pred) - len(rule_hits))
        dslim_tp += len(dslim_hits)
        dslim_fn += len(gold_texts) - len(dslim_hits)
        dslim_fp += max(0, len(dslim_pred) - len(dslim_hits))
        per_item.append(
            {
                "doc_id": item["doc_id"],
                "gold": gold_texts,
                "rule_tagger_pred": sorted(rule_pred),
                "dslim_pred": sorted(dslim_pred),
                "rule_tagger_hits": rule_hits,
                "dslim_hits": dslim_hits,
            }
        )
    run.write_json("per_item.json", per_item)

    rule_scores = _prf(rule_tp, rule_fp, rule_fn)
    dslim_scores = _prf(dslim_tp, dslim_fp, dslim_fn)
    n_gold = sum(len(item["entities"]) for item in GOLD)

    # EXP-033's already-measured spaCy numbers, for the three-way
    # comparison -- not rerun here (spaCy's own result doesn't change),
    # carried forward by reference, not recomputed and not assumed equal.
    spacy_f1 = 0.7619
    spacy_precision = 0.6957
    spacy_recall = 0.8421

    metrics = {
        "n_sentences": len(GOLD),
        "n_gold_entities": n_gold,
        "rule_tagger": rule_scores,
        "dslim_bert_base_ner": dslim_scores,
        "spacy_en_core_web_sm_exp033": {"precision": spacy_precision, "recall": spacy_recall, "f1": spacy_f1},
        "f1_lift_dslim_vs_rule": round(dslim_scores["f1"] - rule_scores["f1"], 4),
        "f1_lift_dslim_vs_spacy": round(dslim_scores["f1"] - spacy_f1, 4),
        "real_model_card": model_card(),
    }

    dslim_beats_both = dslim_scores["f1"] > rule_scores["f1"] and dslim_scores["f1"] > spacy_f1

    prose = (
        f"On the identical EXP-033 fixture ({metrics['n_sentences']} sentences, {metrics['n_gold_entities']} "
        f"gold PERSON/ORG spans): rule tagger F1 {rule_scores['f1']} (unchanged from EXP-008/033, measured "
        f"again here as the baseline). dslim/bert-base-NER F1 {dslim_scores['f1']} (precision "
        f"{dslim_scores['precision']}, recall {dslim_scores['recall']}) -- the first real measurement of this "
        f"checkpoint anywhere in this repo. spaCy en_core_web_sm (EXP-033): F1 {spacy_f1}, for reference, not "
        f"rerun here."
    )

    conclusion = (
        (
            "dslim/bert-base-NER, the actual blueprint-named checkpoint, outperforms both the rule tagger and "
            "the spaCy substitute EXP-033 used when HuggingFace was unreachable -- a real, direct three-way "
            "comparison, not an assumption that the originally-intended checkpoint would be better just "
            "because it's the one the blueprint named. EXP-033/034's gap is closed: the checkpoint was loaded "
            "but never actually called for this role until now."
            if dslim_beats_both
            else "dslim/bert-base-NER does not clearly outperform both alternatives on this fixture -- see the "
            "per-item breakdown for specifics. Reported as measured: being the blueprint-named checkpoint is "
            "not the same as being the better one on this particular sentence set."
        )
    )

    run.finish(
        title="dslim/bert-base-NER, actually measured against EXP-033's rule-tagger-vs-spaCy comparison",
        goal=(
            "Pick up EXP-033's own named follow-up: measure dslim/bert-base-NER (loaded in "
            "lab.common.real_encoders since EXP-033/034's era, never actually called for entity detection "
            "until now) on the identical gold fixture, for a real three-way comparison against the rule "
            "tagger and the spaCy substitute."
        ),
        method=(
            "The same 12 hand-labeled sentences / 19 PERSON-ORG spans EXP-033 used (imported directly from "
            "that exploration's GOLD, not re-picked), scored the identical way (text-containment hit counting, "
            "micro-averaged precision/recall/F1) against lab.common.real_ner.detect_real, the new wiring of "
            "the dslim/bert-base-NER pipeline already loaded in lab.common.real_encoders."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="Same 12-sentence fixture as EXP-033 -- not a held-out annotated corpus, chosen for a direct, controlled comparison against an already-measured result rather than a fresh, larger evaluation.",
        referenced_files=FILES,
        follow_ups=[
            "Hand-label a larger gold sentence set (50+, matching EXP-008's own scale) for a more stable F1 estimate across all three taggers.",
            "lab.common.real_ner.detect_real only maps PER/ORG -- dslim/bert-base-NER's LOC/MISC categories are dropped rather than mapped to this project's address/date/amount labels, which it was never trained to produce; address detection still depends entirely on the regex tagger.",
            "Not yet wired into lab.common.brain.reason's identity-extraction step (detect_primary is still what that step calls) -- this measures the checkpoint standalone, matching EXP-033's own scope, not a live pipeline swap.",
        ],
        models_used="dslim/bert-base-NER (CoNLL-2003 token classifier, non-generative), via lab.common.real_encoders.real_entities, wired through lab.common.real_ner. No generative model.",
    )


if __name__ == "__main__":
    main()
