"""Shared test fixtures and scenario-driver helpers.

Deterministic audit (2026-11-12) found these defined byte-for-byte (or
behaviorally) identically in two or more lab/tests/exp_*/run.py files --
almost always an original exploration and its later "real_*"/rerun sibling,
copy-pasted rather than imported. Consolidated here once each; every
caller imports from here instead of keeping its own local copy. A few
functions needed a small, explicit parameter added (which index class,
which answerer, which needle/chapter fixture) to stay a single shared
definition without changing any existing caller's behavior.

lab/tests/ never gets imported BY lab/common/ (AGENT.md's Java-style
src/main-vs-test rule) -- this module only imports FROM lab.common.
"""

from __future__ import annotations

import random

from lab.common.chunking import chunk_document
from lab.common.index import Index
from lab.common.nested_index import build_nested_index
from lab.common.textutil import normalize, numbers

# ---------------------------------------------------------------------------
# exp_011_decision_heads / exp_036_real_decision_heads: identical scenario
# generator, calibration-bin helper, and the slot/value table they share.
# ---------------------------------------------------------------------------

DECISION_HEAD_SLOTS = [
    ("notice period", ["30 days", "45 days", "60 days"]),
    ("security deposit", ["INR 50000", "INR 75000", "INR 10000"]),
    ("rent", ["INR 25000", "INR 40000", "INR 15000"]),
    ("cure period", ["10 days", "5 days", "20 days"]),
    ("bond interest", ["7 percent", "12 percent", "3 percent"]),
    ("dose", ["40 mg", "10 mg", "80 mg"]),
]


def decision_head_scenario(rng: random.Random, kind: str) -> dict:
    slot, values = rng.choice(DECISION_HEAD_SLOTS)
    truth, other = rng.sample(values, 2)
    if kind == "supported":
        passage = f"The {slot} is {truth}."
        claim_span = truth
        label = "supported"
    elif kind == "contradicted":
        passage = f"The {slot} is {truth}."
        claim_span = other
        label = "contradicted"
    else:
        passage = "The garden has roses and a stone bench."
        claim_span = truth
        label = "inconclusive"
    return {"slot": slot, "passage": passage, "claim_span": claim_span, "label": label, "question": f"What is the {slot}?"}


def decision_head_reliability(probs, labels, positive: str, bins: int = 5) -> list[dict]:
    indexed = list(enumerate(probs))
    width = 1 / bins
    rows = []
    for b in range(bins):
        lo, hi = b * width, (b + 1) * width
        chosen = [(i, p) for i, p in indexed if (p >= lo and p < hi) or (b == bins - 1 and p == 1)]
        if not chosen:
            rows.append({"bin": [round(lo, 2), round(hi, 2)], "n": 0, "mean_p": None, "empirical": None})
            continue
        mean_p = sum(p for _, p in chosen) / len(chosen)
        empirical = sum(1 for i, _ in chosen if labels[i] == positive) / len(chosen)
        rows.append({"bin": [round(lo, 2), round(hi, 2)], "n": len(chosen), "mean_p": round(mean_p, 4), "empirical": round(empirical, 4)})
    return rows


# ---------------------------------------------------------------------------
# exp_018_longform / exp_042_real_repetition: identical finding-fixture
# generator.
# ---------------------------------------------------------------------------


def findings(n: int, duplicate: bool = False) -> list[dict]:
    rows = []
    for i in range(n):
        rows.append(
            {
                "finding_id": f"F{i:05d}",
                "statement": f"The value of item {i} is {i * 3}.",
                "citation": f"C{i:05d}",
                "evidence_id": f"C{i:05d}",
                "sort_key": i,
            }
        )
    if duplicate and n > 8:
        for offset in range(4):
            rows[4 + offset]["statement"] = rows[offset]["statement"]
    if n > 8:
        rows[8]["statement"] = "R. Sharma holds item 8, and the value of item 8 is 24."
    return rows


# ---------------------------------------------------------------------------
# exp_009_entity_resolve / exp_034_real_entity_resolve: identical chunking
# and lookup helpers.
# ---------------------------------------------------------------------------


def find_mention(mentions: list[dict], text: str) -> dict | None:
    for mention in mentions:
        if normalize(mention["text"]) == normalize(text):
            return mention
    return None


def doc_chunks(doc: dict) -> list[dict]:
    chunks = chunk_document(doc["text"], doc["id"], min_words=3, max_words=80)
    if chunks:
        return chunks
    return [{"chunk_id": f"{doc['id']}-p1-c1", "id": f"{doc['id']}-p1-c1", "text": doc["text"]}]


# ---------------------------------------------------------------------------
# exp_029_real_retrieval / exp_032_real_multihop: identical chunks loader
# (exp_025's cached real-document chunks).
# ---------------------------------------------------------------------------


def load_real_document_chunks(root) -> list[dict]:
    import json

    path = root / "data" / "exp_025_real_documents" / "chunks.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing. Run lab/tests/exp_025_real_documents/run.py first.")
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# exp_033_real_entities / exp_080_real_ner_rerun: identical gold-matching
# helpers for the rule-tagger-vs-real-NER comparison.
# ---------------------------------------------------------------------------


def rule_tagger_spans(sentence: str) -> set[str]:
    from lab.common.entities import agreement, detect_primary, detect_secondary

    mentions = agreement(detect_primary(sentence), detect_secondary(sentence))
    return {normalize(m["text"]) for m in mentions if m["label"] in ("person", "organization")}


def contains_match(pred: set[str], gold_text: str) -> bool:
    g = normalize(gold_text)
    return any(g == p or g in p or p in g for p in pred)


# ---------------------------------------------------------------------------
# exp_015_paged_memory / exp_040_real_paged_retrieval: identical synthetic
# haystack, and a needle_recall parameterized over which index class scores
# it (lexical Index vs real-embedding RealBgeIndex).
# ---------------------------------------------------------------------------


def haystack(pages: int, needle_at: int, needle_text: str) -> list[dict]:
    rows = []
    for i in range(pages):
        if i == needle_at:
            text = f"Page {i}. {needle_text} Filler words about gardens and schedules follow this sentence."
        else:
            text = (
                f"Page {i}. The committee discussed item {i} and filed a routine note about chairs, "
                "rosters, and the weekly market. No code is printed on this page."
            )
        rows.append({"id": f"PG{i:04d}", "text": text, "page": i})
    return rows


def needle_recall(pages: int, needle_text: str, index_cls) -> dict:
    from lab.tests.support import recall_at_k

    rows = haystack(pages, pages // 2, needle_text)
    index = index_cls(rows)
    hits = index.search("violet quorum code", top_k=5)
    ids = [hit["passage"]["id"] for hit in hits]
    gold = {f"PG{pages // 2:04d}"}
    return {"pages": pages, "recall_at_5": recall_at_k(ids, gold, 5), "top": ids[:3]}


# ---------------------------------------------------------------------------
# exp_010_gap_resolution / exp_035_real_gap_resolution: identical
# multi-round gap-resolution driver, parameterized over which QA answerer
# and which entailment judge score each round (lexical answer_question/
# judge vs real_answer_question/real_nli).
# ---------------------------------------------------------------------------


def resolve_gap(item: dict, answer_fn, support_fn, label_of_fn, max_rounds: int = 3) -> dict:
    passages = [{"id": f"P{i}", "text": text} for i, text in enumerate(item["passages"])]
    index = Index(passages)
    alternatives = []
    qa = None
    for rnd in range(max_rounds):
        query = item["queries"][min(rnd, len(item["queries"]) - 1)]
        hits = index.rerank(query, index.search(query, top_k=6), keep=6)
        ctx = [hit["passage"] for hit in hits]
        qa = answer_fn(item["question"], ctx, tau=0.34)
        spans = []
        for passage in ctx:
            one = answer_fn(item["question"], [passage], tau=0.34)
            if one["span"]:
                spans.append(one["span"])
        unique = {normalize(span) for span in spans}
        if len(unique) > 1:
            alternatives.extend(sorted(unique))
            continue
        if item["gap"] == "vague_criterion" and not (qa["span"] and numbers(qa["span"])):
            if qa["span"]:
                alternatives.append(qa["span"])
            continue
        if qa["span"] and qa.get("score", 0) >= 0.34:
            support = support_fn(ctx[0]["text"] if ctx else "", f"The answer is {qa['span']}.")
            if label_of_fn(support) != "contradict":
                return {"status": "resolved", "span": qa["span"], "round": rnd, "evidence_id": qa["passage_id"]}
        if qa["span"]:
            alternatives.append(qa["span"])
    if item["gap"] == "vague_criterion":
        return {"status": "ambiguous", "span": None, "alternatives": alternatives}
    if alternatives and item["gap"] == "conflicting_values":
        return {"status": "ambiguous", "span": None, "alternatives": alternatives}
    return {"status": "ambiguous" if alternatives else "unresolved", "span": None, "alternatives": alternatives}


# ---------------------------------------------------------------------------
# exp_065_nested_navigation / exp_067_semantic_navigation: identical
# chapter/section/leaf fixture tree builder (065's fully-parameterized
# signature; 067 passed its needle_chapter/needle_section_idx as its own
# module constants instead, now passed explicitly here too).
# ---------------------------------------------------------------------------


def build_items(
    chapters: list[str],
    chapter_filler: dict[str, str],
    needle_text: str,
    sections_per_chapter: int,
    leaves_per_section: int,
    needle_chapter: str,
    needle_section: int,
) -> list[dict]:
    items = []
    uid = 0
    for chapter in chapters:
        for section_idx in range(sections_per_chapter):
            for leaf_idx in range(leaves_per_section):
                is_needle = chapter == needle_chapter and section_idx == needle_section and leaf_idx == leaves_per_section // 2
                text = needle_text if is_needle else f"{chapter_filler[chapter]} Item {leaf_idx} filed under section {section_idx}."
                items.append({"id": f"P{uid:05d}", "text": text, "chapter": chapter, "section": f"{chapter}-{section_idx}", "is_needle": is_needle})
                uid += 1
    return items


# ---------------------------------------------------------------------------
# exp_068_abstention_fixes / exp_071_dual_signal_calibration: identical
# fixture-dict-to-nested-tree builder.
# ---------------------------------------------------------------------------


def build_fixture_tree(fixture: dict, sections_per_chapter: int = 3, leaves_per_section: int = 8):
    items = []
    uid = 0
    for chapter, filler in fixture["chapters"].items():
        for section_idx in range(sections_per_chapter):
            for leaf_idx in range(leaves_per_section):
                is_needle = chapter == fixture["needle_chapter"] and section_idx == fixture["needle_section_idx"] and leaf_idx == leaves_per_section // 2
                text = fixture["needle"] if is_needle else f"{filler} Item {leaf_idx} filed under section {section_idx}."
                items.append({"id": f"P{uid:05d}", "text": text, "chapter": chapter, "section": f"{chapter}-{section_idx}", "is_needle": is_needle})
                uid += 1
    return build_nested_index(items, ["chapter", "section"])


# ---------------------------------------------------------------------------
# exp_083_symbolic_inference / exp_085_multi_exception_scoping: identical
# (subject, verb_lemma, object) signature-set helper.
# ---------------------------------------------------------------------------


def signature_set(facts: list[dict]) -> set[tuple]:
    return {(f["subject"], f["verb_lemma"], f.get("object")) for f in facts if f.get("subject")}
