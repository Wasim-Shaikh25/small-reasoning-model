"""Real pretrained, non-generative models used by the EXP-029/032/033 reruns.

ARCHITECTURE.md section 8 names bge-small-en-v1.5 for embeddings and DeBERTa-v3 /
GLiNER for extraction. Those checkpoints are hosted on huggingface.co. In this
sandbox huggingface.co is denied by the outbound egress policy (CONNECT refused
with 403, policy denial, confirmed against the agent proxy's own status endpoint
before writing this module). That is a sandbox network policy, not a project
decision, and it was not worked around.

spaCy's packaged pipelines are reachable (they ship as plain pip wheels from
GitHub release assets, not from huggingface.co) and are real pretrained,
non-generative models:
  - en_core_web_sm's NER component is a CNN tagger trained on OntoNotes 5.
  - en_core_web_md ships 300-dimensional GloVe-style static word vectors
    trained on a large web/news crawl.
Neither model generates text. Loading them does not conflict with FORBIDDEN.md,
which forbids generative language models.

These are the closest real, reachable substitutes available here, not the exact
blueprint checkpoints. Do not cite a result produced by this module as a bge or
DeBERTa or GLiNER result.
"""

from __future__ import annotations

import numpy as np
import spacy

NER_MODEL_NAME = "en_core_web_sm"
VECTOR_MODEL_NAME = "en_core_web_md"

_ner_pipeline = None
_vector_pipeline = None


def ner_pipeline():
    global _ner_pipeline
    if _ner_pipeline is None:
        _ner_pipeline = spacy.load(NER_MODEL_NAME)
    return _ner_pipeline


def vector_pipeline():
    global _vector_pipeline
    if _vector_pipeline is None:
        _vector_pipeline = spacy.load(
            VECTOR_MODEL_NAME, disable=["ner", "parser", "tagger", "lemmatizer", "attribute_ruler"]
        )
    return _vector_pipeline


def real_entities(text: str) -> list[dict]:
    """Named entities from the real pretrained OntoNotes NER model."""
    doc = ner_pipeline()(text or "")
    return [
        {"text": ent.text, "label": ent.label_, "start": ent.start_char, "end": ent.end_char}
        for ent in doc.ents
    ]


def real_vector(text: str) -> np.ndarray:
    """Mean pooled 300-d real pretrained word vector for a passage or query."""
    doc = vector_pipeline()(text or "")
    vec = doc.vector
    if vec is None:
        return np.zeros(300, dtype="float32")
    return np.asarray(vec, dtype="float32")


def model_card() -> dict:
    return {
        "ner_model": NER_MODEL_NAME,
        "ner_source": "https://github.com/explosion/spacy-models (pip wheel, GitHub release asset)",
        "ner_training_data": "OntoNotes 5 (real pretrained checkpoint, shipped by spaCy)",
        "vector_model": VECTOR_MODEL_NAME,
        "vector_source": "https://github.com/explosion/spacy-models (pip wheel, GitHub release asset)",
        "vector_training_data": "GloVe-style static vectors trained on a large web/news crawl, shipped by spaCy",
        "huggingface_blocked": True,
        "huggingface_block_detail": "huggingface.co CONNECT rejected with 403 by this sandbox's egress policy",
        "blueprint_checkpoints_named": ["bge-small-en-v1.5", "deepset/deberta-v3-base-squad2", "GLiNER"],
        "substitution_is_exact_blueprint_model": False,
    }
