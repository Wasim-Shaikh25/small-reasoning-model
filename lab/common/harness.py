"""Run harness: timers, RSS, and the pure scoring functions from the architecture."""

from __future__ import annotations

import json
import resource
import time
from pathlib import Path

from lab.common.textutil import modals, normalize, numbers, span_in_passage

ROOT = Path(__file__).resolve().parents[2]


def peak_rss_mb() -> float:
    # Linux ru_maxrss is kilobytes.
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2)


def prf(pred: set, gold: set) -> dict[str, float]:
    tp = len(pred & gold)
    p = tp / max(1, len(pred))
    r = tp / max(1, len(gold))
    f = 2 * p * r / max(1e-9, p + r)
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4), "tp": tp}


def score_qa(item: dict, qa_out: dict) -> dict[str, bool]:
    answerable = item["answerable"]
    abstained = qa_out["no_answer"] >= item["tau_no_answer"] or qa_out["span"] is None
    passages = item["passages"]
    passage = passages.get(qa_out.get("passage_id"), "")
    exact = (
        answerable
        and not abstained
        and normalize(qa_out["span"]) == normalize(item["gold"])
    )
    return {
        "correct_abstain": (not answerable) and abstained,
        "false_answer": (not answerable) and not abstained,
        "missed_answer": answerable and abstained,
        "exact_match": exact,
        "span_valid": (not abstained) and span_in_passage(qa_out["span"], passage),
    }


def fidelity(src: str, out: str) -> dict:
    sn, on = set(numbers(src)), set(numbers(out))
    sm = sorted(modals(src))
    om = sorted(modals(out))
    return {
        "numbers_dropped": sorted(sn - on),
        "numbers_added": sorted(on - sn),
        "modal_changed": sm != om,
    }


class Run:
    def __init__(self, exp_id: str, slug: str):
        self.exp_id = exp_id
        self.slug = slug
        self.t0 = time.perf_counter()
        self.out_dir = ROOT / "data" / slug
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def write_json(self, name: str, payload) -> str:
        path = self.out_dir / name
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return str(path.relative_to(ROOT))

    def finish(
        self,
        *,
        title: str,
        goal: str,
        method: str,
        metrics: dict,
        results_prose: str,
        conclusion: str,
        scale_down: str,
        referenced_files: list[str],
        follow_ups: list[str] | None = None,
    ) -> dict:
        payload = {
            "id": self.exp_id,
            "title": title,
            "status": "closed",
            "goal": goal,
            "method": method,
            "metrics": metrics,
            "results_prose": results_prose,
            "conclusion": conclusion,
            "scale_down": scale_down,
            "referenced_files": referenced_files,
            "follow_ups": follow_ups or [],
            "elapsed_sec": round(time.perf_counter() - self.t0, 4),
            "peak_rss_mb": peak_rss_mb(),
        }
        self.write_json("results.json", payload)
        print(f"{self.exp_id} {title}")
        print(json.dumps(metrics, indent=2))
        print(results_prose)
        print("---")
        return payload
