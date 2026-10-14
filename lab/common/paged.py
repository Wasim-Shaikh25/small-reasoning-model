"""Working set with pinning, eviction, and a notebook of sub-question rows."""

from __future__ import annotations


class Notebook:
    def __init__(self, subquestions: list[str]):
        self.rows = [
            {"fact": q, "status": "missing", "span": None, "evidence_ids": [], "conflicts": []}
            for q in subquestions
        ]

    def update(self, index: int, span: str | None, evidence_id: str | None, status: str):
        row = self.rows[index]
        if status == "found" and span:
            row["status"] = "found"
            row["span"] = span
            if evidence_id and evidence_id not in row["evidence_ids"]:
                row["evidence_ids"].append(evidence_id)
        elif status == "conflicted":
            row["status"] = "conflicted"
            row["conflicts"].append(evidence_id)
        elif row["status"] == "missing":
            row["status"] = status

    def coverage(self) -> dict:
        total = len(self.rows) or 1
        found = sum(1 for row in self.rows if row["status"] == "found")
        return {"found": found, "total": len(self.rows), "ratio": round(found / total, 4)}


class WorkingSet:
    def __init__(self, budget: int):
        self.budget = budget
        self.pinned: list[dict] = []
        self.pages: list[dict] = []
        self.faults = 0
        self.evictions = 0

    def pin(self, item: dict):
        item = {**item, "pinned": True}
        self.pinned = [p for p in self.pinned if p.get("id") != item.get("id")]
        self.pinned.append(item)

    def admit(self, passage: dict, relevance: float):
        pid = passage.get("id")
        if any(p.get("id") == pid for p in self.pages) or any(p.get("id") == pid for p in self.pinned):
            return
        self.pages.append({**passage, "relevance": relevance, "pinned": False})
        self._evict()

    def _evict(self):
        while len(self.pages) > self.budget:
            unpinned = [p for p in self.pages if not p.get("pinned")]
            if not unpinned:
                break
            victim = min(unpinned, key=lambda p: p.get("relevance", 0.0))
            self.pages = [p for p in self.pages if p.get("id") != victim.get("id")]
            self.evictions += 1

    def ids(self) -> set[str]:
        return {p.get("id") for p in self.pages} | {p.get("id") for p in self.pinned}

    def page_fault(self, passage: dict, relevance: float) -> bool:
        if passage.get("id") in self.ids():
            return False
        self.faults += 1
        self.admit(passage, relevance)
        return True
