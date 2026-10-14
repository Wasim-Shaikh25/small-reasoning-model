"""In-memory entity link graph. Optional expansion when lexical search misses a hop."""

from __future__ import annotations

from lab.common.textutil import normalize


class EntityGraph:
    def __init__(self):
        self.links: dict[str, set[str]] = {}
        self.passages_by_name: dict[str, set[str]] = {}

    def add(self, name: str, passage_id: str, also: str | None = None):
        key = normalize(name)
        self.passages_by_name.setdefault(key, set()).add(passage_id)
        if also:
            other = normalize(also)
            self.links.setdefault(key, set()).add(other)
            self.links.setdefault(other, set()).add(key)
            self.passages_by_name.setdefault(other, set()).add(passage_id)

    def expand_ids(self, names: list[str]) -> set[str]:
        ids: set[str] = set()
        seen = set()
        queue = [normalize(name) for name in names]
        while queue:
            name = queue.pop()
            if name in seen:
                continue
            seen.add(name)
            ids |= self.passages_by_name.get(name, set())
            for linked in self.links.get(name, set()):
                if linked not in seen:
                    queue.append(linked)
        return ids
