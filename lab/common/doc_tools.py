"""The tool/template registry the project owner asked for by name: "tools like
this -> legal, study, company policy, email drafts, customer responses, than
under them templates ... any domain company can add their own things."

A template is DATA, never something the model invents -- the same "facts
only ever come from given data" rule this project already enforces for
content (FORBIDDEN.md), now extended to structure. A template's sections and
their per-section instructions are written by whoever actually knows that
document's real shape (a lawyer for a legal notice, an instructor for
lecture notes), checked into `lab/common/templates/<tool>/<template_id>.json`,
and never inferred by the rewriter from its own training data about "what a
writ petition generally looks like." Adding a new tool or template for a
company's own requirement means adding a new JSON file under this
directory -- no code change needed, which is the actual point of "any
domain company can add their own things."

Two tools exist so far (legal, study), one template each -- deliberately
not "1000 templates" yet: this registry and its selection mechanism need to
be proven correct on a couple of real cases before the catalog grows (the
same "measured, not assumed" discipline every other capability in this repo
was built under).

Selection (`select_tool`, `select_template`) reuses lab.common.
intent_signals' exact mechanism: bge cosine similarity between the ask and
each candidate's own description, picking the best match -- not a new,
separate scheme. A tool/template is picked by its own documented purpose,
the same way wants_document picks a signal by matching the ask's form, not
by a keyword list.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from lab.common.real_encoders import bge_embed

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def list_tools() -> list[dict]:
    """Every registered tool's manifest, read fresh from disk each call --
    templates are data a company can add to without restarting anything
    that caches them.
    """
    tools = []
    if not TEMPLATES_DIR.exists():
        return tools
    for tool_dir in sorted(p for p in TEMPLATES_DIR.iterdir() if p.is_dir()):
        manifest = tool_dir / "_tool.json"
        if manifest.exists():
            tools.append(json.loads(manifest.read_text(encoding="utf-8")))
    return tools


def list_templates(tool: str | None = None) -> list[dict]:
    """Every registered template, optionally scoped to one tool."""
    templates = []
    if not TEMPLATES_DIR.exists():
        return templates
    tool_dirs = [TEMPLATES_DIR / tool] if tool else sorted(p for p in TEMPLATES_DIR.iterdir() if p.is_dir())
    for tool_dir in tool_dirs:
        if not tool_dir.is_dir():
            continue
        for template_file in sorted(tool_dir.glob("*.json")):
            if template_file.name == "_tool.json":
                continue
            templates.append(json.loads(template_file.read_text(encoding="utf-8")))
    return templates


def load_template(template_id: str, tool: str | None = None) -> dict:
    for template in list_templates(tool):
        if template["id"] == template_id:
            return template
    raise ValueError(f"No registered template {template_id!r}" + (f" under tool {tool!r}" if tool else "") + f". Known: {[t['id'] for t in list_templates(tool)]}")


def _best_match(ask: str, candidates: list[dict], text_key: str) -> dict:
    if not candidates:
        return {"match": None, "score": 0.0, "ranked": []}
    descriptions = [c[text_key] for c in candidates]
    vecs = bge_embed([ask, *descriptions])
    ask_vec, cand_vecs = vecs[0], vecs[1:]
    scores = cand_vecs @ ask_vec
    ranked = sorted(zip(candidates, scores.tolist()), key=lambda pair: pair[1], reverse=True)
    best_candidate, best_score = ranked[0]
    return {
        "match": best_candidate,
        "score": round(float(best_score), 4),
        "ranked": [{"id": c.get("id", c.get("tool")), "score": round(float(s), 4)} for c, s in ranked],
    }


def select_tool(ask: str) -> dict:
    """Which registered tool this ask best matches, by description
    similarity -- a closed-set choice among named tools, not generation.
    Returns {"tool", "score", "ranked"}; "tool" is None if no tool is
    registered at all.
    """
    result = _best_match(ask, list_tools(), "description")
    return {"tool": result["match"]["tool"] if result["match"] else None, "score": result["score"], "ranked": result["ranked"]}


def select_template(ask: str, tool: str | None = None) -> dict:
    """Which registered template (optionally within one tool) this ask
    best matches. Returns {"template_id", "tool", "score", "ranked"}.
    """
    result = _best_match(ask, list_templates(tool), "description")
    match = result["match"]
    return {
        "template_id": match["id"] if match else None,
        "tool": match["tool"] if match else None,
        "score": result["score"],
        "ranked": result["ranked"],
    }


def assign_findings_to_sections(template: dict, findings: list[dict]) -> tuple[list[dict], list[dict]]:
    """Routes each finding to the template section whose own instructions
    it best matches -- a per-finding closed-set classification over the
    template's own declared sections, same bge-similarity mechanism as
    select_tool/select_template, not a new scheme.

    Returns (sections_with_findings, unassigned) -- "unassigned" is never
    silently dropped; a section with no findings routed to it is also kept
    (empty), visible in the result, not hidden.

    Scored against each section's `content_description` (what kind of
    content belongs there, phrased the way a finding itself reads), not
    its `instructions` (how to write it, phrased as directives to the
    rewriter). The two were originally the same field -- EXP-082 measured
    that collapsing most findings into one section (50%/33% routing
    accuracy on its first run) because directive language like "state
    exactly what is being demanded" doesn't resemble a finding's own
    phrasing closely enough for similarity scoring to discriminate.
    Falls back to `instructions` for a template that hasn't added the
    newer field.
    """
    sections = template["sections"]
    if not findings:
        return [{**s, "findings": []} for s in sections], []
    section_texts = [f"{s['title']}: {s.get('content_description', s['instructions'])}" for s in sections]
    statements = [f["statement"] for f in findings]
    vecs = bge_embed([*statements, *section_texts])
    statement_vecs, section_vecs = vecs[: len(statements)], vecs[len(statements) :]
    sims = statement_vecs @ section_vecs.T
    best_section_idx = np.argmax(sims, axis=1)

    assigned: list[list[dict]] = [[] for _ in sections]
    for finding, section_idx in zip(findings, best_section_idx):
        assigned[section_idx].append(finding)

    sections_with_findings = [{**s, "findings": assigned[i]} for i, s in enumerate(sections)]
    return sections_with_findings, []
