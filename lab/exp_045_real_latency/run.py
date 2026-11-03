"""EXP-045: rerun EXP-021's stage latency with the encoder checkpoints resident.

Same 40 passages and benchmark harness as EXP-021. Reuses EXP-027's
monkeypatch adapters for the end-to-end timing. ONNX Runtime int8 (an
allowed encoder runtime once an encoder exists, per the todo) is not
applied here -- these are the plain transformers/sentence-transformers
checkpoints, same as every other rerun in this batch; quantized runtimes
are a follow-up, not attempted in this pass. CTranslate2/FLAN-T5 are not
timed or loaded (FORBIDDEN.md).

RETIRED (2026-11-03, reasoning-layer audit follow-up): see EXP-027's
run.py docstring -- lab.common.engine was deleted once its capabilities
were ported into lab.common.brain.reason. This script's results.json
stays as the permanent record; a literal rerun now ImportErrors.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import lab.common.engine as engine_mod
from lab.common.ask import analyze
from lab.common.chunking import chunk_document
from lab.common.harness import Run, peak_rss_mb
from lab.common.real_encoders import BGE_MODEL_NAME, NLI_MODEL_NAME, QA_MODEL_NAME, bge_embed, model_card, real_nli, real_qa
from lab.exp_027_real_controller.run import RealIndex, real_answer_with_agreement, real_judge

FILES = [
    "lab/exp_045_real_latency/run.py",
    "lab/exp_027_real_controller/run.py",
    "lab/common/ask.py",
    "lab/common/chunking.py",
    "lab/common/engine.py",
    "lab/common/real_encoders.py",
    "lab/common/harness.py",
    "data/exp_021_latency/results.json",
    "data/exp_045_real_latency/results.json",
]


def bench(fn, repeats: int = 20) -> float:
    fn()
    t0 = time.perf_counter()
    for _ in range(repeats):
        fn()
    return round((time.perf_counter() - t0) / repeats, 6)


def main():
    run = Run("EXP-045", "exp_045_real_latency")
    passages = [{"id": f"P{i}", "text": f"The value of slot {i} is {i} days."} for i in range(40)]
    passages[3] = {"id": "P3", "text": "The notice period is 30 days."}
    doc = "PARTIES:\n" + "\n".join(p["text"] for p in passages)
    index = RealIndex(passages)

    orig = (engine_mod.answer_with_agreement, engine_mod.judge, engine_mod.Index)
    engine_mod.answer_with_agreement = real_answer_with_agreement
    engine_mod.judge = real_judge
    engine_mod.Index = RealIndex
    try:
        timings = {
            "ask_analyze_sec": bench(lambda: analyze("What is the notice period and who is the Lessee?")),
            "chunk_sec": bench(lambda: chunk_document(doc, "D1", max_words=30), repeats=10),
            "bge_search_sec": bench(lambda: index.search("notice period", top_k=10), repeats=10),
            "qa_sec": bench(lambda: real_qa("What is the notice period?", passages[3]["text"]), repeats=10),
            "nli_sec": bench(lambda: real_nli("The notice period is 30 days.", "The notice period is 30 days."), repeats=10),
            "bge_embed_sec": bench(lambda: bge_embed(["The notice period is 30 days."]), repeats=10),
            "e2e_sec": bench(lambda: engine_mod.run_task("What is the notice period?", passages), repeats=3),
        }
    finally:
        engine_mod.answer_with_agreement, engine_mod.judge, engine_mod.Index = orig

    metrics = {
        "mean_seconds": timings,
        "peak_rss_mb": peak_rss_mb(),
        "cpu_note": "Measured on this process (CPU only, no GPU). RSS is peak resident set for the whole run, including every model load, not a per-model figure.",
        "models_loaded": [QA_MODEL_NAME, NLI_MODEL_NAME, BGE_MODEL_NAME],
        "real_model_card": model_card(),
    }
    exp021_path = ROOT / "data" / "exp_021_latency" / "results.json"
    if exp021_path.exists():
        import json

        exp021 = json.loads(exp021_path.read_text())["metrics"]
        metrics["vs_exp_021_lexical"] = {
            "exp_021_e2e_sec": exp021["mean_seconds"]["e2e_sec"],
            "exp_045_e2e_sec": timings["e2e_sec"],
            "exp_021_qa_sec": exp021["mean_seconds"]["qa_sec"],
            "exp_045_qa_sec": timings["qa_sec"],
            "exp_021_nli_sec": exp021["mean_seconds"]["nli_sec"],
            "exp_045_nli_sec": timings["nli_sec"],
            "exp_021_peak_rss_mb": exp021["peak_rss_mb"],
            "exp_045_peak_rss_mb": metrics["peak_rss_mb"],
        }
    prose = (
        "Mean stage times in seconds with the encoder checkpoints resident: "
        + ", ".join(f"{name} {value}" for name, value in timings.items())
        + f". Peak RSS {metrics['peak_rss_mb']} MB (EXP-021's lexical stack: "
        f"{metrics.get('vs_exp_021_lexical', {}).get('exp_021_peak_rss_mb')} MB; e2e "
        f"{metrics.get('vs_exp_021_lexical', {}).get('exp_021_e2e_sec')}s lexical vs {timings['e2e_sec']}s here). "
        f"{QA_MODEL_NAME}, {NLI_MODEL_NAME}, and {BGE_MODEL_NAME} are loaded; FLAN-T5/CTranslate2 are not."
    )
    run.finish(
        title="Stage latency and memory with the encoder checkpoints resident",
        goal="Re-measure EXP-021 stage latency and memory with the encoder checkpoints resident. ONNX Runtime int8 is an allowed encoder runtime for a later measurement, not attempted here.",
        method=(
            "Identical 40 passages and bench() harness as EXP-021 (warm up once, then time repeated calls). "
            "ask_analyze/chunk stay rule code (unaffected by the encoder swap). search is RealIndex's bge "
            "dense channel; qa/nli are real_qa/real_nli; e2e runs engine.run_task with EXP-027's monkeypatch "
            "adapters in place. Peak RSS is the process high-water mark including every model load."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=(
            "Loading three transformers/sentence-transformers checkpoints is measurably slower and heavier "
            "than the lexical substitutes EXP-021 timed -- that is the expected, honest cost of the real "
            "encoders on CPU, not a surprise, and quantized ONNX Runtime int8 (named by the todo as the "
            "allowed path to close that gap) is a follow-up, not run in this pass."
        ),
        scale_down="Forty short passages, same as EXP-021. CTranslate2/FLAN-T5 are not timed (FORBIDDEN.md). ONNX Runtime int8 quantization is not applied in this pass.",
        referenced_files=FILES,
        follow_ups=[
            "Quantize these three checkpoints with ONNX Runtime int8 and rerun this same bench() harness for the latency/memory figure the todo actually asks for.",
        ],
        models_used=f"{QA_MODEL_NAME}, {NLI_MODEL_NAME}, {BGE_MODEL_NAME}, plain transformers/sentence-transformers (no quantization). Local checkpoints, not API calls. Not generative.",
    )


if __name__ == "__main__":
    main()
