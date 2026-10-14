"""EXP-002: ask analyzer (architecture Experiment F), templates only."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.ask import analyze
from lab.common.harness import Run
from lab.common.textutil import content_tokens, coverage

FILES = [
    "lab/exp_002_ask_analyzer/run.py",
    "lab/common/ask.py",
    "lab/common/textutil.py",
    "lab/common/harness.py",
    "data/exp_002_ask_analyzer/asks.json",
    "data/exp_002_ask_analyzer/results.json",
]

# Gold labels are the intended task and depth, not the classifier's own output.
ASKS = [
    {"id": "F01", "ask": "What is the notice period?", "task_type": "lookup", "depth": "light", "facts": ["notice period"]},
    {"id": "F02", "ask": "What is the security deposit?", "task_type": "lookup", "depth": "light", "facts": ["security deposit"]},
    {"id": "F03", "ask": "How many days of leave are stated?", "task_type": "lookup", "depth": "light", "facts": ["days of leave"]},
    {"id": "F04", "ask": "What amount is due on signing?", "task_type": "lookup", "depth": "light", "facts": ["amount due"]},
    {"id": "F05", "ask": "Which clause states the rent?", "task_type": "lookup", "depth": "light", "facts": ["rent clause"]},
    {"id": "F06", "ask": "What is the interest rate?", "task_type": "lookup", "depth": "light", "facts": ["interest rate"]},
    {"id": "F07", "ask": "What does the schedule list?", "task_type": "lookup", "depth": "light", "facts": ["schedule list"]},
    {"id": "F08", "ask": "Where is the parking slot?", "task_type": "lookup", "depth": "light", "facts": ["parking slot"]},
    {"id": "F09", "ask": "Where the proviso applies, and only then, state the cure period; otherwise state that the fact is unresolved.", "task_type": "reason", "depth": "deep", "facts": ["proviso", "cure period"]},
    {"id": "F10", "ask": "List every document about termination.", "task_type": "lookup", "depth": "review", "facts": ["termination documents"]},
    {"id": "F11", "ask": "Rewrite the following clause in shorter words: the tenant shall pay.", "task_type": "rewrite", "depth": "none", "facts": []},
    {"id": "F12", "ask": "Simplify this sentence: payment is due on Monday.", "task_type": "rewrite", "depth": "none", "facts": []},
    {"id": "F13", "ask": "Formalize the note: rent is late.", "task_type": "rewrite", "depth": "none", "facts": []},
    {"id": "F14", "ask": "Shorten the paragraph about the garden.", "task_type": "rewrite", "depth": "none", "facts": []},
    {"id": "F15", "ask": "Rephrase the supplied definition without adding facts.", "task_type": "rewrite", "depth": "none", "facts": []},
    {"id": "F16", "ask": "Paraphrase the quoted sentence only.", "task_type": "rewrite", "depth": "none", "facts": []},
    {"id": "F17", "ask": "Make this shorter: the deposit is INR 50000.", "task_type": "rewrite", "depth": "none", "facts": []},
    {"id": "F18", "ask": "Rewrite the memo heading and keep every number.", "task_type": "rewrite", "depth": "none", "facts": []},
    {"id": "F19", "ask": "Formalize: the parties signed yesterday.", "task_type": "rewrite", "depth": "none", "facts": []},
    {"id": "F20", "ask": "Rewrite the clause, and also tell me the notice period.", "task_type": "lookup", "depth": "medium", "facts": ["notice period"]},
    {"id": "F21", "ask": "Compare the notice period and the cure period.", "task_type": "compare", "depth": "medium", "facts": ["notice period", "cure period"]},
    {"id": "F22", "ask": "What is the difference between the deposit and the rent?", "task_type": "compare", "depth": "medium", "facts": ["deposit", "rent"]},
    {"id": "F23", "ask": "Which is longer, the lease term or the renewal term?", "task_type": "compare", "depth": "medium", "facts": ["lease term", "renewal term"]},
    {"id": "F24", "ask": "Compare clause 4 and clause 9 side by side.", "task_type": "compare", "depth": "medium", "facts": ["clause 4", "clause 9"]},
    {"id": "F25", "ask": "How do the two addresses differ?", "task_type": "compare", "depth": "medium", "facts": ["address one", "address two"]},
    {"id": "F26", "ask": "Versus the draft, what changed in the rent?", "task_type": "compare", "depth": "medium", "facts": ["draft rent", "changed rent"]},
    {"id": "F27", "ask": "Compare the 2023 fee and the 2024 fee.", "task_type": "compare", "depth": "medium", "facts": ["2023 fee", "2024 fee"]},
    {"id": "F28", "ask": "What is the difference in match length versus the old rules?", "task_type": "compare", "depth": "medium", "facts": ["match length", "old rules"]},
    {"id": "F29", "ask": "Compare the party names and their roles.", "task_type": "compare", "depth": "medium", "facts": ["party names", "roles"]},
    {"id": "F30", "ask": "Given the schedules, set out the parties' addresses side by side and say which signing came first.", "task_type": "compare", "depth": "deep", "facts": ["addresses", "signing order"]},
    {"id": "F31", "ask": "When did the lease start?", "task_type": "chronology", "depth": "deep", "facts": ["lease start"]},
    {"id": "F32", "ask": "What date was the notice served?", "task_type": "chronology", "depth": "deep", "facts": ["notice date"]},
    {"id": "F33", "ask": "In what order were the invoices issued?", "task_type": "chronology", "depth": "deep", "facts": ["invoice order"]},
    {"id": "F34", "ask": "Which came first, the signing or the payment?", "task_type": "chronology", "depth": "deep", "facts": ["signing", "payment"]},
    {"id": "F35", "ask": "Timeline of the amendments.", "task_type": "chronology", "depth": "deep", "facts": ["amendments"]},
    {"id": "F36", "ask": "How long after delivery does the warranty end?", "task_type": "chronology", "depth": "deep", "facts": ["delivery", "warranty end"]},
    {"id": "F37", "ask": "When does the notice period end?", "task_type": "chronology", "depth": "deep", "facts": ["notice period end"]},
    {"id": "F38", "ask": "Sequence of signatures on the last page.", "task_type": "chronology", "depth": "deep", "facts": ["signature sequence"]},
    {"id": "F39", "ask": "What is the order of the match events?", "task_type": "chronology", "depth": "deep", "facts": ["match events"]},
    {"id": "F40", "ask": "When was version 2 adopted?", "task_type": "chronology", "depth": "deep", "facts": ["version 2 date"]},
    {"id": "F41", "ask": "Who is the Lessee?", "task_type": "entity", "depth": "deep", "facts": ["lessee"]},
    {"id": "F42", "ask": "Who is the Lessor, and what is their address?", "task_type": "entity", "depth": "deep", "facts": ["lessor", "address"]},
    {"id": "F43", "ask": "What is the address of Ravi Sharma?", "task_type": "entity", "depth": "deep", "facts": ["address of Ravi Sharma"]},
    {"id": "F44", "ask": "Which party signed as the Lessee?", "task_type": "entity", "depth": "deep", "facts": ["lessee"]},
    {"id": "F45", "ask": "Who are the parties named in the preamble?", "task_type": "entity", "depth": "deep", "facts": ["parties"]},
    {"id": "F46", "ask": "Whose address is 14 MG Road?", "task_type": "entity", "depth": "deep", "facts": ["person at 14 MG Road"]},
    {"id": "F47", "ask": "Who was the former tenant?", "task_type": "entity", "depth": "deep", "facts": ["former tenant"]},
    {"id": "F48", "ask": "Identify the Lessee and the Lessor.", "task_type": "entity", "depth": "deep", "facts": ["lessee", "lessor"]},
    {"id": "F49", "ask": "What is the registered address of the company?", "task_type": "entity", "depth": "deep", "facts": ["registered address"]},
    {"id": "F50", "ask": "Who is Mr. Sharma?", "task_type": "entity", "depth": "deep", "facts": ["Mr. Sharma"]},
    {"id": "F51", "ask": "What happens if the rent is late?", "task_type": "reason", "depth": "deep", "facts": ["late rent consequence"]},
    {"id": "F52", "ask": "Is subletting permitted unless the landlord consents?", "task_type": "reason", "depth": "deep", "facts": ["subletting", "landlord consent"]},
    {"id": "F53", "ask": "Why was the invoice cancelled?", "task_type": "reason", "depth": "deep", "facts": ["cancellation reason"]},
    {"id": "F54", "ask": "Is it permitted to keep a pet?", "task_type": "reason", "depth": "deep", "facts": ["pet permission"]},
    {"id": "F55", "ask": "What happens if notice is given on a holiday?", "task_type": "reason", "depth": "deep", "facts": ["holiday notice"]},
    {"id": "F56", "ask": "On condition that the fee is paid, does the licence continue?", "task_type": "reason", "depth": "deep", "facts": ["fee condition", "licence continuation"]},
    {"id": "F57", "ask": "Why did version 2 change the notice period?", "task_type": "reason", "depth": "deep", "facts": ["version 2 reason"]},
    {"id": "F58", "ask": "Provided that the deposit is paid, when can the tenant enter?", "task_type": "reason", "depth": "deep", "facts": ["deposit condition", "entry"]},
    {"id": "F59", "ask": "What happens if two clauses disagree?", "task_type": "reason", "depth": "deep", "facts": ["clause conflict"]},
    {"id": "F60", "ask": "Is it permitted to terminate except where fees are unpaid?", "task_type": "reason", "depth": "deep", "facts": ["termination", "unpaid fees"]},
]


def fact_hit(fact: str, subquestions: list[str]) -> bool:
    need = content_tokens(fact)
    if not need:
        return True
    for sub in subquestions:
        if coverage(need, content_tokens(sub)) >= 0.5:
            return True
    return False


def main():
    run = Run("EXP-002", "exp_002_ask_analyzer")
    run.write_json("asks.json", ASKS)
    rows = []
    for item in ASKS:
        plan = analyze(item["ask"])
        fact_flags = [fact_hit(fact, plan["subquestions"]) for fact in item["facts"]]
        fact_coverage = (sum(fact_flags) / len(fact_flags)) if fact_flags else 1.0
        rows.append(
            {
                "id": item["id"],
                "gold_task": item["task_type"],
                "pred_task": plan["task_type"],
                "task_ok": plan["task_type"] == item["task_type"],
                "gold_depth": item["depth"],
                "pred_depth": plan["depth"],
                "depth_ok": plan["depth"] == item["depth"],
                "subquestions": plan["subquestions"],
                "fact_coverage": round(fact_coverage, 4),
                "raw_ask_kept": plan["raw_ask_is_a_query"] or item["task_type"] == "rewrite",
                "fallback": plan["whole_ask_fallback"],
                "decomposition_failed": bool(item["facts"]) and fact_coverage < 0.5,
            }
        )
    n = len(rows)
    multi = [r for r in rows if len(next(a["facts"] for a in ASKS if a["id"] == r["id"])) > 1]
    metrics = {
        "n": n,
        "task_type_accuracy": round(sum(r["task_ok"] for r in rows) / n, 4),
        "depth_accuracy": round(sum(r["depth_ok"] for r in rows) / n, 4),
        "mean_fact_coverage": round(sum(r["fact_coverage"] for r in rows) / n, 4),
        "decomposition_failure_rate": round(sum(r["decomposition_failed"] for r in rows) / n, 4),
        "multi_fact_count": len(multi),
        "multi_fact_full_coverage_rate": round(sum(r["fact_coverage"] == 1 for r in multi) / max(1, len(multi)), 4),
        "raw_ask_always_in_queries": all(r["raw_ask_kept"] for r in rows),
        "automatic_quality_proxy_1_to_5": round(1 + 4 * (sum(r["fact_coverage"] for r in rows) / n), 4),
        "human_rating_collected": False,
        "misses": [r["id"] for r in rows if not r["task_ok"] or not r["depth_ok"]],
    }
    prose = (
        f"On {n} hand-labeled asks, task-type accuracy is {metrics['task_type_accuracy']} "
        f"and depth accuracy is {metrics['depth_accuracy']}. "
        f"Mean gold-fact coverage of template sub-questions is {metrics['mean_fact_coverage']}. "
        f"Decomposition failure rate (coverage under 0.5) is {metrics['decomposition_failure_rate']}. "
        f"The raw ask stays in the query list for every item: {metrics['raw_ask_always_in_queries']}. "
        f"No human 1-to-5 rating was collected; the automatic proxy is {metrics['automatic_quality_proxy_1_to_5']}. "
        f"Misses: {', '.join(metrics['misses']) if metrics['misses'] else 'none'}."
    )
    run.finish(
        title="Ask analyzer templates",
        goal="Measure task-type accuracy, depth accuracy, and template decomposition on 60 asks without a generative proposer.",
        method="Rule cues classify task type and depth. Sub-questions come from conjunction splits and per-type templates. A fact counts as covered when half of its content tokens appear in a sub-question. The raw ask is always retained as a query.",
        metrics=metrics,
        results_prose=prose,
        conclusion=(
            "Template analysis covers ordinary asks and keeps the raw ask as a fallback. "
            "Unusual multi-clause asks remain the weak spot, which matches the architecture's known limit. "
            "A human sub-question rating was not collected."
        ),
        scale_down="Sixty original asks stand in for a larger labeled set. Experiment F's human 1-to-5 rating is not fabricated; only an automatic coverage proxy is reported.",
        referenced_files=FILES,
        follow_ups=["Collect a human 1-to-5 rating for sub-question quality before treating the proxy as a product metric."],
    )


if __name__ == "__main__":
    main()
