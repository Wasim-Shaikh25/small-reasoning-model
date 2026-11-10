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

# en_core_web_trf (RoBERTa-based) rather than en_core_web_sm (a small CNN):
# measured, not assumed -- en_core_web_sm's own published unlabeled
# attachment score is ~0.918, en_core_web_trf's is ~0.953, and this
# project found a real parser-coverage gap the small model's own
# inconsistency exposed (HANDOFF.md, 2026-11-10: the identical "studying
# WHETHER X should Y" clause shape parsed as `ccomp` for one governing
# verb and `advcl` for another). Benchmarked on this machine (CPU only,
# no GPU -- torch.cuda.is_available() is False here) on a real ~3,000-
# word document-scale sample before committing to the swap, not on
# spaCy's own published words/second figure for different hardware:
# en_core_web_sm parsed it in 0.98s (3,132 words/s), en_core_web_trf in
# 4.20s (733 words/s) -- about 4x slower in absolute terms, but a few
# extra seconds against a pipeline (`longform.write_long_document`) this
# project already measured at ~63.5s per real document (AUDIT.md,
# EXP-081) is negligible, not a real cost.
PARSER_MODEL_NAME = "en_core_web_trf"

_ner_pipeline = None
_parser_pipeline = None
_vector_pipeline = None


def parser_pipeline():
    """The cached spaCy pipeline every LIVE caller (lab.common.rules._parser,
    and everything built on it -- inference.py, connectives.py, deontic.py,
    decision_findings.py, sentence_completeness.py, entities.py's
    FULL_PERSON check's own dependency-parse fallback) uses purely as a
    general-purpose dependency parser -- only `.pos_`/`.tag_`/`.dep_`/
    `.lemma_`/`.children`/`.subtree` are ever read off it, never `.ents`
    (NER tagging). Loads `PARSER_MODEL_NAME` (`en_core_web_trf`, see that
    constant's own comment for why), deliberately NOT the same pipeline
    `ner_pipeline()` below loads -- the two were split out (2026-11-10)
    specifically so upgrading the parser used for live reasoning never
    silently changes `ner_pipeline()`'s own, already-measured, closed
    output (lab/exp_032_real_multihop/run.py and
    lab/exp_033_real_entities/run.py import that exact function by name
    as part of their own frozen reproducibility record).
    """
    global _parser_pipeline
    if _parser_pipeline is None:
        _parser_pipeline = spacy.load(PARSER_MODEL_NAME)
    return _parser_pipeline


def ner_pipeline():
    """The cached `NER_MODEL_NAME` (`en_core_web_sm`) pipeline -- kept on
    its OWN model and its own cache, separate from `parser_pipeline()`
    above, specifically so EXP-032/EXP-033's closed, already-measured
    `.ents`-based output never changes just because the live dependency
    parser was upgraded. No longer an alias of `parser_pipeline` (it was,
    before the 2026-11-10 split) -- do not re-merge them without re-
    running and re-verifying those two closed experiments first.
    """
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
    """Named entities from the real pretrained OntoNotes NER model.

    NAME COLLISION, flagged by the 2026-11-03 reasoning-layer audit
    (AUDIT.md): lab.common.real_encoders ALSO exports a function literally
    named `real_entities` (dslim/bert-base-NER, different model, CoNLL
    labels remapped to person/organization, a `score` field this one
    lacks) -- and that is the one lab.common.real_ner.py/entities.py
    actually use live, via brain.reason(use_real_ner=True). THIS function
    is kept only because lab/exp_032_real_multihop/run.py and
    lab/exp_033_real_entities/run.py import it directly by this exact
    name as part of their own closed reproducibility record -- do not
    rename it, and do not import `real_entities` "from the models module"
    by habit; double-check which module before relying on it for NER.
    """
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
