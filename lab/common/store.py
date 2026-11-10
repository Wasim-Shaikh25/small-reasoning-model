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

Follow-up (2026-11-10): HANDOFF.md's redesign proposal named the two
things `build`-only left missing -- "an incremental/streaming upsert
path (today `Store.build` is one-shot batch-fit only), and always-
hybrid search (never dense-only)". Both fixed below, honestly scoped:

- `Store.upsert` appends new passages without the caller re-supplying
  every earlier one, but the per-leg cost is NOT uniform, and this is
  reported rather than glossed over. `RealBgeIndex`'s dense leg is
  genuinely incremental -- `bge_embed` only ever runs on the NEW
  passages, since one passage's embedding never depends on the rest of
  the corpus; this is the leg real streaming upsert is actually FOR,
  since it is also the only expensive (model-inference) one. The
  lexical `Index`'s TF-IDF vectorizer has no such property --
  scikit-learn's `TfidfVectorizer` has no online-vocabulary update, and
  BM25's own idf is a global corpus statistic -- so that leg, and the
  entity graph (whose own docstring already calls rebuilding "the cheap
  part"), are refit over the full passage set including the new ones.
  Still strictly cheaper than the caller re-chunking and re-ingesting
  raw text from scratch, which is the actual gap this closes.
- `Store.search` now fuses BOTH legs by Reciprocal Rank Fusion (RRF) --
  the two legs' own hybrid scores are not on a shared scale (one blends
  TF-IDF-cosine with BM25, the other blends bge-cosine with BM25), so
  fusing by each leg's own RANK, not its raw score, is the standard way
  to combine rankings that were never calibrated against each other --
  whenever both legs exist, instead of `prefer_bge` picking exactly one
  and discarding the other. This is the structural fix for EXP-029's own
  finding (real embeddings lost to plain TF-IDF on a harder retrieval
  test): a bad dense ranking can no longer silently outvote a good
  lexical one, because the lexical leg's own ranking is never discarded.
  `prefer_bge` is kept, now only consulted when only one leg was built.
"""

from __future__ import annotations

from pathlib import Path

from lab.common.graph_index import build_entity_graph, load_entity_graph, save_entity_graph
from lab.common.index import Index, tokenize
from lab.common.ingest import chunk_document

DEFAULT_STORE_DIR = Path("data/stores")


def _rrf_fuse(rankings: list[list[dict]], top_k: int, rrf_k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion: each ranking contributes `1 / (rrf_k + rank)`
    (rank 0-based) to every passage it lists; a passage absent from a
    ranking contributes nothing from it, never a penalty -- so a passage
    only one leg found at all still surfaces, just without the other
    leg's boost. `rrf_k=60` is the constant the original RRF paper
    (Cormack et al., 2009) and most IR libraries since default to, not
    tuned here; this project has no labeled retrieval set to calibrate it
    against yet.
    """
    fused_scores: dict[str, float] = {}
    rows_by_id: dict[str, dict] = {}
    for ranking in rankings:
        for rank, row in enumerate(ranking):
            pid = row["passage"].get("id")
            if pid is None:
                continue
            fused_scores[pid] = fused_scores.get(pid, 0.0) + 1.0 / (rrf_k + rank + 1)
            rows_by_id.setdefault(pid, row)
    fused = [{**rows_by_id[pid], "score": score} for pid, score in fused_scores.items()]
    fused.sort(key=lambda row: row["score"], reverse=True)
    return fused[:top_k]


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
        self._use_real_ner = False

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
        self._use_real_ner = use_real_ner
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

    def upsert(self, new_passages: list[dict], use_real_ner: bool | None = None) -> "Store":
        """Appends `new_passages` to whatever this collection already has
        persisted, without the caller re-supplying every earlier passage.
        Loads from disk first if this `Store` instance hasn't already
        built/loaded itself this process. See the module docstring for
        exactly which leg is genuinely incremental (RealBgeIndex's dense
        embeddings) versus refit-but-still-cheaper-than-starting-over
        (the lexical Index, the entity graph).

        `use_real_ner` defaults to whatever `build` was last called with
        for this collection (so a caller upserting into an existing
        use_real_ner=True graph doesn't have to remember to repeat it);
        pass it explicitly to override.
        """
        if self.index is None:
            self.load()
        if use_real_ner is not None:
            self._use_real_ner = use_real_ner
        new_passages = list(new_passages)

        all_passages = self.index.passages + new_passages
        self.index = Index(all_passages)
        self.index.save(self.index_path)

        if self.bge_index is not None or self.bge_path.exists():
            from lab.common.real_bge_index import RealBgeIndex
            import numpy as np

            from lab.common.index import BM25
            from lab.common.real_encoders import bge_embed

            if self.bge_index is None:
                self.bge_index = RealBgeIndex.load(self.bge_path)
            new_texts = [p.get("text", "") or "" for p in new_passages]
            new_vectors = bge_embed(new_texts) if new_texts else np.zeros((0, 384), dtype="float32")
            self.bge_index.passages = self.bge_index.passages + new_passages
            self.bge_index._tokens = self.bge_index._tokens + [tokenize(t) for t in new_texts]
            self.bge_index.unit_vectors = (
                np.vstack([self.bge_index.unit_vectors, new_vectors]) if len(self.bge_index.unit_vectors) else new_vectors
            )
            self.bge_index.bm25 = BM25(self.bge_index._tokens)
            self.bge_index.save(self.bge_path)

        if self.graph is not None or self.graph_path.exists():
            if self.graph is None:
                state = load_entity_graph(self.graph_path)
                self.graph, self.graph_passages = state["graph"], state["passages"]
            self.graph_passages = (self.graph_passages or []) + new_passages
            self.graph = build_entity_graph(self.graph_passages, use_real_ner=self._use_real_ner)
            save_entity_graph(self.graph, self.graph_passages, self.graph_path)
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

    def search(self, query: str, top_k: int = 10, prefer_bge: bool = True, fuse: bool = True) -> list[dict]:
        """Both legs when both exist (`fuse=True`, the default): the
        lexical Index's own BM25+TF-IDF ranking and RealBgeIndex's own
        BM25+dense-bge ranking are each computed over the FULL passage
        set, then combined by Reciprocal Rank Fusion (`_rrf_fuse`) -- the
        fix for EXP-029's own finding that real bge embeddings can lose
        to plain TF-IDF on a harder retrieval test, so this collection's
        search should never silently discard the lexical leg's ranking
        just because a dense leg was also built.

        `prefer_bge` only matters when just one leg exists (or `fuse` is
        explicitly set False to force single-leg behavior): RealBgeIndex
        if it was built and `prefer_bge` is true, else the lexical
        Index -- the exact behavior this method always had, kept as a
        fallback/escape hatch, not removed.
        """
        if fuse and self.bge_index is not None and self.index is not None:
            n = len(self.index.passages)
            bge_ranking = self.bge_index.search(query, top_k=n)
            lexical_ranking = self.index.search(query, top_k=n)
            return _rrf_fuse([bge_ranking, lexical_ranking], top_k=top_k)
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


def ingest_and_upsert(
    collection: str,
    raw_text: str,
    base_dir: str | Path = DEFAULT_STORE_DIR,
    use_real_ner: bool | None = None,
    max_words_per_chunk: int = 120,
) -> Store:
    """`ingest_and_store`'s streaming counterpart: chunks `raw_text` and
    appends it to an already-persisted `collection` via `Store.upsert`,
    instead of requiring the caller to re-supply every earlier passage.
    Raises FileNotFoundError if `collection` was never built (same as
    `Store.load` -- use `ingest_and_store` for the first document).
    """
    passages = chunk_document(raw_text, max_words_per_chunk=max_words_per_chunk)
    return Store(collection, base_dir=base_dir).upsert(passages, use_real_ner=use_real_ner)
