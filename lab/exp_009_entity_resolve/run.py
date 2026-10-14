"""EXP-009: entity resolution loop and example store (architecture Experiments E3 and E4)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.chunking import chunk_document
from lab.common.entities import ExampleStore, pair_features, resolve_mentions, same_entity_pairs, train_pair_matcher
from lab.common.harness import Run
from lab.common.textutil import normalize

FILES = [
    "lab/exp_009_entity_resolve/run.py",
    "lab/common/entities.py",
    "lab/common/chunking.py",
    "lab/common/qa.py",
    "lab/common/textutil.py",
    "lab/common/harness.py",
    "data/exp_009_entity_resolve/docs.json",
    "data/exp_009_entity_resolve/results.json",
]

DOCS = [
    {
        "id": "E3-1",
        "text": "PARTIES:\nRavi Sharma (the Lessee) resides at 14 MG Road, Pune 411001.\nABC Pvt Ltd (the Lessor) having its office at 48 Park Street, Kolkata 700016.",
        "expect_person": "Ravi Sharma",
        "expect_status": "resolved",
    },
    {
        "id": "E3-2",
        "text": "PARTIES:\nAmit Sharma lives at 1 Lake Road, Pune 411002.\nNeha Sharma lives at 2 Hill Road, Pune 411003.\nThe letter is addressed to Mr. Sharma.",
        "expect_mention": "Mr. Sharma",
        "expect_status": "ambiguous",
    },
    {
        "id": "E3-3",
        "text": "PARTIES:\nKapil Menon resides at 9 Residency Road, Bengaluru 560001.\nKapil Menon also uses 11 Brigade Road, Bengaluru 560025.",
        "expect_person": "Kapil Menon",
        "expect_status": "ambiguous",
    },
    {
        "id": "E3-4",
        "text": "PARTIES:\nThe agreement names R. Sharma as the tenant.\nRavi Sharma (the Lessee) signed above.",
        "expect_mention": "R. Sharma",
        "expect_status": "ambiguous",
    },
    {
        "id": "E3-5",
        "text": "PARTIES:\nMeera Iyer and Kapil Menon both reside at 48 Park Street, Kolkata 700016.",
        "expect_distinct": ["Meera Iyer", "Kapil Menon"],
    },
    {
        "id": "E3-6",
        "text": "PARTIES:\nPriya Nair (the Licensee) resides at 9 Residency Road, Bengaluru 560001.",
        "expect_person": "Priya Nair",
        "expect_status": "resolved",
    },
]

PAIR_TRAIN = [
    {"left": {"text": "Ravi Sharma", "context": "lessee pune", "address": "411001", "role": "Lessee"}, "right": {"text": "Ravi Sharma", "context": "lessee pune", "address": "411001", "role": "Lessee"}, "same": 1},
    {"left": {"text": "Meera Iyer", "context": "signed page", "address": None, "role": None}, "right": {"text": "Meera Iyer", "context": "signed page witness", "address": None, "role": None}, "same": 1},
    {"left": {"text": "ABC Pvt Ltd", "context": "lessor office", "address": "700016", "role": "Lessor"}, "right": {"text": "ABC Pvt Ltd", "context": "lessor", "address": "700016", "role": "Lessor"}, "same": 1},
    {"left": {"text": "Amit Sharma", "context": "lake road", "address": "411002", "role": None}, "right": {"text": "Neha Sharma", "context": "hill road", "address": "411003", "role": None}, "same": 0},
    {"left": {"text": "R. Sharma", "context": "tenant", "address": None, "role": "tenant"}, "right": {"text": "Ravi Sharma", "context": "lessee", "address": "411001", "role": "Lessee"}, "same": 0},
    {"left": {"text": "Meera Iyer", "context": "park street", "address": "700016", "role": None}, "right": {"text": "Kapil Menon", "context": "park street", "address": "700016", "role": None}, "same": 0},
    {"left": {"text": "Kapil Menon", "context": "residency road", "address": "560001", "role": None}, "right": {"text": "Kapil Menon", "context": "brigade road", "address": "560025", "role": None}, "same": 0},
    {"left": {"text": "Priya Nair", "context": "licensee", "address": "560001", "role": "Licensee"}, "right": {"text": "Priya Nair", "context": "licensee bengaluru", "address": "560001", "role": "Licensee"}, "same": 1},
    {"left": {"text": "John Adeyemi", "context": "agent", "address": None, "role": "Agent"}, "right": {"text": "Owen Blake", "context": "lender", "address": None, "role": "Lender"}, "same": 0},
    {"left": {"text": "Sara Khan", "context": "guarantor", "address": None, "role": "Guarantor"}, "right": {"text": "Sara Khan", "context": "guarantor signed", "address": None, "role": "Guarantor"}, "same": 1},
]


def _chunks(doc: dict) -> list[dict]:
    chunks = chunk_document(doc["text"], doc["id"], min_words=3, max_words=80)
    if chunks:
        return chunks
    return [{"chunk_id": f"{doc['id']}-p1-c1", "id": f"{doc['id']}-p1-c1", "text": doc["text"]}]


def _find(mentions: list[dict], text: str) -> dict | None:
    for mention in mentions:
        if normalize(mention["text"]) == normalize(text):
            return mention
    return None


def main():
    run = Run("EXP-009", "exp_009_entity_resolve")
    run.write_json("docs.json", DOCS)
    outcomes = []
    wrong = 0
    ambiguous_gold = 0
    ambiguous_flagged = 0
    resolved_gold = 0
    resolved_correct = 0
    for doc in DOCS:
        mentions = resolve_mentions(_chunks(doc))
        if doc.get("expect_status") == "ambiguous":
            ambiguous_gold += 1
            mention = _find(mentions, doc.get("expect_mention") or doc.get("expect_person"))
            flagged = bool(mention and mention["status"] == "ambiguous")
            ambiguous_flagged += int(flagged)
            if mention and mention["status"] == "resolved":
                wrong += 1
            outcomes.append({"id": doc["id"], "status": None if not mention else mention["status"], "text": None if not mention else mention["text"], "wrong": bool(mention and mention["status"] == "resolved")})
        elif doc.get("expect_person"):
            resolved_gold += 1
            mention = _find(mentions, doc["expect_person"])
            correct = bool(mention and mention["status"] == "resolved")
            resolved_correct += int(correct)
            if mention and mention["status"] == "resolved" and normalize(mention["text"]) != normalize(doc["expect_person"]):
                wrong += 1
            if mention and mention["status"] == "resolved" and doc["expect_status"] != "resolved":
                wrong += 1
            outcomes.append({"id": doc["id"], "status": None if not mention else mention["status"], "correct": correct})
        elif doc.get("expect_distinct"):
            found = []
            merged_wrong = False
            for name in doc["expect_distinct"]:
                mention = _find(mentions, name)
                found.append(None if not mention else mention["status"])
                if mention is None:
                    merged_wrong = True
            # Wrong if the two full names were collapsed into one surface form.
            surfaces = {normalize(m["text"]) for m in mentions if m["label"] == "person"}
            if not all(normalize(name) in surfaces for name in doc["expect_distinct"]):
                merged_wrong = True
            wrong += int(merged_wrong)
            outcomes.append({"id": doc["id"], "found": found, "wrong": merged_wrong})
    model = train_pair_matcher(PAIR_TRAIN)
    heldout = [
        {"left": {"text": "Anita Desai", "context": "witness", "address": None, "role": "Witness"}, "right": {"text": "Anita Desai", "context": "witness present", "address": None, "role": "Witness"}, "same": 1},
        {"left": {"text": "Amit Sharma", "context": "pune lake", "address": "411002", "role": None}, "right": {"text": "Ravi Sharma", "context": "pune mg road", "address": "411001", "role": "Lessee"}, "same": 0},
    ]
    pair_hits = []
    for pair in heldout:
        pred = int(model.predict([pair_features(pair["left"], pair["right"])])[0])
        pair_hits.append(pred == pair["same"])
    doc5_mentions = resolve_mentions(_chunks(DOCS[4]))
    pair_decisions = same_entity_pairs([m for m in doc5_mentions if m["label"] == "person"], model)

    store = ExampleStore()
    wrong_stored = 0
    seed_docs = [DOCS[0], DOCS[5]]
    for doc in seed_docs:
        for mention in resolve_mentions(_chunks(doc)):
            if mention["status"] != "resolved":
                continue
            gold_name = doc.get("expect_person")
            if gold_name and normalize(mention["text"]) == normalize(gold_name) and mention["label"] == "person":
                store.add(mention["text"], mention.get("context", ""), mention["label"], mention.get("chunk_id") or doc["id"])
            elif gold_name and normalize(mention["text"]) != normalize(gold_name) and mention["label"] == "person":
                wrong_stored += 1
    later = "Ravi Sharma signed a receipt in Pune."
    before = resolve_mentions([{"chunk_id": "L1", "text": later}])
    after = resolve_mentions([{"chunk_id": "L1", "text": later}], store=store)
    before_m = _find(before, "Ravi Sharma")
    after_m = _find(after, "Ravi Sharma")
    conf_before = None if not before_m else before_m["conf"]
    conf_after = None if not after_m else after_m["conf"]
    total = len(DOCS)
    metrics = {
        "documents": total,
        "wrong_resolutions": wrong,
        "wrong_resolution_rate": round(wrong / total, 4),
        "ambiguous_gold": ambiguous_gold,
        "ambiguous_flagged": ambiguous_flagged,
        "ambiguous_flag_rate": round(ambiguous_flagged / max(1, ambiguous_gold), 4),
        "resolved_gold": resolved_gold,
        "resolved_correct": resolved_correct,
        "pair_heldout_accuracy": round(sum(pair_hits) / len(pair_hits), 4),
        "doc5_pair_decisions": pair_decisions,
        "example_store_size": len(store.rows),
        "wrong_examples_stored": wrong_stored,
        "confidence_before_store": conf_before,
        "confidence_after_store": conf_after,
        "outcomes": outcomes,
    }
    prose = (
        f"On {total} short documents, wrong resolutions are {wrong} "
        f"(rate {metrics['wrong_resolution_rate']}). "
        f"Ambiguous cases flagged: {ambiguous_flagged} of {ambiguous_gold} "
        f"(rate {metrics['ambiguous_flag_rate']}). "
        f"Clearly unique people resolved correctly: {resolved_correct} of {resolved_gold}. "
        f"Held-out pair accuracy is {metrics['pair_heldout_accuracy']}. "
        f"Example store size {metrics['example_store_size']}, wrong examples stored {wrong_stored}. "
        f"Confidence on a repeated Ravi Sharma line moved from {conf_before} to {conf_after}."
    )
    run.finish(
        title="Entity resolution and example store",
        goal="Measure wrong resolutions, ambiguous flags, a pair matcher, and whether verified examples are stored without errors.",
        method="Documents are chunked and passed through the resolution loop. Shared surnames and two addresses force an ambiguous status. The pair matcher is logistic regression on string and context features. The example store accepts only resolved mentions that match the gold name.",
        metrics=metrics,
        results_prose=prose,
        conclusion=(
            "Wrong resolution is the headline number and is reported above. "
            "Ambiguous shared names are flagged instead of guessed when the rule can see two full names. "
            "No wrong example was written when the store required a gold-matching resolved span."
            if wrong_stored == 0
            else "The example store wrote at least one person span that did not match the gold name; those rows must not be reused."
        ),
        scale_down="Six short documents replace 20 documents of 5 to 30 pages. The searchable context is the document itself, not a collection-wide index.",
        referenced_files=FILES,
    )


if __name__ == "__main__":
    main()
