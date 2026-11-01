"""External data connectors: optional context feeders that retrieve
passages from a store outside the project's own in-process corpus
(lab.common.index.Index / lab.common.real_bge_index.RealBgeIndex /
lab.common.graph_index's entity graph), so a question can be fed by
something other than passages supplied directly in the same call.

Deliberately scoped per project direction ("leave mcp for now"): no
MCP, no tool-calling -- a connector's one job is producing
lab.common.ingest's own passage shape ({"id", "text"}, score attached)
so its hits can be merged straight into whatever passages a caller
already has before calling lab.common.brain.reason. Nothing downstream
of that point (grounding, citation, the reasoning core) changes to
accommodate a connector; a connector is a retrieval source, not a new
reasoning path.

Two connectors, both deterministic/non-generative:

  - QdrantConnector: a real external vector store (qdrant-client), run
    in LOCAL / embedded on-disk mode only (QdrantClient(path=...)) --
    no server, no network address, no credentials. Embeddings are
    lab.common.real_encoders.bge_embed, the same dense model the rest
    of this project already uses, so a Qdrant-backed search and an
    in-process RealBgeIndex search return comparable scores.

  - GraphConnector: this project's own entity graph
    (lab.common.graph_index.build_entity_graph / expand_from_entity),
    not Microsoft's generative graphrag package -- building a graph
    with an LLM would violate FORBIDDEN.md's no-generative-models rule
    for anything outside the one bounded rewriter exception. This is
    the "graphrag" this project's own planning referred to: a
    citation-safe graph expansion, not an LLM-constructed knowledge
    graph.

qdrant_client is only ever imported lazily, inside QdrantConnector's
own methods -- same convention lab.common.real_encoders already uses
for sentence_transformers/transformers -- so importing this module
never requires qdrant-client to be installed, and the shared
environment (which deliberately does not have it; see this project's
pip-install-risk notes) never loads it just because this module
exists. qdrant-client itself is only ever installed in this project's
isolated .venv.
"""

from __future__ import annotations

from pathlib import Path

from lab.common.graph_index import build_entity_graph, expand_from_entity, load_entity_graph, save_entity_graph
from lab.common.real_encoders import bge_embed

DEFAULT_CONNECTOR_DIR = Path("data/connectors")


class QdrantConnector:
    """Local/embedded on-disk Qdrant collection: `QdrantClient(path=...)`,
    never a server address or network call. `collection` names a
    subdirectory under `base_dir`; each connector instance owns exactly
    one Qdrant collection of that same name, persisted across calls --
    `upsert` once, `search` many times later, in a later process, without
    re-embedding anything.
    """

    def __init__(self, collection: str, base_dir: str | Path = DEFAULT_CONNECTOR_DIR):
        self.collection = collection
        self.dir = Path(base_dir) / "qdrant" / collection
        self.dir.mkdir(parents=True, exist_ok=True)
        self._client = None

    def _get_client(self):
        if self._client is None:
            from qdrant_client import QdrantClient

            self._client = QdrantClient(path=str(self.dir))
        return self._client

    def _ensure_collection(self, dim: int) -> None:
        from qdrant_client.models import Distance, VectorParams

        client = self._get_client()
        if not client.collection_exists(self.collection):
            client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )

    def upsert(self, passages: list[dict]) -> int:
        """Embeds every passage with bge_embed and upserts it into this
        connector's on-disk Qdrant collection, creating the collection on
        first use. Point ids are a running counter starting from the
        collection's current point count, so repeated upserts on the same
        collection add rather than overwrite. Returns the number of
        points written.
        """
        from qdrant_client.models import PointStruct

        if not passages:
            return 0
        texts = [p.get("text", "") or "" for p in passages]
        vectors = bge_embed(texts)
        self._ensure_collection(vectors.shape[1])
        client = self._get_client()
        start_id = client.count(collection_name=self.collection).count
        points = [
            PointStruct(id=start_id + i, vector=vectors[i].tolist(), payload={"id": p.get("id"), "text": p.get("text", "")})
            for i, p in enumerate(passages)
        ]
        client.upsert(collection_name=self.collection, points=points)
        return len(points)

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """Returns rows shaped like lab.common.index.Index.search's own
        rows (`{"passage": {"id", "text"}, "score": float}`) so a caller
        can merge Qdrant hits with in-process Index/RealBgeIndex hits
        without a special case. Returns `[]` for a collection that was
        never upserted into, rather than raising.
        """
        client = self._get_client()
        if not client.collection_exists(self.collection):
            return []
        qv = bge_embed([query])[0]
        hits = client.query_points(collection_name=self.collection, query=qv.tolist(), limit=top_k).points
        return [
            {"passage": {"id": hit.payload.get("id"), "text": hit.payload.get("text", "")}, "score": float(hit.score)}
            for hit in hits
        ]


class GraphConnector:
    """This project's own entity-link graph (lab.common.graph_index), as
    an external-context connector: `upsert` builds the graph from a
    passage set and persists it to disk; `search` expands from a named
    entity against the persisted graph in a later call, with no need to
    re-run entity detection over the original passages again.
    """

    def __init__(self, collection: str, base_dir: str | Path = DEFAULT_CONNECTOR_DIR):
        self.collection = collection
        self.path = Path(base_dir) / "graph" / f"{collection}.pkl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def upsert(self, passages: list[dict], use_real_ner: bool = False) -> dict:
        """Builds lab.common.graph_index.build_entity_graph over `passages`
        and persists it via save_entity_graph (nodes/edges, plus the
        passages themselves so `search` can return full passage dicts
        later without the caller re-supplying them). Returns the built
        graph dict as-is.
        """
        graph = build_entity_graph(passages, use_real_ner=use_real_ner)
        save_entity_graph(graph, passages, self.path)
        return graph

    def search(self, entity_text: str, max_hops: int = 1) -> dict:
        """Expands from `entity_text`'s node in the persisted graph.
        Returns lab.common.graph_index.expand_from_entity's own shape
        (`{"passages": [...], "path": [...]}`, or an `abstain_reason`
        when the entity or the graph itself isn't found) -- never a
        hard failure for a connector that was never upserted into.
        """
        if not self.path.exists():
            return {"passages": [], "path": [], "abstain_reason": f"no graph persisted for collection {self.collection!r}"}
        state = load_entity_graph(self.path)
        passages_by_id = {p.get("id"): p for p in state["passages"]}
        return expand_from_entity(entity_text, state["graph"], passages_by_id, max_hops=max_hops)
