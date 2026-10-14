"""Fetch a real, public, non-confidential multi-document collection (EXP-025).

Source: the Reuters-21578 corpus as packaged by the NLTK project (nltk_data,
corpora/reuters), a long-standing public research corpus of real Reuters news
wire stories from 1987, usable for research.

Network note: NLTK's own downloader refuses to run behind this sandbox's HTTPS
proxy (its SSRF guard cannot pin the destination IP once a proxy is in the
path). That guard is about NLTK's downloader implementation, not about the
destination being unreachable: nltk_data is a plain GitHub Pages repository, so
this module fetches the package zip itself over HTTPS from
raw.githubusercontent.com (reachable in this sandbox) and extracts it into a
local cache, then points nltk.data.path at that cache so nltk.corpus.reuters
reads it like any other local corpus. No generative model is involved in
fetching or reading this data.

The selected subset (documents.json) is written to data/exp_025_real_documents/
so later explorations load it without a network call and so the exact real
text used is auditable in the repository.
"""

from __future__ import annotations

import io
import json
import re
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / ".cache" / "nltk_data"
REUTERS_URL = "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/reuters.zip"
DOCS_PATH = ROOT / "data" / "exp_025_real_documents" / "documents.json"

CATEGORY = "coffee"
N_DOCS = 25


def _ensure_reuters_cached() -> None:
    marker = CACHE_DIR / "corpora" / "reuters" / "cats.txt"
    if marker.exists():
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(REUTERS_URL, headers={"User-Agent": "research-poc/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(CACHE_DIR / "corpora")


def clean_wire_text(text: str) -> str:
    """Join hard-wrapped wire-service lines into real paragraphs, char-for-char content preserved."""
    paragraphs = re.split(r"\n\s*\n", (text or "").strip())
    cleaned = []
    for para in paragraphs:
        joined = " ".join(line.strip() for line in para.splitlines())
        joined = re.sub(r"\s+", " ", joined).strip()
        if joined:
            cleaned.append(joined)
    return "\n\n".join(cleaned)


def fetch_documents(category: str = CATEGORY, n_docs: int = N_DOCS) -> list[dict]:
    """Download (if needed) and return n_docs real, cleaned Reuters articles, deterministically selected."""
    _ensure_reuters_cached()
    import nltk

    nltk_path = str(CACHE_DIR)
    if nltk_path not in nltk.data.path:
        nltk.data.path.insert(0, nltk_path)
    from nltk.corpus import reuters

    file_ids = sorted(fid for fid in reuters.fileids(category) if fid.startswith("training/"))
    chosen = file_ids[:n_docs]
    documents = []
    for fid in chosen:
        raw = reuters.raw(fid)
        text = clean_wire_text(raw)
        if not text:
            continue
        title = text.splitlines()[0][:120]
        documents.append(
            {
                "doc_id": fid.replace("/", "-"),
                "source": "nltk reuters-21578 (real 1987 Reuters news wire stories)",
                "source_fileid": fid,
                "category": category,
                "title": title,
                "text": text,
            }
        )
    return documents


def save_documents(documents: list[dict]) -> str:
    DOCS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOCS_PATH.write_text(json.dumps(documents, indent=2, ensure_ascii=False) + "\n")
    return str(DOCS_PATH.relative_to(ROOT))


def load_documents() -> list[dict]:
    if not DOCS_PATH.exists():
        raise FileNotFoundError(
            f"{DOCS_PATH} is missing. Run lab/exp_025_real_documents/run.py first to fetch the real document collection."
        )
    return json.loads(DOCS_PATH.read_text())
