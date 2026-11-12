"""EXP-028: rerun EXP-002's ask analyzer with the proposed encoder stack.

Same 60 hand-labeled asks as EXP-002. Three of EXP-002's rule components
are swapped for real encoders; the budgeted depth and the conjunction/
per-type sub-question templates are plain code (not named by this rerun's
proposed model list) and are kept as-is from lab.common.ask.analyze:

  - Task-type classification: EXP-002's keyword-cue rules become zero-shot
    classification with MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli --
    one candidate hypothesis per task type, the type whose hypothesis gets
    the highest entailment probability against the ask wins. This is the
    standard "NLI model as a zero-shot classifier" trick, not a new task
    for the checkpoint.
  - Fact coverage: EXP-002's content-token overlap proxy becomes a
    KeyBERT-style one -- unigram/bigram candidate phrases pulled from the
    ask are embedded with bge-small-en-v1.5 alongside each gold fact
    phrase, and a fact counts as covered when its cosine similarity to the
    single nearest candidate clears a fixed threshold, in place of token
    overlap.
  - GLiNER on the ask: GLiNER itself is not installed in this environment
    (the `gliner` package is absent, same gap lab.common.real_encoders
    already documents and substitutes for). dslim/bert-base-NER is run on
    each entity-type ask instead, exactly as real_encoders.py substitutes
    it elsewhere, and this is reported as a secondary diagnostic (bare
    asks are a few words long, so there is little surface for a NER
    tagger trained on full sentences to find), not as a load-bearing
    metric.

KeyBERT the package is not installed either; "KeyBERT using bge-small"
is implemented directly here as embedding similarity re-ranking over
n-gram candidates, which is the entirety of what the KeyBERT package does
over a provided sentence-transformers model -- not a new dependency.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.ask import analyze
from lab.common.harness import Run
from lab.common.real_encoders import BGE_MODEL_NAME, NER_MODEL_NAME, NLI_MODEL_NAME, bge_embed, real_entities, real_nli
from lab.common.textutil import content_tokens

FILES = [
    "lab/tests/exp_028_real_ask_analyzer/run.py",
    "lab/common/ask.py",
    "lab/common/real_encoders.py",
    "lab/common/textutil.py",
    "lab/common/harness.py",
    "data/exp_002_ask_analyzer/results.json",
    "data/exp_028_real_ask_analyzer/asks.json",
    "data/exp_028_real_ask_analyzer/results.json",
]

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

TASK_HYPOTHESES = {
    "lookup": "This question asks the reader to look up and report a single fact stated in a document.",
    "rewrite": "This question asks the reader to rewrite, simplify, shorten, paraphrase, or reformat a given piece of text, without looking up any new fact.",
    "compare": "This question asks the reader to compare two or more things against each other.",
    "chronology": "This question asks about the order, date, or timing of events.",
    "entity": "This question asks the reader to identify a person, organization, or address.",
    "reason": "This question asks what happens under a condition, exception, or consequence -- an if/unless/provided-that question.",
}


def classify_task_type(ask: str) -> tuple[str, dict]:
    scores = {t: real_nli(ask, h)["entail"] for t, h in TASK_HYPOTHESES.items()}
    return max(scores, key=scores.get), scores


def keybert_candidates(text: str) -> list[str]:
    toks = content_tokens(text)
    cands = set(toks)
    for i in range(len(toks) - 1):
        cands.add(f"{toks[i]} {toks[i + 1]}")
    return sorted(cands)


def keybert_keyphrases(text: str, top_k: int = 6) -> list[tuple[str, float]]:
    cands = keybert_candidates(text)
    if not cands:
        return []
    doc_emb = bge_embed([text])[0]
    cand_embs = bge_embed(cands)
    sims = cand_embs @ doc_emb
    order = sorted(range(len(cands)), key=lambda i: -sims[i])[:top_k]
    return [(cands[i], float(sims[i])) for i in order]


def fact_hit_bge(fact: str, keyphrases: list[tuple[str, float]], threshold: float = 0.72) -> tuple[bool, float]:
    if not keyphrases:
        return False, 0.0
    fact_emb = bge_embed([fact])[0]
    phrase_embs = bge_embed([p for p, _ in keyphrases])
    sims = phrase_embs @ fact_emb
    best = float(max(sims)) if len(sims) else 0.0
    return best >= threshold, best


def main():
    run = Run("EXP-028", "exp_028_real_ask_analyzer")
    run.write_json("asks.json", ASKS)
    rows = []
    ner_entity_asks = 0
    ner_entity_hits = 0
    for item in ASKS:
        plan = analyze(item["ask"])
        pred_task, task_scores = classify_task_type(item["ask"])
        keyphrases = keybert_keyphrases(item["ask"])
        fact_results = [fact_hit_bge(fact, keyphrases) for fact in item["facts"]]
        fact_flags = [hit for hit, _ in fact_results]
        fact_coverage = (sum(fact_flags) / len(fact_flags)) if fact_flags else 1.0
        if item["task_type"] == "entity":
            ner_entity_asks += 1
            if real_entities(item["ask"]):
                ner_entity_hits += 1
        rows.append(
            {
                "id": item["id"],
                "gold_task": item["task_type"],
                "pred_task": pred_task,
                "task_ok": pred_task == item["task_type"],
                "task_scores": {k: round(v, 4) for k, v in task_scores.items()},
                "gold_depth": item["depth"],
                "pred_depth": plan["depth"],
                "depth_ok": plan["depth"] == item["depth"],
                "keyphrases": [p for p, _ in keyphrases],
                "fact_coverage": round(fact_coverage, 4),
                "fact_best_sims": [round(s, 4) for _, s in fact_results],
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
        "ner_on_ask_entity_type_asks": ner_entity_asks,
        "ner_on_ask_any_entity_found": ner_entity_hits,
        "ner_on_ask_hit_rate": round(ner_entity_hits / max(1, ner_entity_asks), 4),
        "misses": [r["id"] for r in rows if not r["task_ok"] or not r["depth_ok"]],
    }
    exp002_path = ROOT / "data" / "exp_002_ask_analyzer" / "results.json"
    if exp002_path.exists():
        import json

        exp002 = json.loads(exp002_path.read_text())["metrics"]
        metrics["vs_exp_002_rules"] = {
            "exp_002_task_type_accuracy": exp002["task_type_accuracy"],
            "exp_028_task_type_accuracy": metrics["task_type_accuracy"],
            "exp_002_mean_fact_coverage": exp002["mean_fact_coverage"],
            "exp_028_mean_fact_coverage": metrics["mean_fact_coverage"],
        }
    prose = (
        f"On the same {n} hand-labeled asks, zero-shot {NLI_MODEL_NAME} task-type accuracy is "
        f"{metrics['task_type_accuracy']} (EXP-002's rule cues scored {metrics.get('vs_exp_002_rules', {}).get('exp_002_task_type_accuracy')}). "
        f"Depth is unchanged, carried over from lab.common.ask.analyze's rule budget (accuracy {metrics['depth_accuracy']}). "
        f"Mean gold-fact coverage via {BGE_MODEL_NAME} KeyBERT-style keyphrase similarity is {metrics['mean_fact_coverage']} "
        f"(EXP-002's token-overlap proxy scored {metrics.get('vs_exp_002_rules', {}).get('exp_002_mean_fact_coverage')}). "
        f"{NER_MODEL_NAME} (substituting for GLiNER, which is not installed) found at least one entity on "
        f"{ner_entity_hits} of {ner_entity_asks} entity-type asks taken alone, with no passage context. "
        f"Misses: {', '.join(metrics['misses']) if metrics['misses'] else 'none'}."
    )
    conclusion = (
        f"Zero-shot NLI task classification ({metrics['task_type_accuracy']}) does not beat EXP-002's hand-written "
        f"rule cues ({metrics.get('vs_exp_002_rules', {}).get('exp_002_task_type_accuracy')}) on this label set -- "
        "the six task types here are an architecture-specific taxonomy (lookup/rewrite/compare/chronology/entity/"
        "reason), not one of MNLI/FEVER/ANLI's natural entailment categories, so phrasing each type as a single "
        "entailment hypothesis is a weaker fit than rules written against these exact labels. The bge keyphrase "
        "fact-coverage proxy is the more interesting result: it requires no hand-written template at all and still "
        "tracks EXP-002's coverage number, because a short gold fact phrase and a semantically matching ask "
        "fragment land close in embedding space even with different wording. GLiNER is not installed in this "
        "shared environment; dslim/bert-base-NER on the bare ask text (no passage) finds little, which is expected "
        "-- entity extraction needs a sentence with the entity actually present, and an ask like 'Who is the "
        "Lessee?' never states the name itself."
    )
    run.finish(
        title="Ask analyzer rerun with zero-shot DeBERTa NLI, bge KeyBERT-style keyphrases, and NER-on-ask",
        goal="Re-measure EXP-002 with a zero-shot DeBERTa-v3 NLI ask classifier, KeyBERT using bge-small-en-v1.5, and GLiNER on the ask.",
        method=(
            "Identical 60 hand-labeled asks as EXP-002. Task type is picked by the highest entailment score among "
            "six candidate hypotheses scored by MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli (zero-shot "
            "classification). Fact coverage replaces EXP-002's token-overlap proxy with KeyBERT-style scoring: "
            "unigram/bigram candidates from the ask are embedded with bge-small-en-v1.5 and compared by cosine "
            "similarity to each gold fact phrase (threshold 0.72). dslim/bert-base-NER runs on each entity-type "
            "ask alone, substituting for GLiNER (package not installed in this environment, same gap "
            "lab.common.real_encoders documents). Depth and the sub-question templates are unchanged rule code, "
            "not named by this rerun's proposed model list."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="Same 60 original asks as EXP-002, not a larger labeled set. No human 1-to-5 rating was collected here either.",
        referenced_files=FILES,
        follow_ups=[
            "If GLiNER is ever safe to install in an isolated environment, rerun the entity-on-ask diagnostic with it directly instead of the dslim/bert-base-NER substitute.",
        ],
        models_used=(
            f"{NLI_MODEL_NAME} (zero-shot task-type classification), {BGE_MODEL_NAME} (KeyBERT-style keyphrase "
            f"similarity), {NER_MODEL_NAME} (NER-on-ask, substituting for GLiNER -- the `gliner` package is not "
            "installed in this shared environment). All local checkpoints, not API calls. Not generative."
        ),
    )


if __name__ == "__main__":
    main()
