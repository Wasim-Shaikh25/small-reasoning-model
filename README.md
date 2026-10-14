# Evidence-grounded reasoning POC

A CPU-first proof of concept of the system in [ARCHITECTURE.md](ARCHITECTURE.md). Answers are spans, labels, and citations. The controller abstains when the evidence is missing or in conflict.

Generative language models are not used. Read [FORBIDDEN.md](FORBIDDEN.md) before adding code. Contributors follow [AGENT.md](AGENT.md). The aim is in [OBJECTIVE.md](OBJECTIVE.md). Measurements live in [EXPLORATIONS.md](EXPLORATIONS.md).

```bash
python3 -m pip install -r requirements.txt
python3 lab/run_all.py
python3 lab/render_explorations.py
```

Datasets are under `data/exp_NNN_slug/`. Methods are under `lab/exp_NNN_slug/` and `lab/common/`.

## Real-model reruns (EXP-025, EXP-029, EXP-032, EXP-033)

Most explorations above run on synthetic lease fixtures with classical substitutes
(TF-IDF, rule taggers) for the models ARCHITECTURE.md names. EXP-025, EXP-029,
EXP-032, and EXP-033 instead fetch a real, public document collection and load
real pretrained, non-generative models over it: see
[`lab/common/real_models.py`](lab/common/real_models.py) for exactly which
models and why they are not the blueprint's bge/DeBERTa/GLiNER (huggingface.co
is blocked by this sandbox's egress policy).

```bash
python3 -m spacy download en_core_web_sm
python3 -m spacy download en_core_web_md
python3 lab/exp_025_real_documents/run.py   # fetches real Reuters documents, run this first
python3 lab/exp_029_real_retrieval/run.py
python3 lab/exp_033_real_entities/run.py
python3 lab/exp_032_real_multihop/run.py    # multi-document, multi-hop reasoning chain
```

EXP-025 fetches the real document collection once and writes it to
`data/exp_025_real_documents/`; the other three load it from there, so run
EXP-025 first (`lab/run_all.py` already does this, since it runs
alphabetically).
