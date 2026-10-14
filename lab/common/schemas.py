"""Schema checks. One repair attempt, then the controller abstains."""

from __future__ import annotations


JUDGMENT_REQUIRED = ("ask", "task_type", "required_facts", "decision", "next_action")
DECISION_LABELS = {"supported", "contradicted", "inconclusive"}
FACT_STATUS = {"found", "missing", "conflicted"}
NEXT_ACTIONS = {"retrieve_more", "verify", "calculate", "answer", "abstain"}


def _repair_judgment(payload: dict) -> dict:
    repaired = dict(payload)
    decision = repaired.get("decision")
    if isinstance(decision, dict) and "confidence" in decision and isinstance(decision["confidence"], str):
        try:
            decision = dict(decision)
            decision["confidence"] = float(decision["confidence"])
            repaired["decision"] = decision
            repaired["_repaired"] = True
        except ValueError:
            pass
    if "required_facts" not in repaired:
        repaired["required_facts"] = []
        repaired["_repaired"] = True
    return repaired


def validate_judgment(payload: dict, *, allow_repair: bool = True) -> dict:
    errors = _judgment_errors(payload)
    if not errors:
        return {"ok": True, "payload": payload, "repaired": False, "errors": []}
    if allow_repair:
        repaired = _repair_judgment(payload)
        errors2 = _judgment_errors(repaired)
        if not errors2:
            return {"ok": True, "payload": repaired, "repaired": True, "errors": []}
        return {"ok": False, "payload": None, "repaired": True, "errors": errors2, "abstain": True}
    return {"ok": False, "payload": None, "repaired": False, "errors": errors, "abstain": True}


def _judgment_errors(payload: dict) -> list[str]:
    errors = []
    if not isinstance(payload, dict):
        return ["not_an_object"]
    for key in JUDGMENT_REQUIRED:
        if key not in payload:
            errors.append(f"missing:{key}")
    decision = payload.get("decision")
    if isinstance(decision, dict):
        if decision.get("label") not in DECISION_LABELS:
            errors.append("bad_decision_label")
        conf = decision.get("confidence")
        if not isinstance(conf, (int, float)):
            errors.append("bad_confidence")
    else:
        errors.append("decision_not_object")
    if payload.get("next_action") not in NEXT_ACTIONS:
        errors.append("bad_next_action")
    facts = payload.get("required_facts")
    if facts is not None and not isinstance(facts, list):
        errors.append("facts_not_list")
    if isinstance(facts, list):
        for i, fact in enumerate(facts):
            if not isinstance(fact, dict):
                errors.append(f"fact_{i}_not_object")
                continue
            if fact.get("status") not in FACT_STATUS:
                errors.append(f"fact_{i}_bad_status")
    return errors


def validate_note(note: dict) -> list[str]:
    errors = []
    for key in ("note_id", "kind", "statement", "source"):
        if key not in note:
            errors.append(f"missing:{key}")
    source = note.get("source") or {}
    for key in ("doc_id", "version", "chunk_id", "exact_text"):
        if key not in source:
            errors.append(f"source_missing:{key}")
    if note.get("kind") not in {"stated_fact", "entity_fact", "inference"}:
        errors.append("bad_kind")
    return errors
