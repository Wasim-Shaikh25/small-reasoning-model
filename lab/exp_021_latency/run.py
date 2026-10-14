"""EXP-021: stage latency and peak RSS on this machine."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.ask import analyze
from lab.common.chunking import chunk_document
from lab.common.engine import run_task
from lab.common.harness import Run, peak_rss_mb
from lab.common.index import Index
from lab.common.nli import judge
from lab.common.qa import answer_question

FILES = [
    "lab/exp_021_latency/run.py",
    "lab/common/ask.py",
    "lab/common/chunking.py",
    "lab/common/engine.py",
    "lab/common/index.py",
    "lab/common/nli.py",
    "lab/common/qa.py",
    "lab/common/harness.py",
    "lab/common/textutil.py",
    "lab/common/verify.py",
    "lab/common/budget.py",
    "lab/common/schemas.py",
    "data/exp_021_latency/results.json",
]


def bench(fn, repeats: int = 20) -> float:
    fn()
    t0 = time.perf_counter()
    for _ in range(repeats):
        fn()
    return round((time.perf_counter() - t0) / repeats, 6)


def main():
    run = Run("EXP-021", "exp_021_latency")
    passages = [{"id": f"P{i}", "text": f"The value of slot {i} is {i} days."} for i in range(40)]
    passages[3] = {"id": "P3", "text": "The notice period is 30 days."}
    doc = "PARTIES:\n" + "\n".join(p["text"] for p in passages)
    index = Index(passages)
    timings = {
        "ask_analyze_sec": bench(lambda: analyze("What is the notice period and who is the Lessee?")),
        "chunk_sec": bench(lambda: chunk_document(doc, "D1", max_words=30), repeats=10),
        "search_sec": bench(lambda: index.search("notice period", top_k=10)),
        "qa_sec": bench(lambda: answer_question("What is the notice period?", passages, tau=0.34)),
        "nli_sec": bench(lambda: judge("The notice period is 30 days.", "The notice period is 30 days.")),
        "e2e_sec": bench(lambda: run_task("What is the notice period?", passages), repeats=5),
    }
    metrics = {
        "mean_seconds": timings,
        "peak_rss_mb": peak_rss_mb(),
        "cpu_note": "Measured on this process. RSS is peak resident set for the whole run, not a per-model load.",
        "models_loaded": [],
    }
    prose = (
        "Mean stage times in seconds: "
        + ", ".join(f"{name} {value}" for name, value in timings.items())
        + f". Peak RSS {metrics['peak_rss_mb']} MB. No neural checkpoint was loaded."
    )
    run.finish(
        title="Stage latency and memory",
        goal="Record latency and peak RAM for ask analysis, chunking, retrieval, QA, NLI, and the controller on this machine.",
        method="Each stage is warmed up once and then timed over repeated calls. Peak RSS is the process high-water mark from getrusage.",
        metrics=metrics,
        results_prose=prose,
        conclusion="These times are for the lexical substitutes. They are not the latency of DeBERTa, GLiNER, or FLAN-T5, which are not loaded.",
        scale_down="Forty short passages. Quantized ONNX and CTranslate2 runtimes from the architecture are not used.",
        referenced_files=FILES,
    )


if __name__ == "__main__":
    main()
