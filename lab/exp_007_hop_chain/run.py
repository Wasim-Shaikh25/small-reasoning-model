"""EXP-007: multi-hop chaining and the date calculator (architecture Experiment D)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.calc import add_period
from lab.common.harness import Run
from lab.common.qa import answer_question
from lab.common.textutil import normalize

FILES = [
    "lab/exp_007_hop_chain/run.py",
    "lab/common/qa.py",
    "lab/common/calc.py",
    "lab/common/nli.py",
    "lab/common/textutil.py",
    "lab/common/harness.py",
    "data/exp_007_hop_chain/items.json",
    "data/exp_007_hop_chain/results.json",
]

ITEMS = [
    {
        "id": "D01",
        "hops": 2,
        "questions": ["Who is the Lessee?", "What is the address of {prev}?"],
        "golds": ["Ravi Sharma", "14 MG Road, Pune 411001"],
        "passages": [
            "Ravi Sharma (the Lessee) signed the deed.",
            "Ravi Sharma resides at 14 MG Road, Pune 411001.",
            "Anita Sharma teaches in Pune.",
        ],
    },
    {
        "id": "D02",
        "hops": 2,
        "questions": ["Who is the Lessor?", "Where is the office of {prev}?"],
        "golds": ["ABC Pvt Ltd", "48 Park Street, Kolkata 700016"],
        "passages": [
            "ABC Pvt Ltd (the Lessor) executed the deed.",
            "The office of ABC Pvt Ltd is 48 Park Street, Kolkata 700016.",
        ],
    },
    {
        "id": "D03",
        "hops": 2,
        "questions": ["What is the start date?", "What is the notice period?"],
        "golds": ["1 January 2024", "30 days"],
        "calc": {"gold": "31 January 2024"},
        "passages": ["The start date is 1 January 2024.", "The notice period is 30 days."],
    },
    {
        "id": "D04",
        "hops": 3,
        "questions": [
            "Who is the Lessee?",
            "What is the city of {prev}?",
            "What is the postcode in that address for {prev}?",
        ],
        "golds": ["Ravi Sharma", "Pune", "411001"],
        "passages": [
            "Ravi Sharma is the Lessee.",
            "Ravi Sharma resides at 14 MG Road, Pune 411001.",
        ],
    },
    {
        "id": "D05",
        "hops": 2,
        "questions": ["What is the security deposit?", "What is the rent?"],
        "golds": ["INR 50000", "INR 25000"],
        "passages": ["The security deposit is INR 50000.", "The monthly rent is INR 25000."],
    },
    {
        "id": "D06",
        "hops": 2,
        "questions": ["What does zorb mean?", "How many days does that definition mention?"],
        "golds": ["a refund issued after 14 days", "14"],
        "passages": ["A zorb is a refund issued after 14 days."],
    },
    {
        "id": "D07",
        "hops": 3,
        "questions": ["Who signed the page?", "On what date did {prev} sign?", "Which document date is that?"],
        "golds": ["Meera Iyer", "5 January 2024", "5 January 2024"],
        "passages": ["Signed by Meera Iyer on 5 January 2024."],
    },
    {
        "id": "D08",
        "hops": 2,
        "questions": ["What is the cure period?", "What is the notice period?"],
        "golds": ["10 days", "30 days"],
        "passages": ["The cure period is 10 days.", "The notice period is 30 days.", "The flower show period is listed on the board."],
    },
    {
        "id": "D09",
        "hops": 2,
        "questions": ["What is the delivery date?", "What is the warranty length?"],
        "golds": ["1 March 2024", "15 days"],
        "calc": {"gold": "16 March 2024"},
        "passages": ["The delivery date is 1 March 2024.", "The warranty length is 15 days."],
    },
    {
        "id": "D10",
        "hops": 2,
        "questions": ["Who is the former tenant?", "Who signed the current page?"],
        "golds": ["Kapil Iyer", "Meera Iyer"],
        "passages": ["The former tenant was Kapil Iyer.", "Signed by Meera Iyer on 5 January 2024."],
    },
    {
        "id": "D11",
        "hops": 3,
        "questions": ["What is item A?", "What is item B?", "Which amount is the deposit rather than the rent?"],
        "golds": ["INR 50000", "INR 25000", "INR 50000"],
        "passages": ["Item A is INR 50000 and it is the deposit.", "Item B is INR 25000 and it is the rent."],
    },
    {
        "id": "D12",
        "hops": 2,
        "questions": ["What is the quorum code?", "What is the committee size?"],
        "golds": ["41827", "three members"],
        "passages": ["The violet quorum code is 41827.", "The committee quorum is three members."],
    },
]


def _hit(pred: str | None, gold: str) -> bool:
    if not pred:
        return False
    return normalize(gold) in normalize(pred) or normalize(pred) in normalize(gold)


def main():
    run = Run("EXP-007", "exp_007_hop_chain")
    details = []
    by_hops = {2: [], 3: []}
    calc_ok = []
    for item in ITEMS:
        passages = [{"id": f"C{i}", "text": text} for i, text in enumerate(item["passages"])]
        prev = ""
        preds = []
        hops_correct = []
        for question, gold in zip(item["questions"], item["golds"]):
            asked = question.format(prev=prev)
            qa = answer_question(asked, passages, tau=0.25)
            pred = qa["span"]
            preds.append(pred)
            hops_correct.append(_hit(pred, gold))
            prev = pred or ""
        if item.get("calc"):
            result = add_period(preds[0] or "", preds[1] or "")
            pred = result.get("result") if result.get("ok") else None
            calc_hit = _hit(pred, item["calc"]["gold"])
            calc_ok.append({"ok": bool(result.get("ok")), "hit": calc_hit, "pred": pred, "shown_inputs": result.get("inputs")})
            preds.append(pred)
            hops_correct.append(calc_hit)
        all_ok = all(hops_correct)
        by_hops[item["hops"]].append(all_ok)
        details.append({"id": item["id"], "hops": item["hops"], "preds": preds, "golds": item["golds"], "hop_hits": hops_correct, "chain_correct": all_ok})
    run.write_json("items.json", details)
    metrics = {
        "n": len(details),
        "chain_accuracy": round(sum(d["chain_correct"] for d in details) / len(details), 4),
        "accuracy_2hop": round(sum(by_hops[2]) / max(1, len(by_hops[2])), 4),
        "n_2hop": len(by_hops[2]),
        "accuracy_3hop": round(sum(by_hops[3]) / max(1, len(by_hops[3])), 4),
        "n_3hop": len(by_hops[3]),
        "calculator_cases": len(calc_ok),
        "calculator_accuracy": round(sum(1 for row in calc_ok if row["hit"]) / max(1, len(calc_ok)), 4) if calc_ok else None,
        "max_reliable_hop_count": 2 if (sum(by_hops[2]) / max(1, len(by_hops[2])) >= 0.5 and sum(by_hops[3]) / max(1, len(by_hops[3])) < 0.5) else (3 if sum(by_hops[3]) / max(1, len(by_hops[3])) >= 0.5 else 1),
    }
    prose = (
        f"Chain accuracy on {metrics['n']} items is {metrics['chain_accuracy']}. "
        f"2-hop accuracy is {metrics['accuracy_2hop']} (n={metrics['n_2hop']}). "
        f"3-hop accuracy is {metrics['accuracy_3hop']} (n={metrics['n_3hop']}). "
        f"Calculator checks: {metrics['calculator_accuracy']} on {metrics['calculator_cases']} cases. "
        f"Recorded maximum reliable hop count at the 0.5 cutoff used here: {metrics['max_reliable_hop_count']}."
    )
    run.finish(
        title="Multi-hop chaining",
        goal="Measure 2-hop and 3-hop extractive chaining, including date arithmetic done in code.",
        method="Each hop inserts the previous span into the next question and runs extractive QA. Date endings call add_period on the extracted start and length. A chain is correct only if every hop matches.",
        metrics=metrics,
        results_prose=prose,
        conclusion=(
            f"The reliable hop depth on this small set, using a 0.5 accuracy cutoff, is {metrics['max_reliable_hop_count']}. "
            "The controller should keep asks inside that depth and send arithmetic to the calculator."
        ),
        scale_down="Twelve original chains replace HotpotQA plus 30 custom items. No pretrained QA model is loaded.",
        referenced_files=FILES,
    )


if __name__ == "__main__":
    main()
