"""EXP-024: local span tagger.

EXP-008's own follow_up named the trigger condition: "If hard-slice F1
is not enough, train a span tagger only on locally labeled spans. Do
not download a pretrained NER model." Verified directly before building
anything: the rule tagger scored hard-slice F1=0.4615 (EXP-008), and a
real PRETRAINED NER model (dslim/bert-base-NER, EXP-080's own
checkpoint) scores hard-slice F1=0.4138 on the exact same 10 sentences
-- essentially the SAME, not better. The trigger genuinely still holds;
this is not a stale todo.

This trains a small per-token multinomial logistic regression (the same
head shape every other sklearn-based exploration in this repo uses, EXP-
011/051) directly on EXP-008's own labeled lines -- both EASY and HARD
slices, every gold span already stored in this repository, nothing
downloaded or newly labeled. Features come only from spaCy's POS tags
and token shape (lab.common.rules._parser, already a dependency used
throughout this repo for dependency parsing -- never doc.ents, which
would be using the bundled NER component this todo explicitly forbids)
plus simple orthographic signals (capitalization, digits, token
position). Sentence-grouped 5-fold cross-validation (no sentence's own
tokens appear in both train and test for the same fold) gives an honest
out-of-sample exact-span F1, the same metric EXP-008 itself used,
specifically broken out for the hard slice.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.tests.support import prf
from lab.common.rules import _parser
from lab.tests.exp_008_entity_detect.run import HARD, _easy_lines, _gold_set
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold, cross_val_predict

FILES = [
    "lab/tests/exp_024_local_span_tagger/run.py",
    "lab/common/rules.py",
    "lab/tests/exp_008_entity_detect/run.py",
    "lab/tests/exp_080_real_ner_rerun/run.py",
    "data/exp_008_entity_detect/results.json",
    "data/exp_080_real_ner_rerun/results.json",
    "lab/tests/support.py",

]

LABELS = ("O", "person", "organization", "address", "amount", "date", "defined term")
LABEL_INDEX = {label: i for i, label in enumerate(LABELS)}


def token_label(tok, gold_spans: set[tuple[int, int, str]]) -> str:
    for start, end, label in gold_spans:
        if tok.idx < end and tok.idx + len(tok.text) > start:
            return label
    return "O"


def token_features(doc, i) -> list[float]:
    tok = doc[i]
    prev = doc[i - 1] if i > 0 else None
    nxt = doc[i + 1] if i + 1 < len(doc) else None
    return [
        1.0 if tok.text[:1].isupper() else 0.0,
        1.0 if tok.text.isupper() and len(tok.text) > 1 else 0.0,
        1.0 if any(c.isdigit() for c in tok.text) else 0.0,
        float(len(tok.text)),
        1.0 if tok.pos_ == "PROPN" else 0.0,
        1.0 if tok.pos_ == "NUM" else 0.0,
        1.0 if tok.like_num else 0.0,
        1.0 if prev is not None and prev.text[:1].isupper() else 0.0,
        1.0 if nxt is not None and nxt.text[:1].isupper() else 0.0,
        1.0 if tok.is_title else 0.0,
        float(i) / max(1, len(doc) - 1),
    ]


def main():
    run = Run("EXP-024", "exp_024_local_span_tagger")
    lines = _easy_lines() + HARD

    x, y, groups, doc_meta = [], [], [], []
    for sent_idx, (text, spans, kind) in enumerate(lines):
        doc = _parser()(text)
        gold_spans = _gold_set(text, spans)
        for i in range(len(doc)):
            x.append(token_features(doc, i))
            y.append(token_label(doc[i], gold_spans))
            groups.append(sent_idx)
        doc_meta.append({"text": text, "kind": kind, "doc": doc, "gold_spans": gold_spans, "sent_idx": sent_idx})

    n_splits = min(5, len({k for k in groups}))
    gkf = GroupKFold(n_splits=n_splits)
    model = LogisticRegression(max_iter=1000)
    pred_labels = cross_val_predict(model, x, y, groups=groups, cv=gkf)

    # Reconstruct spans from contiguous same-label token runs, per sentence.
    pred_by_sentence: dict[int, set[tuple[int, int, str]]] = {m["sent_idx"]: set() for m in doc_meta}
    token_offset = 0
    for meta in doc_meta:
        doc = meta["doc"]
        run_label, run_start = None, None
        for i in range(len(doc)):
            label = pred_labels[token_offset + i]
            tok = doc[i]
            if label != run_label:
                if run_label is not None and run_label != "O":
                    pred_by_sentence[meta["sent_idx"]].add((run_start, prev_end, run_label))
                run_label, run_start = label, tok.idx
            prev_end = tok.idx + len(tok.text)
        if run_label is not None and run_label != "O":
            pred_by_sentence[meta["sent_idx"]].add((run_start, prev_end, run_label))
        token_offset += len(doc)

    gold_easy, pred_easy, gold_hard, pred_hard = set(), set(), set(), set()
    for meta in doc_meta:
        offset_gold = {(s + meta["sent_idx"] * 10_000, e + meta["sent_idx"] * 10_000, l) for s, e, l in meta["gold_spans"]}
        offset_pred = {(s + meta["sent_idx"] * 10_000, e + meta["sent_idx"] * 10_000, l) for s, e, l in pred_by_sentence[meta["sent_idx"]]}
        if meta["kind"] == "hard":
            gold_hard |= offset_gold
            pred_hard |= offset_pred
        else:
            gold_easy |= offset_gold
            pred_easy |= offset_pred

    hard_scores = prf(pred_hard, gold_hard)
    easy_scores = prf(pred_easy, gold_easy)

    run.write_json(
        "tagger.json",
        {
            "hard_predictions": [{"text": m["text"], "gold": sorted(m["gold_spans"]), "pred": sorted(pred_by_sentence[m["sent_idx"]])} for m in doc_meta if m["kind"] == "hard"],
        },
    )

    rule_tagger_hard_f1 = 0.4615
    real_ner_hard_f1 = 0.4138
    improved = hard_scores["f1"] > max(rule_tagger_hard_f1, real_ner_hard_f1)

    metrics = {
        "n_sentences": len(lines),
        "n_tokens": len(x),
        "cv_folds": n_splits,
        "hard_slice": hard_scores,
        "easy_slice": easy_scores,
        "rule_tagger_hard_f1_baseline": rule_tagger_hard_f1,
        "real_pretrained_ner_hard_f1_baseline": real_ner_hard_f1,
        "improved_over_both_baselines": improved,
    }

    prose = (
        f"Sentence-grouped {n_splits}-fold cross-validated local span tagger on {len(x)} tokens from "
        f"{len(lines)} sentences (EXP-008's own EASY+HARD fixture, nothing newly labeled): hard-slice exact-"
        f"span F1={hard_scores['f1']} (precision={hard_scores['precision']}, recall={hard_scores['recall']}), "
        f"easy-slice F1={easy_scores['f1']}. Baselines on the same hard sentences: rule tagger "
        f"F1={rule_tagger_hard_f1} (EXP-008), real pretrained NER (dslim/bert-base-NER) F1={real_ner_hard_f1} "
        f"(EXP-080) -- the local tagger {'improves on both' if improved else 'does not improve on both'}."
    )

    conclusion = (
        "A locally-trained span tagger on this repository's own labeled lines, with no pretrained NER model "
        "and no newly-collected data, measurably improves hard-slice F1 over both the rule tagger and a real "
        "pretrained NER checkpoint -- confirming EXP-008's own named remedy works on the exact fixture that "
        "motivated it."
        if improved
        else "The local tagger did not clear both baselines on this fixture -- see metrics for the exact "
        "numbers, reported as measured rather than assumed to work. The fixture is tiny (10 hard sentences); "
        "a token-level classifier with only 5-fold sentence-grouped CV has very little signal to learn from."
    )

    run.finish(
        title="Local span tagger, measured against both the rule tagger and a real pretrained NER on the exact fixture that motivated this todo",
        goal=(
            "If rule-tagger hard-slice F1 is too low, train a span tagger only on locally labeled spans. "
            "Verify the trigger condition still holds (it does: a real pretrained NER model does not fix "
            "it either, F1=0.4138 vs the rule tagger's 0.4615) before training anything, then measure "
            "whether a token-level classifier trained only on this repo's own labels actually helps."
        ),
        method=(
            "Per-token multinomial logistic regression (sklearn), features from spaCy POS tags/token shape "
            "only (lab.common.rules._parser, never doc.ents -- no pretrained NER model used anywhere in this "
            "exploration). Trained on EXP-008's own EASY+HARD lines (every gold span already stored in this "
            "repository). Sentence-grouped GroupKFold cross-validation so no sentence's tokens appear in both "
            "train and test within a fold. Predicted spans reconstructed from contiguous same-label token "
            "runs, scored with EXP-008's own exact-span prf(), broken out by slice."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            "10 hard sentences, 19 gold hard-slice spans total -- a genuinely small fixture for a trained "
            "classifier; this result should not be read as a general claim about span tagging, only about "
            "this specific repository's own fixture. Per-token classification with contiguous-run span "
            "reconstruction, not a true BIO/CRF sequence tagger -- adjacent same-label entities would merge "
            "into one span, a real limit not exercised by this particular fixture (no two adjacent gold spans "
            "share a label here) but not proven absent either."
        ),
        referenced_files=FILES,
        follow_ups=[],
        models_used=(
            "Multinomial logistic regression (sklearn) trained only on labels already stored in this "
            "repository. spaCy en_core_web_sm's POS tagger (lab.common.rules._parser, already a dependency) "
            "for features -- its NER component is never read. No pretrained NER model, no generative model."
        ),
    )

    print(f"hard_slice_f1={hard_scores['f1']} (rule_tagger={rule_tagger_hard_f1}, real_ner={real_ner_hard_f1}) improved={improved}")


if __name__ == "__main__":
    main()
