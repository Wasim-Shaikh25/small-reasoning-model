"""Real pretrained, non-generative encoder checkpoints named in ARCHITECTURE.md section 8.

These are the actual blueprint checkpoints -- not the classical substitutes in
lab/common/qa.py, lab/common/nli.py, lab/common/entities.py, or the spaCy
real-model substitutes in lab/common/real_models.py (which were the closest
reachable stand-ins while huggingface.co was blocked in an earlier sandbox).
On this machine huggingface.co is reachable, so the real checkpoints are
loaded directly:

  - bge-small-en-v1.5 (BAAI): dense embeddings, in place of TF-IDF cosine.
  - deepset/deberta-v3-base-squad2: extractive QA, in place of the lexical
    span extractors in lab/common/qa.py.
  - MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli: NLI judge, in place of
    lab/common/nli.judge.
  - dslim/bert-base-NER: named-entity tagging, in place of the rule tagger.
    GLiNER is also named in the blueprint for this role; the `gliner`
    package is not installed in this environment, so GLiNER itself is not
    loaded here -- say so, do not substitute silently.

None of these generate text. Loading them does not touch FORBIDDEN.md's
generative-model restriction, which is only about the bounded FLAN-T5
rewriter (lab/common/real_rewriter.py). These checkpoints are never used to
extract an answer that gets attributed as fact without going through the
same gates (span-in-passage, fidelity, citation survival) the lexical
substitutes already go through -- only the scoring function underneath
changes.
"""

from __future__ import annotations

import numpy as np

BGE_MODEL_NAME = "BAAI/bge-small-en-v1.5"
QA_MODEL_NAME = "deepset/deberta-v3-base-squad2"
NLI_MODEL_NAME = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"
NER_MODEL_NAME = "dslim/bert-base-NER"
GLINER_MODEL_NAME = "urchade/gliner_small-v2.1"  # named by the blueprint; not loaded, see module docstring.

_bge = None
_qa_pipeline = None
_nli_pipeline = None
_ner_pipeline = None
_nli_label_map = None


def bge_model():
    global _bge
    if _bge is None:
        from sentence_transformers import SentenceTransformer

        _bge = SentenceTransformer(BGE_MODEL_NAME)
    return _bge


def bge_embed(texts: list[str]) -> np.ndarray:
    """L2-normalized bge-small-en-v1.5 embeddings, one row per input text."""
    model = bge_model()
    vecs = model.encode(list(texts), normalize_embeddings=True)
    return np.asarray(vecs, dtype="float32")


def bge_similarity(a: str, b: str) -> float:
    vecs = bge_embed([a, b])
    return float(np.dot(vecs[0], vecs[1]))


def bge_cosine_matrix(texts: list[str]) -> np.ndarray:
    """Pairwise cosine similarity for a batch of texts (embeddings are already unit-norm)."""
    if not texts:
        return np.zeros((0, 0), dtype="float32")
    vecs = bge_embed(texts)
    return vecs @ vecs.T


def qa_pipeline():
    global _qa_pipeline
    if _qa_pipeline is None:
        from transformers import pipeline

        _qa_pipeline = pipeline("question-answering", model=QA_MODEL_NAME, tokenizer=QA_MODEL_NAME)
    return _qa_pipeline


def real_qa(question: str, context: str) -> dict:
    """deepset/deberta-v3-base-squad2's best span, or no_answer when its handle_impossible_answer fires."""
    pipe = qa_pipeline()
    out = pipe(question=question, context=context, handle_impossible_answer=True)
    answer = (out.get("answer") or "").strip()
    is_no_answer = not answer
    return {
        "answer": answer or None,
        "score": float(out.get("score", 0.0)),
        "start": out.get("start"),
        "end": out.get("end"),
        "no_answer": is_no_answer,
    }


def nli_pipeline():
    global _nli_pipeline, _nli_label_map
    if _nli_pipeline is None:
        from transformers import pipeline

        _nli_pipeline = pipeline("text-classification", model=NLI_MODEL_NAME, top_k=None)
        id2label = _nli_pipeline.model.config.id2label
        _nli_label_map = {}
        for label in id2label.values():
            low = label.lower()
            if "entail" in low:
                _nli_label_map[label] = "entail"
            elif "contra" in low:
                _nli_label_map[label] = "contradict"
            else:
                _nli_label_map[label] = "neutral"
    return _nli_pipeline


def real_nli(premise: str, hypothesis: str) -> dict:
    """entail/neutral/contradict probabilities from DeBERTa-v3-base-mnli-fever-anli."""
    pipe = nli_pipeline()
    text = f"{premise} [SEP] {hypothesis}"
    scored = pipe(text)[0]
    probs = {"entail": 0.0, "neutral": 0.0, "contradict": 0.0}
    for row in scored:
        probs[_nli_label_map[row["label"]]] += float(row["score"])
    return {k: round(v, 4) for k, v in probs.items()}


def ner_pipeline():
    global _ner_pipeline
    if _ner_pipeline is None:
        from transformers import pipeline

        _ner_pipeline = pipeline("ner", model=NER_MODEL_NAME, aggregation_strategy="simple")
    return _ner_pipeline


def real_entities(text: str) -> list[dict]:
    """Named entities from dslim/bert-base-NER (real pretrained, CoNLL-2003).

    NAME COLLISION, flagged by the 2026-11-03 reasoning-layer audit
    (AUDIT.md): lab.common.real_models ALSO exports a function literally
    named `real_entities` (spaCy en_core_web_sm/OntoNotes NER, a different,
    weaker model, raw unmapped spaCy labels, no `score` field). THIS one
    is the real, live NER path (lab.common.real_ner wraps it; reachable
    from brain.reason() via entities.detect_primary(use_real_ner=True)).
    Double-check the import's source module before trusting a
    `real_entities` call -- the two are not interchangeable.
    """
    pipe = ner_pipeline()
    out = pipe(text or "")
    return [
        {
            "text": ent["word"],
            "label": ent["entity_group"],
            "start": ent["start"],
            "end": ent["end"],
            "score": round(float(ent["score"]), 4),
        }
        for ent in out
    ]


def real_bidirectional_nli(source: str, output: str, tau: float = 0.55) -> dict:
    """lab.common.verify.bidirectional_nli's shape, scored by the real DeBERTa-v3 MNLI checkpoint."""
    forward = real_nli(source, output)
    backward = real_nli(output, source)
    return {
        "forward": forward,
        "backward": backward,
        "ok": forward["entail"] >= tau and backward["entail"] >= tau,
    }


def model_card() -> dict:
    return {
        "bge_model": BGE_MODEL_NAME,
        "qa_model": QA_MODEL_NAME,
        "nli_model": NLI_MODEL_NAME,
        "ner_model": NER_MODEL_NAME,
        "gliner_named_by_blueprint": GLINER_MODEL_NAME,
        "gliner_loaded": False,
        "gliner_reason": "the `gliner` package is not installed in this environment; dslim/bert-base-NER is the real checkpoint measured for the NER role instead",
        "huggingface_reachable": True,
        "all_non_generative": True,
    }
