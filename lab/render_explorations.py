"""Build EXPLORATIONS.md from closed results plus todo entries. Numbers are copied from results.json."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TODOS = [
    {
        "id": "EXP-022",
        "title": "On-disk hybrid index",
        "status": "todo",
        "goal": "Repeat the hybrid retrieval measurement with an on-disk index once the corpus no longer fits the process index.",
        "method": "Not run.",
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
        "referenced_files": [],
        "results_prose": "Not run.",
        "conclusion": "Todo. Do not download a pretrained NER or generative model.",
        "scale_down": "",
    },
    {
        "id": "EXP-025",
        "title": "Attach a document collection",
        "status": "todo",
        "goal": "Ingest a public, non-confidential document set with the same chunker and index. Keep the engine domain-agnostic.",
        "method": "Not run.",
        "referenced_files": [],
        "results_prose": "Not run.",
        "conclusion": "Todo. Phase 3 in the architecture waits on a real collection and a human reviewer. This POC does not attach one.",
        "scale_down": "",
    },
    {
        "id": "EXP-026",
        "title": "Qualification rules",
        "status": "todo",
        "goal": "Add code rules for except, unless, and provided that if the lexical judge keeps missing them.",
        "method": "Not run.",
        "referenced_files": [],
        "results_prose": "Not run.",
        "conclusion": "Todo. This stays a deterministic checker.",
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
        "Generative language models were not used in any exploration.",
        "",
    ]
    for row in results:
        lines.extend(_section(row))
    lines.append("## Follow-up todos")
    lines.append("")
    for row in TODOS:
        lines.extend(_section(row))
    (ROOT / "EXPLORATIONS.md").write_text("\n".join(lines) + "\n")
    print(f"wrote EXPLORATIONS.md with {len(results)} closed and {len(TODOS)} todo")


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
    return [
        f"## {row['id']} {row['title']}",
        "",
        f"- Status: `{row['status']}`",
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


if __name__ == "__main__":
    main()
