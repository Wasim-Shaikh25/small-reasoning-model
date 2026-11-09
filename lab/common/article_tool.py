"""The `write_article` tool: one named, schema-checked entry point wrapping
everything built today (notes_to_findings, write_article, relationship_graph)
into a single callable with the same shape as this project's other named
tools (`lab.common.rewriter_backends.BACKENDS`, `lab.common.method_teaching.
PRIMITIVE_REGISTRY`) -- a fixed input contract, a fixed output contract,
validated before anything runs, never a guess at what a malformed call meant.

Input: {"notes": str, "sources": [{"id": str, "text": str}, ...],
"checkpoint": str (optional), "rewrite": bool (optional)}.

Output: {"ok": bool, "article": str (rendered markdown), "coverage",
"citations", "attribution", "rewrite_diagnostics", "relationships",
"errors"}. `ok=False` with `errors` set and everything else empty means the
input itself was invalid -- nothing was attempted, same abstain-don't-guess
discipline as every other primitive in this file's trail.
"""

from __future__ import annotations

import json
import sys

from lab.common.relationship_graph import build_relationship_graph, find_cycles
from lab.common.write_article import write_article

TOOL_NAME = "write_article"
TOOL_DESCRIPTION = (
    "Turn raw, possibly messy notes plus a few named sources into one cited "
    "article. Content comes only from the notes and sources -- nothing is "
    "invented. Also reports any directed relationship cycles found across "
    "the same input (e.g. A paid B, B paid C, C paid A)."
)


def _validate(payload: dict) -> list[str]:
    errors = []
    if not isinstance(payload, dict):
        return ["payload must be an object"]
    notes = payload.get("notes")
    if not isinstance(notes, str) or not notes.strip():
        errors.append("'notes' must be a non-empty string")
    sources = payload.get("sources")
    if not isinstance(sources, list):
        errors.append("'sources' must be a list")
    else:
        for i, s in enumerate(sources):
            if not isinstance(s, dict) or not s.get("id") or not isinstance(s.get("text"), str):
                errors.append(f"sources[{i}] must be {{'id': str, 'text': str}}")
    return errors


def _format_article(document: str, sources: list[dict], cycles: list[list[dict]]) -> str:
    lines = []
    for section in document.split("\n\n"):
        section_lines = section.split("\n")
        if not section_lines or not section_lines[0].strip():
            continue
        lines.append(f"## {section_lines[0]}")
        for item in section_lines[1:]:
            if item.strip():
                lines.append(f"- {item}")
        lines.append("")

    lines.append("## Sources")
    for s in sources:
        lines.append(f"- [{s['id']}] {s['text']}")
    lines.append("")

    if cycles:
        lines.append("## Relationships detected")
        for cycle in cycles:
            chain = " -> ".join([cycle[0]["from_text"]] + [e["to_text"] for e in cycle])
            flagged = any(e.get("antecedent_ambiguous") for e in cycle)
            note = "  (uses at least one guessed pronoun reference -- verify before relying on this)" if flagged else ""
            lines.append(f"- {chain}{note}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_article_tool(payload: dict) -> dict:
    errors = _validate(payload)
    if errors:
        return {
            "ok": False, "article": "", "coverage": None, "citations": None,
            "attribution": None, "rewrite_diagnostics": None, "relationships": None,
            "errors": errors,
        }

    notes = payload["notes"]
    sources = payload["sources"]
    checkpoint = payload.get("checkpoint", "gemma3:270m")
    rewrite = payload.get("rewrite", True)

    result = write_article(notes, sources, checkpoint=checkpoint, rewrite=rewrite)

    # Relationship detection runs on the pre-rewrite findings (original
    # source text + original note sentences) -- extract_fact_triple's
    # subject/object structure is only tested against that text, not
    # against a paraphrase an LLM may have produced.
    passages = [{"id": s["id"], "text": s["text"]} for s in sources]
    passages += [{"id": f["finding_id"], "text": f["statement"]} for f in result["attribution"]]
    graph = build_relationship_graph(passages)
    cycles = find_cycles(graph)

    article = _format_article(result["document"], sources, cycles)

    return {
        "ok": True,
        "article": article,
        "coverage": result["coverage"],
        "citations": result["citations"],
        "attribution": result["attribution"],
        "rewrite_diagnostics": result.get("rewrite_diagnostics"),
        "relationships": {
            "cycles": [
                {
                    "chain": [cycle[0]["from_text"]] + [e["to_text"] for e in cycle],
                    "ambiguous": any(e.get("antecedent_ambiguous") for e in cycle),
                    "edges": cycle,
                }
                for cycle in cycles
            ],
        },
        "errors": [],
    }


if __name__ == "__main__":
    raw = sys.stdin.read() if len(sys.argv) < 2 else open(sys.argv[1], encoding="utf-8").read()
    payload = json.loads(raw)
    output = write_article_tool(payload)
    if not output["ok"]:
        print(json.dumps({"errors": output["errors"]}, indent=2), file=sys.stderr)
        sys.exit(1)
    print(output["article"])
