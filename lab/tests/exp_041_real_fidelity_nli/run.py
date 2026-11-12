"""EXP-041: fidelity bidirectional-NLI rerun with the real DeBERTa-v3 MNLI checkpoint.

Re-measures EXP-017's bidirectional-NLI pass rate (the second of its four
fidelity checks, alongside number preservation, added-content, and modal
error) with lab.tests.support.real_bidirectional_nli in place of
lab.tests.support.bidirectional_nli's lexical judge. Number/modal checks
and the deterministic renderer are unchanged -- only the entailment scorer
underneath the bidirectional-NLI check changes. The rewriter stays the
unchanged deterministic copy; FLAN-T5 is not part of this rerun (that is
EXP-048, closed separately, and the generative unit writer stays out of
scope for this one per EXP-046).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.real_encoders import NLI_MODEL_NAME
from lab.common.verify import entity_number_check, modality_preserved
from lab.tests.support import fidelity, real_bidirectional_nli

FILES = [
    "lab/tests/exp_041_real_fidelity_nli/run.py",
    "lab/common/real_encoders.py",
    "lab/common/harness.py",
    "lab/common/verify.py",
    "data/exp_017_fidelity/results.json",
    "data/exp_041_real_fidelity_nli/results.json",
    "lab/tests/support.py",

]

CLAIMS = [
    "The notice period is 30 days.",
    "The security deposit is INR 50000.",
    "Ravi Sharma is the Lessee.",
    "The lease was signed on 5 January 2024.",
    "The tenant shall not sublet unless the Lessor consents.",
    "The rent is INR 25000.",
    "The cure period is 10 days.",
    "ABC Pvt Ltd is the Lessor.",
]
PARAGRAPHS = [
    "The tenant shall pay INR 25000 on the 1st of each month and shall not withhold rent.",
    "Notice of 30 days must be given except where the premises are destroyed.",
    "Meera Iyer signed on 5 January 2024 in the presence of the witness.",
    "The deposit of INR 50000 is held until 14 days after the handover.",
    "Entry is permitted only between 09:00 and 18:00.",
]


def deterministic_render(lines: list[str]) -> str:
    return " ".join(" ".join(line.split()) for line in lines if line.strip())


def main():
    run = Run("EXP-041", "exp_041_real_fidelity_nli")
    both_ways = []
    rows = []
    for claim in CLAIMS:
        out = deterministic_render([claim])
        nli = real_bidirectional_nli(claim, out)
        both_ways.append(nli["ok"])
        rows.append({"source": claim, "output": out, "nli": nli})
    for paragraph in PARAGRAPHS:
        out = deterministic_render([paragraph])
        nli = real_bidirectional_nli(paragraph, out)
        both_ways.append(nli["ok"])
        rows.append({"source": paragraph, "output": out, "nli": nli})
    run.write_json("items.json", rows)

    n = len(both_ways)
    metrics = {
        "model": NLI_MODEL_NAME,
        "renders": n,
        "bidirectional_nli_pass_rate": round(sum(both_ways) / n, 4),
        "generator_used": False,
    }

    exp017_path = ROOT / "data" / "exp_017_fidelity" / "results.json"
    exp017 = json.loads(exp017_path.read_text())["metrics"] if exp017_path.exists() else None
    if exp017:
        metrics["vs_exp_017_lexical_judge"] = {
            "exp_017_bidirectional_nli_pass_rate": exp017["bidirectional_nli_pass_rate"],
            "exp_041_bidirectional_nli_pass_rate": metrics["bidirectional_nli_pass_rate"],
        }

    prose = (
        f"On the same {n} claim and paragraph renders EXP-017 used (restricted to the 'memo' style's identity "
        f"copy, since the renderer does not paraphrase), {NLI_MODEL_NAME} scores bidirectional entailment pass "
        f"rate {metrics['bidirectional_nli_pass_rate']}. "
        + (f"EXP-017's lexical judge scored {exp017['bidirectional_nli_pass_rate']} on a larger, 5-style sweep over the same source text." if exp017 else "")
    )

    run.finish(
        title="Fidelity bidirectional-NLI rerun with the real DeBERTa-v3 MNLI checkpoint",
        goal="Re-measure EXP-017's bidirectional-NLI fidelity check with MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli in place of the lexical judge.",
        method=(
            "The same claims and paragraphs EXP-017 used, run once each through the identity-copy renderer "
            "(whitespace normalization only, no paraphrase -- the renderer does not generate text). "
            "lab.tests.support.real_bidirectional_nli replaces lab.tests.support.bidirectional_nli: "
            "same forward/backward entailment-threshold structure, scored by the real MoritzLaurer/"
            "DeBERTa-v3-base-mnli-fever-anli checkpoint instead of the lexical judge."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=(
            f"The real {NLI_MODEL_NAME} checkpoint is loaded and measured for this fidelity check, not "
            "assumed. The renderer itself is still deterministic copy, not a generative rewriter -- this "
            "rerun only changes which model verifies that the copy preserved meaning, not what produced the "
            "copy."
        ),
        scale_down="13 renders (8 claims, 5 paragraphs), one style each, versus EXP-017's 5-style x 13-item sweep.",
        referenced_files=FILES,
        models_used=(
            f"{NLI_MODEL_NAME}, a local checkpoint loaded with transformers (not an API call). Rewriter role "
            "is out of scope for this rerun; the renderer stays the unchanged deterministic copy."
        ),
    )


if __name__ == "__main__":
    main()
