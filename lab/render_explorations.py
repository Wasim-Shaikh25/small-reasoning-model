"""Build EXPLORATIONS.md from closed results plus todo entries. Numbers are copied from results.json."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# model, component, used, substitute, reason
BLUEPRINT = [
    (
        "bge-small-en-v1.5",
        "Embeddings (section 8)",
        "No",
        "sklearn TfidfVectorizer cosine",
        "Not downloaded or loaded. Retrieval ran with a classical substitute.",
    ),
    (
        "bge-m3",
        "Embeddings alternative",
        "No",
        "sklearn TfidfVectorizer cosine",
        "Not downloaded or loaded.",
    ),
    (
        "e5-small",
        "Embeddings alternative",
        "No",
        "sklearn TfidfVectorizer cosine",
        "Not downloaded or loaded.",
    ),
    (
        "all-MiniLM-L6-v2",
        "Embeddings alternative",
        "No",
        "sklearn TfidfVectorizer cosine",
        "Not downloaded or loaded.",
    ),
    (
        "Qdrant sparse vectors (BM25/SPLADE)",
        "Sparse retrieval (section 8)",
        "No",
        "in-process Okapi BM25 (k1=1.5, b=0.75)",
        "Qdrant was not installed and SPLADE was not loaded. The BM25 algorithm ran in-process.",
    ),
    (
        "fastembed sparse models",
        "Sparse retrieval alternative",
        "No",
        "in-process Okapi BM25",
        "Not downloaded or loaded.",
    ),
    (
        "bge-reranker-v2-m3",
        "Reranker (section 8)",
        "No",
        "lexical score: 0.6 coverage + 0.25 Jaccard + 0.15 phrase",
        "Not downloaded or loaded.",
    ),
    (
        "MiniLM cross-encoder",
        "Reranker alternative",
        "No",
        "lexical coverage reranker",
        "Not downloaded or loaded.",
    ),
    (
        "DeBERTa-v3 NLI (zero-shot)",
        "Ask classifier (sections 3.2 and 8)",
        "No",
        "feature rules on the ask text",
        "Not downloaded or loaded.",
    ),
    (
        "Fine-tuned DeBERTa-v3-small",
        "Ask classifier alternative",
        "No",
        "feature rules on the ask text",
        "Not trained and not downloaded.",
    ),
    (
        "KeyBERT-style with bge-small",
        "Keyphrases (sections 3.2 and 8)",
        "No",
        "content-term salience",
        "Not downloaded or loaded. bge-small was not loaded, so this embedding keyphrase method did not run.",
    ),
    (
        "YAKE",
        "Keyphrase alternative",
        "No",
        "content-term salience",
        "Not used.",
    ),
    (
        "GLiNER (medium or multi)",
        "Entity tagging (sections 3.4 and 8)",
        "No",
        "two rule taggers",
        "Not downloaded or loaded.",
    ),
    (
        "spaCy NER",
        "Entity tagging alternative",
        "No",
        "two rule taggers",
        "Not installed.",
    ),
    (
        "dslim/bert-base-NER",
        "Second NER (section 8)",
        "No",
        "stricter second rule tagger",
        "Not downloaded or loaded.",
    ),
    (
        "RoBERTa NER",
        "Second NER alternative",
        "No",
        "stricter second rule tagger",
        "Not downloaded or loaded.",
    ),
    (
        "libpostal (pypostal)",
        "Address parsing (section 8)",
        "No",
        "regex field parser",
        "Not installed. The regex parser is the whole address parser. The blueprint allows regex only as a PIN-code feature beside libpostal.",
    ),
    (
        "deepset/deberta-v3-base-squad2",
        "Extractive QA (sections 3.5 and 8)",
        "No",
        "unigram lexical span extractor",
        "Not downloaded or loaded.",
    ),
    (
        "roberta-base-squad2",
        "Second QA model for agreement",
        "No",
        "bigram lexical span extractor",
        "Not downloaded or loaded.",
    ),
    (
        "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli",
        "NLI (sections 3.5 and 8)",
        "No",
        "polarity, number-mismatch, and token-coverage judge",
        "Not downloaded or loaded.",
    ),
    (
        "Larger DeBERTa-v3 NLI",
        "NLI alternative",
        "No",
        "lexical NLI judge",
        "Not downloaded or loaded.",
    ),
    (
        "ContractNLI-tuned verifier",
        "NLI alternative, Phase 3",
        "No",
        "lexical NLI judge",
        "Not downloaded or loaded. No legal corpus is attached.",
    ),
    (
        "Logistic regression",
        "Pair matcher; decision and next-action heads (section 8)",
        "Yes",
        "sklearn LogisticRegression; decision head uses CalibratedClassifierCV method=sigmoid (Platt)",
        "The blueprint lists logistic regression for these roles. LightGBM, the other listed option, was not used.",
    ),
    (
        "LightGBM",
        "Pair matcher and heads alternative",
        "No",
        "sklearn LogisticRegression",
        "Not installed. Logistic regression, which the blueprint lists for the same roles, was used.",
    ),
    (
        "Small cross-encoder",
        "Pair matcher alternative",
        "No",
        "logistic regression over rapidfuzz ratio, Jaccard, surname, address, and role",
        "Not trained and not downloaded.",
    ),
    (
        "Small MLP",
        "Decision and next-action heads alternative",
        "No",
        "logistic regression with Platt scaling",
        "Not used. Logistic regression was used.",
    ),
    (
        "FLAN-T5 checkpoint",
        "Rewriter (section 3.7, Experiment A)",
        "No. Conflicts with FORBIDDEN.md",
        "deterministic assembly of verified findings",
        "Generative language model. Prohibited at any size, including a local checkpoint.",
    ),
    (
        "FLAN-T5 checkpoint",
        "Proposer (section 3.2.1, Experiment P)",
        "No. Conflicts with FORBIDDEN.md",
        "template analyzer plus grounding filter",
        "Generative language model. The proposer was not called.",
    ),
    (
        "FLAN-T5-large",
        "Rewriter alternative",
        "No. Conflicts with FORBIDDEN.md",
        "deterministic assembly of verified findings",
        "Generative language model. Prohibited.",
    ),
    (
        "LaMini-Flan-T5",
        "Rewriter alternative",
        "No. Conflicts with FORBIDDEN.md",
        "deterministic assembly of verified findings",
        "Generative language model. Prohibited. The blueprint also flags its card as non-commercial.",
    ),
    (
        "Qdrant (server or local mode)",
        "Vector database (section 8)",
        "No",
        "in-memory BM25 + TF-IDF index",
        "Not installed.",
    ),
    (
        "Qdrant Edge",
        "Vector database alternative",
        "No",
        "in-memory index",
        "Not installed.",
    ),
    (
        "NetworkX",
        "Graph (section 8)",
        "No",
        "in-memory adjacency list (lab/common/graph.py)",
        "Not installed.",
    ),
    (
        "Kuzu",
        "Graph alternative",
        "No",
        "in-memory adjacency list",
        "Not installed.",
    ),
    (
        "Neo4j",
        "Graph alternative",
        "No",
        "in-memory adjacency list",
        "Not installed.",
    ),
    (
        "dateparser and a small calculator",
        "Dates and amounts (section 8)",
        "Yes",
        "dateparser plus timedelta, plus code that compares and sums amounts",
        "This matches the blueprint's primary date tool.",
    ),
    (
        "Duckling",
        "Date alternative",
        "No",
        "dateparser plus timedelta",
        "The primary date tool was used, so Duckling was not loaded.",
    ),
    (
        "ONNX Runtime int8",
        "Encoder runtime (section 8)",
        "No",
        "CPython running the classical substitutes",
        "No encoder checkpoint was loaded, so nothing was exported to ONNX.",
    ),
    (
        "CTranslate2 int8",
        "FLAN-T5 runtime (section 8)",
        "No. Conflicts with FORBIDDEN.md",
        "no generative runtime",
        "CTranslate2 generation is prohibited.",
    ),
    (
        "SQLite",
        "Recall memory (section 3.3; Qdrant is the alternative)",
        "Yes",
        "SQLite via lab/common/memory.py",
        "This matches the blueprint's primary recall store.",
    ),
    (
        "Isotonic regression",
        "Calibration alternative (section 9)",
        "No",
        "Platt scaling (sigmoid)",
        "Platt scaling is the other method the blueprint names, and it was used.",
    ),
    (
        "bge-small-en-v1.5",
        "Embeddings -- real-model reruns EXP-029 and EXP-032 only",
        "No, but a real substitute was loaded",
        "spaCy en_core_web_md static word vectors (real pretrained, not bge)",
        "huggingface.co is blocked by this sandbox's egress policy (403 CONNECT, policy denial). spaCy's pipelines ship as plain pip wheels, not from huggingface.co, and are reachable. See lab/common/real_models.py.",
    ),
    (
        "GLiNER / dslim/bert-base-NER",
        "Entity tagging -- real-model reruns EXP-032 and EXP-033 only",
        "No, but a real substitute was loaded",
        "spaCy en_core_web_sm NER, a CNN tagger trained on OntoNotes 5 (real pretrained, not GLiNER or BERT-NER)",
        "huggingface.co is blocked by this sandbox's egress policy (403 CONNECT, policy denial). See lab/common/real_models.py.",
    ),
]

RERUN_MAP = [
    ("EXP-001", "DeBERTa QA, DeBERTa NLI, and bge retrieval inside the controller", "EXP-027"),
    ("EXP-002", "DeBERTa-v3 NLI, KeyBERT with bge-small, GLiNER", "EXP-028"),
    ("EXP-003", "No neural model is assigned to chunking", "none"),
    ("EXP-004", "bge-small-en-v1.5, Qdrant BM25/SPLADE, bge-reranker-v2-m3, NetworkX", "EXP-029 (closed, real pretrained spaCy vectors, not bge)"),
    ("EXP-005", "deepset/deberta-v3-base-squad2 and roberta-base-squad2", "EXP-030"),
    ("EXP-006", "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli", "EXP-031"),
    ("EXP-007", "DeBERTa SQuAD2 for the hops. dateparser stays", "EXP-032 (closed, real spaCy retrieval+NER multi-hop chain on real documents, not DeBERTa SQuAD2)"),
    ("EXP-008", "GLiNER, dslim/bert-base-NER, libpostal", "EXP-033 (closed, real pretrained spaCy NER, not GLiNER/BERT-NER)"),
    ("EXP-009", "GLiNER, BERT-NER, and bge similarity. Logistic regression stays", "EXP-034"),
    ("EXP-010", "DeBERTa QA and DeBERTa NLI", "EXP-035"),
    ("EXP-011", "Encoder features into the existing logistic-regression heads", "EXP-036"),
    ("EXP-012", "DeBERTa NLI for the support check. dateparser stays", "EXP-037"),
    ("EXP-013", "DeBERTa SQuAD2", "EXP-038"),
    ("EXP-014", "DeBERTa SQuAD2. dateparser stays", "EXP-039"),
    ("EXP-015", "bge-small-en-v1.5 embeddings", "EXP-040"),
    ("EXP-016", "SQLite was the proposed recall store", "none"),
    ("EXP-017", "DeBERTa NLI for fidelity. FLAN-T5 rewriter is blocked", "EXP-041 and EXP-046"),
    ("EXP-018", "bge for repetition. FLAN-T5 unit writer is blocked", "EXP-042 and EXP-046"),
    ("EXP-019", "FLAN-T5 proposer is blocked", "EXP-043 and EXP-046"),
    ("EXP-020", "Encoder stack. FLAN-T5 stays out", "EXP-044"),
    ("EXP-021", "Encoder latency. CTranslate2 stays out", "EXP-045"),
]

MODELS_USED = {
    "EXP-001": "No blueprint checkpoint. The controller ran lexical QA, lexical NLI, TF-IDF, in-process BM25, and logistic-regression heads. DeBERTa, GLiNER, bge, and FLAN-T5 were not loaded. FLAN-T5 conflicts with FORBIDDEN.md. Rerun: EXP-027.",
    "EXP-002": "Proposed for this component: zero-shot DeBERTa-v3 NLI, fine-tuned DeBERTa-v3-small, KeyBERT with bge-small, YAKE, and GLiNER. None of those were loaded. The run used feature rules and content-term salience. Rerun: EXP-028.",
    "EXP-003": "The blueprint assigns no neural model to structure-aware chunking. This run used code (heading rules and extractive summaries). FLAN-T5 was not used to write summaries and conflicts with FORBIDDEN.md. There is no model rerun for this entry.",
    "EXP-004": "Proposed: bge-small-en-v1.5 (alternatives bge-m3, e5-small, all-MiniLM-L6-v2), Qdrant BM25/SPLADE (alternative fastembed), bge-reranker-v2-m3 (alternative MiniLM cross-encoder), and NetworkX (alternatives Kuzu, Neo4j). None of those were loaded. The run used TF-IDF cosine, in-process Okapi BM25, a lexical reranker, and an adjacency list. Rerun: EXP-029.",
    "EXP-005": "Proposed: deepset/deberta-v3-base-squad2 and roberta-base-squad2. Neither was loaded. The run used a unigram lexical span extractor and a bigram lexical span extractor. Rerun: EXP-030.",
    "EXP-006": "Proposed: MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli, with a larger DeBERTa-v3 NLI and ContractNLI as alternatives. None were loaded. The run used a polarity, number-mismatch, and token-coverage judge. Rerun: EXP-031.",
    "EXP-007": "dateparser was used, which is the blueprint's date tool. Duckling was not used. Hop spans came from the lexical QA extractor. deepset/deberta-v3-base-squad2 and roberta-base-squad2 were not loaded. Rerun the QA hops as EXP-032 and keep dateparser.",
    "EXP-008": "Proposed: GLiNER, spaCy, dslim/bert-base-NER, RoBERTa NER, and libpostal. None were loaded. The run used two rule taggers, a regex address parser, and lexical QA for roles. Rerun: EXP-033.",
    "EXP-009": "Logistic regression and rapidfuzz string features were used. The blueprint allows logistic regression for the pair matcher. LightGBM and a small cross-encoder were not used. GLiNER, BERT-NER, and bge similarity were not loaded, so these features are not encoder features. Rerun: EXP-034. Keep logistic regression and rapidfuzz.",
    "EXP-010": "DeBERTa SQuAD2, MoritzLaurer DeBERTa-v3 MNLI, and bge-reranker-v2-m3 were not loaded. The loop used lexical QA, lexical NLI, and lexical retrieval. Rerun: EXP-035.",
    "EXP-011": "Logistic regression with Platt scaling (CalibratedClassifierCV, method=sigmoid) was used for the decision head, and multinomial logistic regression for the next-action head. The blueprint allows logistic regression here. LightGBM and a small MLP were not used. Features came from the lexical QA/NLI pipeline, not from DeBERTa. Rerun: EXP-036.",
    "EXP-012": "Quote, coverage, citation, and qualifier checks are code. dateparser was used for the calculation check. The support check used lexical NLI. MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli was not loaded. Rerun: EXP-037.",
    "EXP-013": "Provenance tags are code. Answer spans came from lexical QA. deepset/deberta-v3-base-squad2 was not loaded. FLAN-T5 was not used. Rerun: EXP-038.",
    "EXP-014": "Cross-domain spans came from lexical QA. dateparser was used for ordering. DeBERTa SQuAD2 was not loaded. Rerun: EXP-039 and keep dateparser.",
    "EXP-015": "The page index used TF-IDF. bge-small-en-v1.5 and Qdrant were not loaded. Rerun: EXP-040.",
    "EXP-016": "SQLite was used, which is the blueprint's recall store. A Qdrant collection was the named alternative and was not used. No encoder checkpoint applies to this entry.",
    "EXP-017": "The proposed rewriter is FLAN-T5, with FLAN-T5-large and LaMini-Flan-T5 as alternatives and CTranslate2 as the runtime. CONFLICTS WITH FORBIDDEN.md. Those models were not used and must not be run. The run copied verified findings and checked them with lexical bidirectional NLI. A DeBERTa NLI rerun of the fidelity check is EXP-041. The FLAN-T5 rerun is EXP-046 and is blocked.",
    "EXP-018": "Unit text was copied from verified findings. FLAN-T5, FLAN-T5-large, LaMini-Flan-T5, and CTranslate2 were not used. CONFLICTS WITH FORBIDDEN.md. Repetition used TF-IDF, not bge. Rerun similarity with bge as EXP-042. The FLAN-T5 writer stays blocked (EXP-046).",
    "EXP-019": "The proposer is FLAN-T5 in section 3.2.1. CONFLICTS WITH FORBIDDEN.md. It was not called. The run used template queries plus the grounding filter. The measured field proposer_model_called is false. The rerun is EXP-043 and is blocked.",
    "EXP-020": "The end-to-end loop used the same lexical stack as EXP-001: lexical QA, lexical NLI, TF-IDF, and in-process BM25. DeBERTa, GLiNER, bge, and FLAN-T5 were not loaded. FLAN-T5 conflicts with FORBIDDEN.md. Rerun: EXP-044.",
    "EXP-021": "Stage timings are for the lexical stack. The measured models_loaded list is empty. ONNX Runtime was not used because no encoder was loaded. CTranslate2 conflicts with FORBIDDEN.md and was not used. Rerun: EXP-045.",
}

ENCODER_METHOD = (
    "Not run. When this is picked up, load the named checkpoint locally and measure again. "
    "Not a generative model. Do not call a hosted generative API. Do not use the checkpoint to write answer text. "
    "Write a new results.json only after the checkpoint actually runs. Do not copy the closed lexical scores forward."
)


def _prior(*slugs: str) -> list[str]:
    files = []
    for slug in slugs:
        files.append(f"lab/{slug}/run.py")
        files.append(f"data/{slug}/results.json")
    files.extend(["lab/config/models.json", "FORBIDDEN.md", "ARCHITECTURE.md"])
    return files


def _todo(exp_id, title, goal, method, models_used, files, conclusion) -> dict:
    return {
        "id": exp_id,
        "title": title,
        "status": "todo",
        "goal": goal,
        "method": method,
        "models_used": models_used,
        "referenced_files": files,
        "results_prose": "Not run.",
        "conclusion": conclusion,
        "scale_down": "",
    }


TODOS = [
    {
        "id": "EXP-022",
        "title": "On-disk hybrid index",
        "status": "todo",
        "goal": "Repeat the hybrid retrieval measurement with an on-disk index once the corpus no longer fits the process index.",
        "method": "Not run.",
        "models_used": "bge, SPLADE, fastembed, and Qdrant are still not loaded. This todo is an on-disk index for the classical hybrid scorer. Do not add a generative retriever.",
        "referenced_files": [],
        "results_prose": "Not run.",
        "conclusion": "Todo. Do not add a generative retriever.",
        "scale_down": "",
    },
    {
        "id": "EXP-023",
        "title": "Human fluency rating",
        "status": "todo",
        "goal": "Collect a human 1-to-5 fluency rating for deterministic assemblies. Do not impute the score.",
        "method": "Not run.",
        "models_used": "No model. A person rates fluency. Filling the score with FLAN-T5 or any other generative model conflicts with FORBIDDEN.md.",
        "referenced_files": [],
        "results_prose": "Not run.",
        "conclusion": "Todo.",
        "scale_down": "",
    },
    {
        "id": "EXP-024",
        "title": "Local span tagger",
        "status": "todo",
        "goal": "If rule-tagger hard-slice F1 is too low, train a span tagger only on locally labeled spans.",
        "method": "Not run.",
        "models_used": "This todo trains a span tagger on labels stored in the repository. It is separate from the GLiNER and dslim/bert-base-NER rerun (EXP-033). Do not download a generative model.",
        "referenced_files": [],
        "results_prose": "Not run.",
        "conclusion": "Todo. Do not download a pretrained NER or generative model.",
        "scale_down": "",
    },
    {
        "id": "EXP-026",
        "title": "Qualification rules",
        "status": "todo",
        "goal": "Add code rules for except, unless, and provided that if the lexical judge keeps missing them.",
        "method": "Not run.",
        "models_used": "Code rules only. ContractNLI is a Phase 3 NLI alternative and is not this todo. The checker stays deterministic.",
        "referenced_files": [],
        "results_prose": "Not run.",
        "conclusion": "Todo. This stays a deterministic checker.",
        "scale_down": "",
    },
]

RERUN_TODOS = [
    _todo(
        "EXP-027",
        "Rerun the controller with the proposed encoders",
        "Re-measure EXP-001 once DeBERTa extractive QA, DeBERTa NLI, and bge retrieval are actually loaded. Keep FLAN-T5 out of the controller.",
        ENCODER_METHOD,
        "Not run. Proposed: deepset/deberta-v3-base-squad2, MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli, bge-small-en-v1.5. These are encoders. FLAN-T5 conflicts with FORBIDDEN.md and must not be added.",
        _prior("exp_001_controller"),
        "Todo. Replace the EXP-001 numbers only after a real encoder run.",
    ),
    _todo(
        "EXP-028",
        "Rerun the ask analyzer with DeBERTa, KeyBERT, and GLiNER",
        "Re-measure EXP-002 with a zero-shot DeBERTa-v3 NLI ask classifier, KeyBERT using bge-small-en-v1.5, and GLiNER on the ask.",
        ENCODER_METHOD,
        "Not run. Proposed: DeBERTa-v3 NLI, bge-small-en-v1.5, GLiNER. Not generative. Do not call a hosted generative API. Do not use these models to write answer text. FLAN-T5 is not the ask classifier and conflicts with FORBIDDEN.md.",
        _prior("exp_002_ask_analyzer"),
        "Todo. The closed EXP-002 scores are rule scores.",
    ),
    _todo(
        "EXP-030",
        "Rerun extractive QA with DeBERTa and RoBERTa SQuAD2",
        "Re-measure EXP-005 with deepset/deberta-v3-base-squad2 and roberta-base-squad2 as the agreement model.",
        ENCODER_METHOD,
        "Not run. Proposed: deepset/deberta-v3-base-squad2 and roberta-base-squad2. Not generative. Do not use either model to write answer text; they extract spans.",
        _prior("exp_005_extractive_qa"),
        "Todo. The closed EXP-005 scores are lexical-extractor scores.",
    ),
    _todo(
        "EXP-031",
        "Rerun the NLI judge with DeBERTa-v3 MNLI",
        "Re-measure EXP-006 with MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli.",
        ENCODER_METHOD + " A larger DeBERTa-v3 NLI is an alternative. ContractNLI waits on a legal collection and is not this rerun.",
        "Not run. Proposed: MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli. Not generative.",
        _prior("exp_006_nli_judge"),
        "Todo. The closed EXP-006 scores, including exception accuracy 0, are lexical-judge scores.",
    ),
    _todo(
        "EXP-034",
        "Rerun entity resolution on encoder mentions and bge similarity",
        "Re-measure EXP-009 after GLiNER and BERT-NER supply the mentions and bge-small-en-v1.5 supplies a similarity feature. Keep logistic regression and rapidfuzz.",
        ENCODER_METHOD + " Do not swap the head to a generative model. LightGBM remains optional.",
        "Not run. Proposed taggers and embedder: GLiNER, dslim/bert-base-NER, bge-small-en-v1.5. Logistic regression stays. Not generative.",
        _prior("exp_009_entity_resolve"),
        "Todo. The closed pair-matcher accuracy is a logistic-regression score on rule features.",
    ),
    _todo(
        "EXP-035",
        "Rerun gap resolution with DeBERTa QA and NLI",
        "Re-measure EXP-010 with DeBERTa SQuAD2 spans and DeBERTa NLI support checks.",
        ENCODER_METHOD,
        "Not run. Proposed: deepset/deberta-v3-base-squad2 and MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli. Not generative.",
        _prior("exp_010_gap_resolution"),
        "Todo. The closed EXP-010 accuracy is a lexical-loop score.",
    ),
    _todo(
        "EXP-036",
        "Rerun the decision heads on encoder features",
        "Re-measure EXP-011 with features taken from the real DeBERTa QA and NLI pipeline. The head may stay logistic regression.",
        ENCODER_METHOD + " Do not add a generative model. LightGBM and a small MLP are optional alternatives to logistic regression, not a reason to drop the measured head before a new run.",
        "Not run. Proposed feature source: DeBERTa QA and DeBERTa NLI. The head used here was already logistic regression, which the blueprint allows. Not generative.",
        _prior("exp_011_decision_heads"),
        "Todo. The closed test accuracy is on templated lexical features, not on MNLI or SQuAD features.",
    ),
    _todo(
        "EXP-037",
        "Rerun the support check with DeBERTa NLI",
        "Re-measure the EXP-012 support re-check with MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli. Keep dateparser for the calculation check.",
        ENCODER_METHOD + " Do not replace dateparser.",
        "Not run. Proposed: MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli. dateparser stays. Not generative.",
        _prior("exp_012_verification"),
        "Todo. Quote and coverage checks stay code.",
    ),
    _todo(
        "EXP-038",
        "Rerun provenance QA with DeBERTa SQuAD2",
        "Re-measure EXP-013 answer spans with deepset/deberta-v3-base-squad2. Provenance tags stay code.",
        ENCODER_METHOD,
        "Not run. Proposed: deepset/deberta-v3-base-squad2. Not generative. FLAN-T5 must not write the answer.",
        _prior("exp_013_provenance"),
        "Todo. The closed faithfulness score is a lexical-QA score.",
    ),
    _todo(
        "EXP-039",
        "Rerun cross-domain QA with DeBERTa SQuAD2",
        "Re-measure EXP-014 with deepset/deberta-v3-base-squad2. Keep dateparser for ordering.",
        ENCODER_METHOD + " Do not replace dateparser. Do not relabel the recipe items to hide a miss.",
        "Not run. Proposed: deepset/deberta-v3-base-squad2. dateparser stays. Not generative.",
        _prior("exp_014_reasoning"),
        "Todo. The closed domain scores are lexical-QA scores.",
    ),
    _todo(
        "EXP-040",
        "Rerun paged retrieval with bge embeddings",
        "Re-measure EXP-015 needle recall and the page index with bge-small-en-v1.5.",
        ENCODER_METHOD,
        "Not run. Proposed: bge-small-en-v1.5. Not generative.",
        _prior("exp_015_paged_memory"),
        "Todo. The closed needle scores are TF-IDF scores.",
    ),
    _todo(
        "EXP-041",
        "Rerun fidelity NLI with DeBERTa; do not load FLAN-T5",
        "Re-measure the EXP-017 bidirectional NLI check with MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli. The rewriter stays the deterministic copy.",
        ENCODER_METHOD + " BLOCKED for the rewriter: do not download or run FLAN-T5, FLAN-T5-large, LaMini-Flan-T5, or CTranslate2 generation. CONFLICTS WITH FORBIDDEN.md.",
        "DeBERTa NLI is an encoder and may be measured later. FLAN-T5, FLAN-T5-large, LaMini-Flan-T5, and CTranslate2 CONFLICT WITH FORBIDDEN.md and must not be run. The deterministic copy stays.",
        _prior("exp_017_fidelity"),
        "Todo for the DeBERTa check only. The FLAN-T5 rewriter rerun is blocked. See EXP-046.",
    ),
    _todo(
        "EXP-042",
        "Rerun repetition similarity with bge; do not load FLAN-T5",
        "Re-measure EXP-018 repetition with bge-small-en-v1.5. Unit text stays copied from verified findings.",
        ENCODER_METHOD + " BLOCKED for the unit writer: do not download or run FLAN-T5, FLAN-T5-large, LaMini-Flan-T5, or CTranslate2 generation. CONFLICTS WITH FORBIDDEN.md.",
        "bge-small-en-v1.5 is an encoder and may be measured later. FLAN-T5 as the unit writer CONFLICTS WITH FORBIDDEN.md and must not be run.",
        _prior("exp_018_longform"),
        "Todo for the bge similarity check only. The FLAN-T5 writer is blocked. See EXP-046.",
    ),
    _todo(
        "EXP-043",
        "Blocked: do not rerun the proposer with FLAN-T5",
        "The blueprint assigns FLAN-T5 to the proposer (section 3.2.1, Experiment P). That rerun is not allowed. The grounding filter from EXP-019 stays.",
        "BLOCKED. Do not download or run FLAN-T5 as a proposer. Do not call a hosted generative API. Do not ask another model to write proposals.",
        "Still CONFLICTS WITH FORBIDDEN.md even after the 2026-10-14 bounded-rewriter exception (see EXP-048): that exception covers the rewriter role only, never the proposer. This entry records the gap. It is not permission to run the model. The template analyzer and grounding filter stay.",
        _prior("exp_019_proposal_filter"),
        "Blocked by FORBIDDEN.md. Leave EXP-019 on the deterministic path.",
    ),
    _todo(
        "EXP-044",
        "Rerun the red-team loop with the encoder stack",
        "Re-measure EXP-020 after the encoder reruns above are real. The loop still abstains when support fails.",
        ENCODER_METHOD + " BLOCKED: do not add FLAN-T5 to the rewrite case or any other case. CONFLICTS WITH FORBIDDEN.md.",
        "Not run. Proposed stack: DeBERTa QA, DeBERTa NLI, bge retrieval. FLAN-T5 conflicts with FORBIDDEN.md and must stay out.",
        _prior("exp_020_redteam_e2e"),
        "Todo. Run this only after the encoder checkpoints have actually been measured. Do not reuse the lexical red-team scores as encoder scores.",
    ),
    _todo(
        "EXP-045",
        "Rerun latency after the encoders are loaded",
        "Re-measure EXP-021 stage latency and memory with the encoder checkpoints resident. ONNX Runtime int8 is an allowed encoder runtime for that later measurement.",
        ENCODER_METHOD + " BLOCKED: do not time CTranslate2 generation and do not load FLAN-T5. CONFLICTS WITH FORBIDDEN.md.",
        "Not run. ONNX Runtime int8 is an encoder runtime and is allowed once an encoder exists. CTranslate2 generation CONFLICTS WITH FORBIDDEN.md and must not be run.",
        _prior("exp_021_latency"),
        "Todo. The closed timings describe the lexical stack, whose models_loaded list is empty.",
    ),
    {
        "id": "EXP-046",
        "title": "Still blocked: FLAN-T5 proposer, larger FLAN-T5 variants, and CTranslate2 generation",
        "status": "todo",
        "goal": "Record that the blueprint's remaining generative pieces were not used and must not be run: FLAN-T5 as proposer (section 3.2.1, Experiment P), FLAN-T5-large, LaMini-Flan-T5, and CTranslate2 int8 generation. The rewriter role is no longer blanket-blocked -- see EXP-048 for the narrow, bounded exception recorded in FORBIDDEN.md on 2026-10-14.",
        "method": "BLOCKED. Do not download or run FLAN-T5 as a proposer, FLAN-T5-large, LaMini-Flan-T5, or CTranslate2 generation. Do not call a hosted generative API. A small FLAN-T5/T5 checkpoint in the rewriter role only is EXP-048, not this entry.",
        "models_used": "CONFLICTS WITH FORBIDDEN.md. These are generative language models or roles the bounded exception does not cover. The deterministic proposer path (template analyzer plus grounding filter) stays. This entry exists so the remaining gap is visible. It is not permission to run these models or roles.",
        "referenced_files": [
            "FORBIDDEN.md",
            "ARCHITECTURE.md",
            "lab/common/proposals.py",
            "lab/exp_019_proposal_filter/run.py",
        ],
        "results_prose": "Not run. Must not be run.",
        "conclusion": "Blocked by FORBIDDEN.md. EXP-019 stays on the deterministic path. EXP-017 and EXP-018's fidelity/repetition checks are unaffected by this entry; a bounded-rewriter rerun of those two, once EXP-048 exists, would be a separate future todo.",
        "scale_down": "",
    },
    {
        "id": "EXP-048",
        "title": "Bounded FLAN-T5 rewriter (small checkpoint, fidelity-gated)",
        "status": "todo",
        "goal": (
            "Implement and measure the narrow rewriter exception recorded in FORBIDDEN.md on 2026-10-14 "
            "(project owner's explicit decision): load flan-t5-small, feed it only already-verified "
            "(statement, citation) findings plus a style instruction, run the section 3.7 fidelity validator "
            "on its output, and fall back to the unchanged lab/common/assemble.py text on any failure. "
            "Measure fidelity pass rate, fallback rate, and a human or proxy fluency rating, the same way "
            "EXP-017 and EXP-023 (still todo) would."
        ),
        "method": (
            "Not run. Blocked: huggingface.co is denied by this sandbox's egress policy, so flan-t5-small "
            "cannot be downloaded here (same block that limits EXP-029/032/033/040/etc. to spaCy real-model "
            "substitutes; see lab/common/real_models.py). This todo is expected to be picked up on a machine "
            "or environment where huggingface.co is reachable -- for example, a laptop, rather than this "
            "sandbox."
        ),
        "models_used": (
            "Not run. Proposed: a small local flan-t5-small checkpoint (or comparably small T5 model, under "
            "~300M params), loaded with transformers (or converted to CTranslate2 int8, as ARCHITECTURE.md "
            "section 8 recommends, once the plain-transformers path is measured). Rewriter role only -- never "
            "extraction, answering, or support/contradiction judging. Not an API call; a local checkpoint only."
        ),
        "referenced_files": [
            "FORBIDDEN.md",
            "OBJECTIVE.md",
            "lab/config/models.json",
            "ARCHITECTURE.md",
            "lab/common/assemble.py",
            "lab/common/harness.py",
            "lab/exp_017_fidelity/run.py",
            "lab/exp_018_longform/run.py",
        ],
        "results_prose": "Not run.",
        "conclusion": (
            "Todo, blocked on network access to huggingface.co from wherever this is run next. Once "
            "unblocked: add lab/common/real_rewriter.py (model load, a render_unit_generative(leaf, glossary) "
            "counterpart to assemble.render_unit, and the fidelity gate reusing harness.fidelity()), wire it "
            "into assemble.assemble() behind a flag so the deterministic path remains the default and the "
            "fallback, and write lab/exp_048_bounded_rewriter/run.py following the existing exploration "
            "pattern (Run, write_json, finish, models_used). Do not let this checkpoint touch extraction or "
            "verification; those stay on the existing lexical/real-NER/real-embedding substitutes."
        ),
        "scale_down": "",
    },
]


def main():
    results = []
    for path in sorted((ROOT / "data").glob("exp_*/results.json")):
        results.append(json.loads(path.read_text()))
    results.sort(key=lambda row: row["id"])
    lines = [
        "# Explorations",
        "",
        "An exploration is one research step. Status is `todo`, `open`, or `closed`.",
        "Closed results below were written by `lab/exp_*/run.py` into `data/exp_*/results.json` and copied here by `lab/render_explorations.py`.",
        "Do not edit the numbers by hand. Re-run the exploration and render again.",
        "",
        "Generative language models were not used in any exploration. The blueprint's exact encoder checkpoints (bge, DeBERTa, GLiNER) were not loaded either -- huggingface.co is blocked by this sandbox's egress policy. EXP-029, EXP-032, and EXP-033 are the one exception: they load real, reachable, non-generative substitutes (spaCy's pretrained NER and static vectors) in place of the blueprint checkpoints and say so in their own Models used line. Read **Blueprint models were not used** before treating any score as a DeBERTa, GLiNER, bge, or FLAN-T5 result.",
        "",
    ]
    lines.extend(_blueprint_section())
    for row in results:
        lines.extend(_section(row))
    lines.append("## Follow-up todos")
    lines.append("")
    for row in TODOS:
        lines.extend(_section(row))
    lines.append("## Proposed-model reruns")
    lines.append("")
    lines.append("These entries are `todo`. None of them has been run. A blocked entry must stay blocked.")
    lines.append("")
    for row in RERUN_TODOS:
        lines.extend(_section(row))
    (ROOT / "EXPLORATIONS.md").write_text("\n".join(lines) + "\n")
    print(
        f"wrote EXPLORATIONS.md with {len(results)} closed, {len(TODOS)} todo, "
        f"and {len(RERUN_TODOS)} rerun todos"
    )


def _blueprint_section() -> list[str]:
    lines = [
        "## Blueprint models were not used",
        "",
        "Read this before any score below. The closed numbers were not changed by this note.",
        "",
        "ARCHITECTURE.md section 8 names the PoC models. Section 3.2.1 names FLAN-T5 as the untrusted proposer. Section 3.7 names FLAN-T5 as the rewriter. The runtime lines under section 8 name ONNX Runtime for encoders and CTranslate2 for FLAN-T5. Section 3.3 names SQLite for recall memory. Section 9 names Platt scaling and isotonic regression for calibration.",
        "",
        "**Those proposed models were not used**, except the rows whose Used cell is Yes: logistic regression, dateparser, SQLite, and Platt scaling. Every other closed score was measured with the substitute in the last column. Do not cite these scores as DeBERTa, GLiNER, bge, KeyBERT, libpostal, or FLAN-T5 results.",
        "",
        "The same substitute list is stored in `lab/config/models.json`.",
        "",
        "| Proposed model | Component | Used in this POC? | Substitute actually used | Reason |",
        "|---|---|---|---|---|",
    ]
    for model, component, used, substitute, reason in BLUEPRINT:
        lines.append(f"| {model} | {component} | {used} | {substitute} | {reason} |")
    lines.extend(
        [
            "",
            "### Conflicts with FORBIDDEN.md",
            "",
            "These proposed models are generative language models. FORBIDDEN.md forbids them at any size, including a local checkpoint and including CTranslate2 generation. They were not used. The rerun entries that name them are blocked. A blocked entry is not permission to run the model.",
            "",
            "- FLAN-T5 as the rewriter (section 3.7, Experiment A). See EXP-046.",
            "- FLAN-T5 as the proposer (section 3.2.1, Experiment P). See EXP-043 and EXP-046.",
            "- FLAN-T5-large. See EXP-046.",
            "- LaMini-Flan-T5. See EXP-046.",
            "- CTranslate2 int8 generation. See EXP-046.",
            "",
            "DeBERTa, GLiNER, BERT-NER, RoBERTa, bge, MiniLM, e5, spaCy, libpostal, Qdrant, SPLADE, fastembed, NetworkX, Kuzu, Neo4j, and LightGBM are not generative decoders. Their rerun entries are unrun measurement work. A future run still must not call a hosted generative API and must not use the checkpoint to write answer text.",
            "",
            "### Which closed exploration to rerun",
            "",
            "| Closed exploration | Proposed piece that was skipped | Rerun todo |",
            "|---|---|---|",
        ]
    )
    for exp_id, skipped, todo in RERUN_MAP:
        lines.append(f"| {exp_id} | {skipped} | {todo} |")
    lines.append("")
    return lines


def _section(row: dict) -> list[str]:
    files = row.get("referenced_files") or []
    file_block = "\n".join(f"- `{path}`" for path in files) if files else "- none yet"
    metrics = row.get("metrics")
    metric_block = ""
    if metrics:
        metric_block = "```json\n" + json.dumps(metrics, indent=2, ensure_ascii=False) + "\n```\n"
    elapsed = row.get("elapsed_sec")
    rss = row.get("peak_rss_mb")
    extra = ""
    if elapsed is not None:
        extra = f"\nElapsed seconds: {elapsed}. Peak RSS MB: {rss}.\n"
    models = row.get("models_used") or MODELS_USED.get(row.get("id", ""))
    lines = [
        f"## {row['id']} {row['title']}",
        "",
        f"- Status: `{row['status']}`",
    ]
    if models:
        lines.append(f"- Models used: {models}")
    lines.extend(
        [
            f"- Goal: {row['goal']}",
            f"- Method: {row['method']}",
            "- Referenced files:",
            file_block,
            f"- Results: {row.get('results_prose', '')}",
            metric_block.rstrip("\n") if metric_block else "",
            extra.rstrip("\n") if extra else "",
            f"- Scale-down: {row.get('scale_down', '')}",
            f"- Conclusion: {row.get('conclusion', '')}",
            "",
        ]
    )
    return lines


if __name__ == "__main__":
    main()
