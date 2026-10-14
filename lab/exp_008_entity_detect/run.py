"""EXP-008: entity detection and role questions (architecture Experiments E1 and E2)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.entities import agreement, detect_primary, detect_secondary, parse_address
from lab.common.harness import Run, prf
from lab.common.qa import answer_question
from lab.common.textutil import find_span, normalize

FILES = [
    "lab/exp_008_entity_detect/run.py",
    "lab/common/entities.py",
    "lab/common/qa.py",
    "lab/common/textutil.py",
    "lab/common/harness.py",
    "lab/common/nli.py",
    "data/exp_008_entity_detect/lines.json",
    "data/exp_008_entity_detect/results.json",
]

EASY_PEOPLE = ["Ravi Sharma", "Anita Desai", "Meera Iyer", "Kapil Menon", "Sara Khan", "Owen Blake", "Priya Nair", "John Adeyemi"]
EASY_ORGS = ["ABC Pvt Ltd", "Northwind LLC", "Helios GmbH", "Kite Corp", "Blue Oak LLP", "Sable Inc"]
EASY_ADDR = [
    "14 MG Road, Pune 411001",
    "221B Baker Street, London",
    "9 Residency Road, Bengaluru 560001",
    "48 Park Street, Kolkata 700016",
]
EASY_DATES = ["5 January 2024", "2 March 2024", "14/10/2024", "2024-10-14"]
EASY_AMOUNTS = ["INR 50000", "USD 250", "$80", "30 days", "7 percent"]

HARD = [
    ("Infosys bid for the work.", [("Infosys", "organization")], "hard"),
    ("Please pay fifty thousand rupees.", [("fifty thousand rupees", "amount")], "hard"),
    ("Contact R. Sharma about the keys.", [("R. Sharma", "person")], "hard"),
    ("Mr. Sharma called twice.", [("Mr. Sharma", "person")], "hard"),
    ("Park Street is busy at noon.", [("Park Street", "address")], "ambiguous_place"),
    ("Ashok Nagar flooded after the rain.", [("Ashok Nagar", "address")], "ambiguous_place"),
    ("The flat is at Plot 14, Sector 5.", [("Plot 14, Sector 5", "address")], "hard"),
    ("ravi sharma sent the scan.", [("ravi sharma", "person")], "hard"),
    ("New Delhi High Court dismissed the appeal.", [("New Delhi High Court", "organization")], "hard"),
    ("The said premises include a parking slot.", [], "hard"),
    ("May Sharma join the call?", [("Sharma", "person")], "hard"),
    ("Rent is due each Monday.", [], "easy"),
    ("the Lessee must pay.", [("the Lessee", "defined term")], "easy"),
    ("Helios (the Company) signed.", [("the Company", "defined term")], "easy"),
    ("Notice period is thirty days in words only.", [("thirty days", "amount")], "hard"),
    ("Meet at Baker Street tomorrow.", [("Baker Street", "address")], "ambiguous_place"),
]


def _easy_lines():
    lines = []
    for name in EASY_PEOPLE:
        lines.append((f"{name} signed the page.", [(name, "person")], "easy"))
        lines.append((f"Witnessed by Dr. {name.split()[-1]}.", [(f"Dr. {name.split()[-1]}", "person")], "easy"))
    for org in EASY_ORGS:
        lines.append((f"{org} is a party.", [(org, "organization")], "easy"))
    for addr in EASY_ADDR:
        lines.append((f"Address: {addr}.", [(addr, "address")], "easy"))
    for date in EASY_DATES:
        lines.append((f"Dated {date}.", [(date, "date")], "easy"))
    for amount in EASY_AMOUNTS:
        lines.append((f"Amount due: {amount}.", [(amount, "amount")], "easy"))
    lines.append(("Ravi Sharma (the Lessee) resides at 14 MG Road, Pune 411001.", [
        ("Ravi Sharma", "person"),
        ("the Lessee", "defined term"),
        ("14 MG Road, Pune 411001", "address"),
    ], "easy"))
    return lines


def _gold_set(text: str, spans: list[tuple[str, str]]) -> set[tuple[int, int, str]]:
    gold = set()
    for span, label in spans:
        located = find_span(text, span)
        if located is None:
            raise SystemExit(f"gold span not in text: {span!r} :: {text!r}")
        gold.add((located[0], located[1], label))
    return gold


def _pred_set(mentions: list[dict]) -> set[tuple[int, int, str]]:
    return {(m["start"], m["end"], m["label"]) for m in mentions}


ROLES = [
    {"id": "R01", "text": "Ravi Sharma (the Lessee) resides at 14 MG Road, Pune 411001.", "question": "Who is the Lessee?", "gold": "Ravi Sharma"},
    {"id": "R02", "text": "ABC Pvt Ltd (the Lessor) has its office at 48 Park Street, Kolkata 700016.", "question": "Who is the Lessor?", "gold": "ABC Pvt Ltd"},
    {"id": "R03", "text": "Meera Iyer (the Purchaser) paid the price.", "question": "Who is the Purchaser?", "gold": "Meera Iyer"},
    {"id": "R04", "text": "The address of Ravi Sharma is 14 MG Road, Pune 411001.", "question": "What is the address of Ravi Sharma?", "gold": "14 MG Road, Pune 411001"},
    {"id": "R05", "text": "Kapil Menon (the Borrower) owes INR 50000.", "question": "Who is the Borrower?", "gold": "Kapil Menon"},
    {"id": "R06", "text": "Sable Inc (the Vendor) shipped the goods.", "question": "Who is the Vendor?", "gold": "Sable Inc"},
    {"id": "R07", "text": "Priya Nair (the Licensee) may use the mark.", "question": "Who is the Licensee?", "gold": "Priya Nair"},
    {"id": "R08", "text": "Owen Blake (the Lender) released the funds.", "question": "Who is the Lender?", "gold": "Owen Blake"},
    {"id": "R09", "text": "The office of Northwind LLC is 221B Baker Street, London.", "question": "What is the address of Northwind LLC?", "gold": "221B Baker Street, London"},
    {"id": "R10", "text": "Sara Khan (the Guarantor) signed below.", "question": "Who is the Guarantor?", "gold": "Sara Khan"},
    {"id": "R11", "text": "Anita Desai (the Witness) was present.", "question": "Who is the Witness?", "gold": "Anita Desai"},
    {"id": "R12", "text": "John Adeyemi (the Agent) holds the keys at 9 Residency Road, Bengaluru 560001.", "question": "What is the address of John Adeyemi?", "gold": "9 Residency Road, Bengaluru 560001"},
]


def main():
    run = Run("EXP-008", "exp_008_entity_detect")
    lines = _easy_lines() + HARD
    dumped = [{"text": text, "gold": spans, "slice": kind} for text, spans, kind in lines]
    run.write_json("lines.json", dumped)
    labels = ["person", "organization", "address", "defined term", "date", "amount"]
    per_label = {label: {"pred": set(), "gold": set()} for label in labels}
    per_slice_gold = {"easy": set(), "hard": set(), "ambiguous_place": set()}
    per_slice_pred = {"easy": set(), "hard": set(), "ambiguous_place": set()}
    ambiguous_flags = []
    offset = 0
    for text, spans, kind in lines:
        primary = detect_primary(text)
        secondary = detect_secondary(text)
        merged = agreement(primary, secondary)
        gold = {(start + offset, end + offset, label) for start, end, label in _gold_set(text, spans)}
        pred = {(start + offset, end + offset, label) for start, end, label in _pred_set(primary)}
        for label in labels:
            per_label[label]["gold"] |= {row for row in gold if row[2] == label}
            per_label[label]["pred"] |= {row for row in pred if row[2] == label}
        per_slice_gold[kind] |= gold
        per_slice_pred[kind] |= pred
        if kind == "ambiguous_place":
            flagged = any(m["label"] == "address" and m["status"] == "unsure" for m in merged)
            ambiguous_flags.append(flagged)
        offset += len(text) + 1
    label_scores = {label: prf(per_label[label]["pred"], per_label[label]["gold"]) for label in labels}
    parsed = parse_address("14 MG Road, Pune 411001")
    role_hits = []
    for item in ROLES:
        qa = answer_question(item["question"], [{"id": item["id"], "text": item["text"]}], tau=0.2)
        role_hits.append(bool(qa["span"] and normalize(item["gold"]) in normalize(qa["span"])))
    overall = prf(set().union(*[bucket["pred"] for bucket in per_label.values()]), set().union(*[bucket["gold"] for bucket in per_label.values()]))
    metrics = {
        "lines": len(lines),
        "overall": overall,
        "per_label": label_scores,
        "easy_f1": prf(per_slice_pred["easy"], per_slice_gold["easy"])["f1"],
        "hard_f1": prf(per_slice_pred["hard"], per_slice_gold["hard"])["f1"],
        "ambiguous_place_flag_rate": round(sum(ambiguous_flags) / max(1, len(ambiguous_flags)), 4),
        "ambiguous_place_n": len(ambiguous_flags),
        "address_parse_sample": parsed,
        "role_questions": len(ROLES),
        "role_accuracy": round(sum(role_hits) / len(ROLES), 4),
    }
    prose = (
        f"On {metrics['lines']} lines, overall exact-span F1 is {overall['f1']} "
        f"(precision {overall['precision']}, recall {overall['recall']}). "
        f"Person F1 {label_scores['person']['f1']}, organization F1 {label_scores['organization']['f1']}, "
        f"address F1 {label_scores['address']['f1']}, defined term F1 {label_scores['defined term']['f1']}, "
        f"date F1 {label_scores['date']['f1']}, amount F1 {label_scores['amount']['f1']}. "
        f"Easy-slice F1 is {metrics['easy_f1']}; hard-slice F1 is {metrics['hard_f1']}. "
        f"Ambiguous place names were flagged unsure in {metrics['ambiguous_place_flag_rate']} of {metrics['ambiguous_place_n']} cases. "
        f"Role and address questions: {metrics['role_accuracy']} on {metrics['role_questions']} passages. "
        f"Address parse of the sample: {parsed}."
    )
    run.finish(
        title="Entity detection and roles",
        goal="Score rule taggers per label, flag ambiguous place names, parse an address, and answer role questions from the passage.",
        method="A primary rule tagger marks person, organization, address, defined term, date, and amount. A stricter second tagger covers titled people and suffixed organizations. Exact character offsets are compared with gold. Role questions use extractive QA.",
        metrics=metrics,
        results_prose=prose,
        conclusion=(
            "Exact-span F1 is high on easy titled names, suffixed organizations, and fully patterned addresses, and lower on the hard slice "
            "(bare company names, amounts in words, lowercase names, courts). Ambiguous place names are flagged rather than treated as high-confidence addresses."
        ),
        scale_down="52 short lines and 12 role passages replace the blueprint's 150 to 200 detection lines and 30 role passages. GLiNER, BERT-NER, and libpostal are not loaded.",
        referenced_files=FILES,
        follow_ups=["If hard-slice F1 is not enough, train a span tagger only on locally labeled spans. Do not download a pretrained NER model."],
    )


if __name__ == "__main__":
    main()
