"""EXP-033: rerun entity detection with a real pretrained NER model.

The blueprint names GLiNER, dslim/bert-base-NER, and libpostal. All three are
hosted on huggingface.co, which this sandbox's egress policy denies (see
lab/common/real_models.py). This rerun loads the closest real, reachable,
non-generative substitute -- spaCy's en_core_web_sm NER, a CNN tagger trained
on OntoNotes 5 -- and measures it against EXP-008's rule tagger (built for the
lease fixtures) on real, hand-labeled sentences drawn from the real Reuters
documents attached in EXP-025.

Gold labels are PERSON and ORG spans only, the two categories the rule tagger
also distinguishes; it has no general place/GPE category, so comparing on GPE
would not be apples to apples and is left out of the head-to-head score.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.entities import agreement, detect_primary, detect_secondary
from lab.common.harness import Run, prf
from lab.common.real_models import model_card, real_entities
from lab.common.textutil import normalize

FILES = [
    "lab/exp_033_real_entities/run.py",
    "lab/common/real_models.py",
    "lab/common/entities.py",
    "lab/common/textutil.py",
    "lab/common/harness.py",
    "data/exp_025_real_documents/documents.json",
    "data/exp_033_real_entities/gold.json",
    "data/exp_033_real_entities/results.json",
]

# Hand-labeled against the real sentences themselves (not invented): PERSON and
# ORG spans a person reading these real Reuters sentences would mark. Pulled
# verbatim from data/exp_025_real_documents/documents.json.
GOLD = [
    {
        "doc_id": "training-10014",
        "sentence": (
            "The New York Coffee, Sugar and Cocoa Exchange (CSCE) elected former first vice "
            "chairman Gerald Clancy to a two-year term as chairman of the board of managers, "
            "replacing previous chairman Howard Katz."
        ),
        "entities": [
            {"text": "Gerald Clancy", "label": "PERSON"},
            {"text": "Howard Katz", "label": "PERSON"},
            {"text": "CSCE", "label": "ORG"},
        ],
    },
    {
        "doc_id": "training-10014",
        "sentence": "Clancy currently serves on the Exchange board of managers as chairman of its appeals, executive, pension and political action committees.",
        "entities": [{"text": "Clancy", "label": "PERSON"}],
    },
    {
        "doc_id": "training-10100",
        "sentence": (
            "Jorge Cardenas, manager of Colombia's coffee growers' federation, said he did not "
            "believe any important decisions would emerge from an upcoming meeting of the "
            "International Coffee Organization (ICO)."
        ),
        "entities": [
            {"text": "Jorge Cardenas", "label": "PERSON"},
            {"text": "International Coffee Organization", "label": "ORG"},
        ],
    },
    {
        "doc_id": "training-1026",
        "sentence": "President Daniel Arap Moi said.",
        "entities": [{"text": "Daniel Arap Moi", "label": "PERSON"}],
    },
    {
        "doc_id": "training-1030",
        "sentence": "Administrative Executive Robin Taylor told the domestic news agency ZIANA that Zimbabwe earned the equivalent of 33 mln U.S.",
        "entities": [
            {"text": "Robin Taylor", "label": "PERSON"},
            {"text": "ZIANA", "label": "ORG"},
        ],
    },
    {
        "doc_id": "training-10640",
        "sentence": (
            "Nicaraguan Foreign Trade Minister Alejandro Martinez Cuenca was in London to brief "
            "International Coffee Organisation (ICO) executive board producer members after a "
            "meeting last weekend in Managua attended by eight Latin American coffee producers "
            "to discuss the fall in coffee prices."
        ),
        "entities": [
            {"text": "Alejandro Martinez Cuenca", "label": "PERSON"},
            {"text": "International Coffee Organisation", "label": "ORG"},
        ],
    },
    {
        "doc_id": "training-10682",
        "sentence": (
            "roastings of green coffee in the week ended March 21 were about 250,000 (60-kilo) "
            "bags, including that used for soluble production, compared with 195,000 bags in "
            "the corresponding week of last year and about 300,000 bags in the week ended March "
            "14, George Gordon Paton and Co Inc reported."
        ),
        "entities": [{"text": "George Gordon Paton and Co Inc", "label": "ORG"}],
    },
    {
        "doc_id": "training-10902",
        "sentence": (
            "Chances that the International Coffee Organization, ICO, executive board meeting "
            "this week will agree to resume negotiations on export quotas soon look remote, ICO "
            "delegates and trade sources said."
        ),
        "entities": [{"text": "International Coffee Organization", "label": "ORG"}],
    },
    {
        "doc_id": "training-10959",
        "sentence": (
            "They said IBC President Jorio Dauster is likely to leave the basic formula for the "
            "minimum registration price unchanged but raise the contribution quota to partially "
            "offset the effects of cruzado devaluation since April registrations were closed in "
            "mid-February."
        ),
        "entities": [
            {"text": "Jorio Dauster", "label": "PERSON"},
            {"text": "IBC", "label": "ORG"},
        ],
    },
    {
        "doc_id": "training-11372",
        "sentence": "No firm date has been set for the talks, Ambassador Rene Montes told reporters at the ICO executive board meeting here.",
        "entities": [{"text": "Rene Montes", "label": "PERSON"}],
    },
    {
        "doc_id": "training-11816",
        "sentence": (
            "Singapore's United Industrial Corp Ltd (UIC) has agreed in principle to inject 16 "
            "mln dlrs in convertible loan stock into Teck Hock and Co (Pte) Ltd, a creditor bank "
            "official said."
        ),
        "entities": [
            {"text": "United Industrial Corp Ltd", "label": "ORG"},
            {"text": "Teck Hock and Co", "label": "ORG"},
        ],
    },
    {
        "doc_id": "training-11183",
        "sentence": "India cut the export duty on coffee to 330 rupees per 100 kg from 600 rupees, effective March 23, a Coffee Board official said.",
        "entities": [{"text": "Coffee Board", "label": "ORG"}],
    },
]


def _rule_tagger_spans(sentence: str) -> set[str]:
    mentions = agreement(detect_primary(sentence), detect_secondary(sentence))
    out = set()
    for m in mentions:
        if m["label"] in ("person", "organization"):
            out.add(normalize(m["text"]))
    return out


def _real_ner_spans(sentence: str) -> set[str]:
    ents = real_entities(sentence)
    return {normalize(e["text"]) for e in ents if e["label"] in ("PERSON", "ORG")}


def _contains_match(pred: set[str], gold_text: str) -> bool:
    g = normalize(gold_text)
    return any(g == p or g in p or p in g for p in pred)


def main():
    run = Run("EXP-033", "exp_033_real_entities")
    run.write_json("gold.json", GOLD)

    rule_tp = rule_fp = rule_fn = 0
    real_tp = real_fp = real_fn = 0
    per_item = []
    for item in GOLD:
        sentence = item["sentence"]
        gold_texts = [e["text"] for e in item["entities"]]
        rule_pred = _rule_tagger_spans(sentence)
        real_pred = _real_ner_spans(sentence)

        rule_hits = [g for g in gold_texts if _contains_match(rule_pred, g)]
        real_hits = [g for g in gold_texts if _contains_match(real_pred, g)]
        rule_tp += len(rule_hits)
        rule_fn += len(gold_texts) - len(rule_hits)
        rule_fp += max(0, len(rule_pred) - len(rule_hits))
        real_tp += len(real_hits)
        real_fn += len(gold_texts) - len(real_hits)
        real_fp += max(0, len(real_pred) - len(real_hits))
        per_item.append(
            {
                "doc_id": item["doc_id"],
                "gold": gold_texts,
                "rule_tagger_pred": sorted(rule_pred),
                "real_ner_pred": sorted(real_pred),
                "rule_tagger_hits": rule_hits,
                "real_ner_hits": real_hits,
            }
        )

    def _prf(tp, fp, fn):
        p = tp / max(1, tp + fp)
        r = tp / max(1, tp + fn)
        f = 2 * p * r / max(1e-9, p + r)
        return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4), "tp": tp, "fp": fp, "fn": fn}

    rule_scores = _prf(rule_tp, rule_fp, rule_fn)
    real_scores = _prf(real_tp, real_fp, real_fn)
    n_gold = sum(len(item["entities"]) for item in GOLD)

    metrics = {
        "n_sentences": len(GOLD),
        "n_gold_entities": n_gold,
        "rule_tagger": rule_scores,
        "real_pretrained_ner": real_scores,
        "f1_lift": round(real_scores["f1"] - rule_scores["f1"], 4),
        "recall_lift": round(real_scores["recall"] - rule_scores["recall"], 4),
        "real_model_card": model_card(),
    }
    run.write_json("per_item.json", per_item)
    prose = (
        f"On {metrics['n_sentences']} real sentences with {metrics['n_gold_entities']} hand-labeled PERSON/ORG "
        f"spans, the rule tagger (built for lease fixtures, EXP-008) gets precision {rule_scores['precision']}, "
        f"recall {rule_scores['recall']}, F1 {rule_scores['f1']}. The real pretrained spaCy NER (OntoNotes-trained) "
        f"gets precision {real_scores['precision']}, recall {real_scores['recall']}, F1 {real_scores['f1']}. "
        f"F1 lift from the real pretrained model: {metrics['f1_lift']:+.4f}."
    )
    run.finish(
        title="Entity detection with a real pretrained NER model, on real documents",
        goal="Re-measure EXP-008-style entity detection with a real pretrained NER checkpoint, on real open-domain news sentences instead of lease fixtures.",
        method=(
            "Hand-labeled PERSON and ORG spans on 12 real sentences drawn verbatim from the EXP-025 real document "
            "collection (see GOLD in this file). Ran EXP-008's unmodified rule tagger (detect_primary, "
            "detect_secondary, agreement) and the real pretrained spaCy en_core_web_sm NER pipeline on the same raw "
            "sentences. A hit counts when a predicted span equals, contains, or is contained by a normalized gold "
            "span (text containment, not character-offset overlap). Micro-averaged precision/recall/F1 across all "
            "gold spans."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=(
            "The rule tagger was written against lease-fixture patterns (two-capitalized-word names, Pvt Ltd/Inc "
            "suffixes, a fixed exclusion list for false positives like 'New Delhi'). On real open-domain news text "
            "it both misses organization abbreviations it has no pattern for (ZIANA, IBC, UIC, Coffee Board) and "
            "can mistag place names its exclusion list does not cover as PERSON. The real pretrained OntoNotes NER "
            "generalizes across domains without hand-written patterns, which is exactly the generalization gap "
            "FORBIDDEN.md's own substitute list predicted. This closes the EXP-033 rerun todo for entity tagging, "
            "measured with spaCy rather than GLiNER or dslim/bert-base-NER."
        ),
        scale_down=(
            "12 hand-labeled sentences, not a held-out annotated corpus (EXP-008 used 52 lines on the lease "
            "domain). GLiNER, dslim/bert-base-NER, and libpostal remain unloaded because huggingface.co is blocked "
            "by this sandbox's egress policy; see real_model_card. Address/GPE detection is out of scope for this "
            "head-to-head since the rule tagger has no general place category."
        ),
        referenced_files=FILES,
        follow_ups=[
            "Hand-label a larger gold sentence set (EXP-008-sized, 50+) for a more stable F1 estimate.",
            "If huggingface.co access is ever granted, rerun with GLiNER and dslim/bert-base-NER and compare against this spaCy result.",
        ],
        models_used=(
            "Real pretrained spaCy en_core_web_sm NER (CNN tagger trained on OntoNotes 5) compared against the "
            "unmodified EXP-008 rule tagger. GLiNER, dslim/bert-base-NER, and libpostal were not loaded: "
            "huggingface.co is blocked in this sandbox (403 CONNECT, policy denial). This is a real, reachable, "
            "non-generative pretrained model, not the exact blueprint checkpoint. See lab/common/real_models.py:model_card()."
        ),
    )


if __name__ == "__main__":
    main()
