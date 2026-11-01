"""Auto-create-on-ingest, load-on-reuse on-disk store.

Extends EXP-022's Index.save/load pattern (previously the BM25+TF-IDF
leg only) to every in-process retrieval primitive this project already
has: the dense bge leg (lab.common.real_bge_index.RealBgeIndex) and the
entity graph (lab.common.graph_index). One Store.build call with
passages fits and persists all of them under one collection directory;
a later Store.load call for that same collection reads straight from
disk -- no re-fitting the TF-IDF vectorizer, no re-embedding every
passage with bge, no re-running entity detection.

This is the entry point named by the project owner's own description:
"when we give it prompt data it should be able to create its own
vector or whatever db in disk" (as opposed to rebuilding every
in-process index from scratch on every call, which is what
lab.common.index/lab.common.real_bge_index/lab.common.graph_index did
on their own before this module). Still exactly this project's
standing rule: a persisted index is a cache of deterministic
in-process state, never a new judgment call and never a generative
step.

lab.common.connectors.QdrantConnector/GraphConnector already persist
themselves on their own schedule (a Qdrant collection writes to disk on
every upsert; GraphConnector calls save_entity_graph directly) -- this
module is for the two primitives (Index, RealBgeIndex) that didn't
already have a caller-facing "ingest once, reuse by collection name"
entry point.
"""

from __future__ import annotations

from pathlib import Path

from lab.common.graph_index import build_entity_graph, load_entity_graph, save_entity_graph
from lab.common.index import Index
from lab.common.ingest import chunk_document

DEFAULT_STORE_DIR = Path("data/stores")


class Store:
    """One persisted collection: a lexical Index (always), optionally a
    dense RealBgeIndex, optionally an entity graph. `collection` names a
    subdirectory under `base_dir` -- one store per collection, never
    shared.
    """

    def __init__(self, collection: str, base_dir: str | Path = DEFAULT_STORE_DIR):
        self.collection = collection
        self.dir = Path(base_dir) / collection
        self.index_path = self.dir / "index.pkl"
        self.bge_path = self.dir / "bge_index.pkl"
        self.graph_path = self.dir / "graph.pkl"
        self.index: Index | None = None
        self.bge_index = None
        self.graph: dict | None = None
        self.graph_passages: list[dict] | None = None

    def exists(self) -> bool:
        return self.index_path.exists()

    def build(self, passages: list[dict], use_bge: bool = False, use_graph: bool = False, use_real_ner: bool = False) -> "Store":
        """Fits every requested primitive over `passages` and persists
        each to this collection's directory. Always builds+saves the
        lexical Index; `use_bge`/`use_graph` opt into the heavier
        real-encoder dense leg / entity graph -- the same opt-in shape
        lab.common.brain.reason already uses for use_real_ner, so a
        caller who doesn't want the real-encoder cost pays nothing for
        it here either.
        """
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index = Index(passages)
        self.index.save(self.index_path)
        if use_bge:
            from lab.common.real_bge_index import RealBgeIndex

            self.bge_index = RealBgeIndex(passages)
            self.bge_index.save(self.bge_path)
        if use_graph:
            self.graph = build_entity_graph(passages, use_real_ner=use_real_ner)
            self.graph_passages = list(passages)
            save_entity_graph(self.graph, passages, self.graph_path)
        return self

    def load(self) -> "Store":
        """Loads whichever of the persisted pieces exist for this
        collection. Raises FileNotFoundError if the lexical Index itself
        (the one piece `build` always writes) was never persisted --
        callers should check `exists()` or use `get_or_build` instead of
        catching this.
        """
        if not self.index_path.exists():
            raise FileNotFoundError(f"no store persisted for collection {self.collection!r} under {self.dir}")
        self.index = Index.load(self.index_path)
        if self.bge_path.exists():
            from lab.common.real_bge_index import RealBgeIndex

            self.bge_index = RealBgeIndex.load(self.bge_path)
        if self.graph_path.exists():
            state = load_entity_graph(self.graph_path)
            self.graph = state["graph"]
            self.graph_passages = state["passages"]
        return self

    def search(self, query: str, top_k: int = 10, prefer_bge: bool = True) -> list[dict]:
        """RealBgeIndex's search when it was built/loaded for this
        collection and `prefer_bge` is true, else the lexical Index's own
        BM25+TF-IDF search -- both already return the identical row
        shape (`{"passage", "score", "dense", "sparse"}`), so a caller
        never needs to branch on which leg actually ran.
        """
        if prefer_bge and self.bge_index is not None:
            return self.bge_index.search(query, top_k=top_k)
        return self.index.search(query, top_k=top_k)

    def expand_entity(self, entity_text: str, max_hops: int = 1) -> dict:
        """lab.common.graph_index.expand_from_entity over this
        collection's persisted graph. Returns an `abstain_reason` rather
        than raising when `use_graph` was never requested for this
        collection.
        """
        from lab.common.graph_index import expand_from_entity

        if self.graph is None:
            return {"passages": [], "path": [], "abstain_reason": f"collection {self.collection!r} has no entity graph (build with use_graph=True)"}
        passages_by_id = {p.get("id"): p for p in (self.graph_passages or [])}
        return expand_from_entity(entity_text, self.graph, passages_by_id, max_hops=max_hops)


def get_or_build(
    collection: str,
    passages: list[dict] | None = None,
    base_dir: str | Path = DEFAULT_STORE_DIR,
    use_bge: bool = False,
    use_graph: bool = False,
    use_real_ner: bool = False,
) -> Store:
    """Pass `passages` the first time for a given `collection` -- the
    store is built fresh and persisted. Omit `passages` on every later
    call for that same `collection` -- the already-persisted store loads
    from disk instead of refitting. Raises FileNotFoundError if
    `passages` is omitted and nothing was ever persisted for this
    collection.
    """
    store = Store(collection, base_dir=base_dir)
    if passages is not None:
        return store.build(passages, use_bge=use_bge, use_graph=use_graph, use_real_ner=use_real_ner)
    return store.load()


def ingest_and_store(
    collection: str,
    raw_text: str,
    base_dir: str | Path = DEFAULT_STORE_DIR,
    use_bge: bool = False,
    use_graph: bool = False,
    use_real_ner: bool = False,
    max_words_per_chunk: int = 120,
) -> Store:
    """Raw document text straight to a persisted store in one call:
    lab.common.ingest.chunk_document's existing chunking feeds
    get_or_build directly, so a caller handing this module a prompt's
    worth of document text never has to call chunk_document separately.
    """
    passages = chunk_document(raw_text, max_words_per_chunk=max_words_per_chunk)
    return get_or_build(collection, passages=passages, base_dir=base_dir, use_bge=use_bge, use_graph=use_graph, use_real_ner=use_real_ner)
