"""The one public entry point: resolve a connector, run the ask against
the taught-concept registry, render the result. The "framework/dependency
structure" the project owner asked for -- a caller declares where the data
comes from (YAML, like a message-queue connection) and gets back either a
rendered result or an honest "I don't know how to do this, teach me"
response. Nothing in this module is domain-specific; every domain-specific
behavior lives in a concept YAML (lab/common/concepts/) or a template JSON
(lab/common/templates/), both data, not code.
"""

from __future__ import annotations

from pathlib import Path

from lab.common.concept_tools import teach_and_run
from lab.common.connector_config import fetch_context, load_connector_config
from lab.common.render import RENDERERS


def run(
    ask: str,
    connector: dict | str | Path,
    output_format: str = "json",
    out_path: str | None = None,
    concepts: list[dict] | None = None,
) -> dict:
    """`connector` is either a YAML path or an already-loaded config dict
    (inline/records/file/qdrant/graph -- see lab.common.connector_config).
    `output_format` is one of "json", "md", "docx". `concepts`, if given,
    overrides the default `lab/common/concepts/*.yaml` scan -- a caller
    (a specific tenant/industry) can pass its own taught-concept set
    instead of relying on whatever is registered globally on disk; this
    is also how `lab/common/concepts/examples/` (never auto-loaded, see
    `concept_tools.load_concepts`) gets exercised for proof/test runs.
    Returns `teach_and_run`'s own result dict, with a `"rendered"` key
    added on success; a failure (`ok=False`, e.g. an untaught concept) is
    returned as-is, never rendered, never guessed at.
    """
    config = connector if isinstance(connector, dict) else load_connector_config(connector)
    ctx = fetch_context(config)
    outcome = teach_and_run(ask, ctx, concepts=concepts)
    if not outcome["ok"]:
        return outcome

    if output_format not in RENDERERS:
        raise ValueError(f"Unknown output_format {output_format!r}. Known: {sorted(RENDERERS)}")

    if output_format == "docx":
        rendered = RENDERERS["docx"](outcome["result"], ask, out_path or "output.docx")
    else:
        rendered = RENDERERS[output_format](outcome["result"], ask) if output_format == "md" else RENDERERS[output_format](outcome["result"])

    return {**outcome, "output_format": output_format, "rendered": rendered}
