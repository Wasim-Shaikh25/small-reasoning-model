"""The data half of a job, declared as YAML -- the "attach a connector the
way you'd declare a RabbitMQ connection" shape the project owner asked for.
A job names one connector type and its own params; this module turns that
into the `ctx = {"passages": [...], "records": [...]}` shape every
`lab.common.concept_tools` primitive runs against. Adding a new case or
data source is a new YAML file, never a code change, for the three types
that need no new wiring (`inline`, `file`, `records`); `qdrant` and `graph`
reuse `lab.common.connectors`' already-built, already-tested classes.

Connector YAML shape:

    type: file
    paths: ["case_123/*.txt"]

    type: records
    records:
      - {name: "Ravi Sharma", role: respondent, address: "14 MG Road, Pune"}

    type: qdrant
    collection: "case_123"
    query: "refund policy"
"""

from __future__ import annotations

import glob
from pathlib import Path

import yaml

from lab.common.ingest import chunk_document


def load_connector_config(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def fetch_context(config: dict) -> dict:
    """Returns `{"passages": [...], "records": [...]}`. Never raises for an
    empty source (an empty list either side is a legitimate, honestly-
    reported "no data," not an error) -- raises only for an unrecognized
    `type`, which is a configuration mistake worth stopping on.
    """
    kind = config.get("type")

    if kind == "inline":
        return {"passages": config.get("passages", []), "records": config.get("records", [])}

    if kind == "records":
        return {"passages": [], "records": config.get("records", [])}

    if kind == "file":
        passages = []
        for pattern in config.get("paths", []):
            for fp in sorted(glob.glob(pattern)):
                text = Path(fp).read_text(encoding="utf-8", errors="replace")
                for chunk in chunk_document(text):
                    passages.append({"id": f"{Path(fp).stem}-{chunk['id']}", "text": chunk["text"]})
        return {"passages": passages, "records": config.get("records", [])}

    if kind == "qdrant":
        from lab.common.connectors import QdrantConnector

        conn = QdrantConnector(collection=config["collection"])
        hits = conn.search(config.get("query", ""), top_k=config.get("top_k", 50))
        return {"passages": [h["passage"] for h in hits], "records": config.get("records", [])}

    if kind == "graph":
        from lab.common.connectors import GraphConnector

        conn = GraphConnector(collection=config["collection"])
        passages: list[dict] = []
        seen: set = set()
        for entity_text in config.get("entities", []):
            expansion = conn.search(entity_text, max_hops=config.get("max_hops", 1))
            for p in expansion.get("passages", []):
                if p.get("id") not in seen:
                    seen.add(p.get("id"))
                    passages.append(p)
        return {"passages": passages, "records": config.get("records", [])}

    raise ValueError(f"Unknown connector type {kind!r}. Known: inline, records, file, qdrant, graph")
