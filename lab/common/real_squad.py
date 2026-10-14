"""Fetch the real SQuAD2 dev set (EXP-047).

ARCHITECTURE.md's Experiment B (section 10) names "SQuAD2 dev subset plus 40
custom items" as the data for extractive QA and answerability. EXP-005 only
ran the 40 custom items; the real SQuAD2 dev set was never fetched.

This is a real-data exploration, not a real-model one: it still runs the
existing lexical span extractors from lab/common/qa.py (no checkpoint, no
network model). The subset is public, non-confidential Wikipedia-paragraph
text (CC BY-SA 4.0), consistent with FORBIDDEN.md's "no private or real
personal data" rule.

The official file is hosted on raw.githubusercontent.com (the SQuAD-explorer
repository), which is reachable in this sandbox, unlike huggingface.co.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / ".cache" / "squad_dev_v2.json"
SQUAD_URL = "https://raw.githubusercontent.com/rajpurkar/SQuAD-explorer/master/dataset/dev-v2.0.json"
SUBSET_PATH = ROOT / "data" / "exp_047_real_squad_qa" / "squad_subset.json"

N_ITEMS = 300


def _ensure_cached() -> dict:
    if not CACHE_PATH.exists():
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(SQUAD_URL, headers={"User-Agent": "research-poc/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        CACHE_PATH.write_bytes(data)
    return json.loads(CACHE_PATH.read_text())


def build_subset(n_items: int = N_ITEMS) -> list[dict]:
    """Deterministically select the first n_items real questions, in file order,
    across articles and paragraphs. Each item gets a second, real distractor
    passage drawn from the next article in the dataset (not the correct one)."""
    squad = _ensure_cached()
    articles = squad["data"]

    flat = []
    for art_idx, art in enumerate(articles):
        for para in art["paragraphs"]:
            for qa in para["qas"]:
                flat.append(
                    {
                        "art_idx": art_idx,
                        "title": art["title"],
                        "context": para["context"],
                        "question": qa["question"],
                        "qid": qa["id"],
                        "is_impossible": bool(qa.get("is_impossible")),
                        "answers": sorted({a["text"] for a in qa.get("answers", [])}),
                    }
                )
    flat = flat[:n_items]

    # A real distractor paragraph per item: the first paragraph of a different
    # article, chosen deterministically (next article index, wrapping around).
    article_first_paragraph = [art["paragraphs"][0]["context"] for art in articles]

    items = []
    for row in flat:
        distractor_idx = (row["art_idx"] + 1) % len(articles)
        items.append(
            {
                "id": row["qid"],
                "title": row["title"],
                "question": row["question"],
                "answerable": not row["is_impossible"],
                "gold": row["answers"][0] if row["answers"] else None,
                "gold_alternatives": row["answers"],
                "passages": {"A": row["context"], "B": article_first_paragraph[distractor_idx]},
            }
        )
    return items


def save_subset(items: list[dict]) -> str:
    SUBSET_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUBSET_PATH.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n")
    return str(SUBSET_PATH.relative_to(ROOT))


def load_subset() -> list[dict]:
    if not SUBSET_PATH.exists():
        raise FileNotFoundError(f"{SUBSET_PATH} is missing. Run lab/exp_047_real_squad_qa/run.py first.")
    return json.loads(SUBSET_PATH.read_text())
