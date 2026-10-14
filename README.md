# Evidence-grounded reasoning POC

A CPU-first proof of concept of the system in [ARCHITECTURE.md](ARCHITECTURE.md). Answers are spans, labels, and citations. The controller abstains when the evidence is missing or in conflict.

Generative language models are not used. Read [FORBIDDEN.md](FORBIDDEN.md) before adding code. Contributors follow [AGENT.md](AGENT.md). The aim is in [OBJECTIVE.md](OBJECTIVE.md). Measurements live in [EXPLORATIONS.md](EXPLORATIONS.md).

```bash
python3 -m pip install -r requirements.txt
python3 lab/run_all.py
python3 lab/render_explorations.py
```

Datasets are under `data/exp_NNN_slug/`. Methods are under `lab/exp_NNN_slug/` and `lab/common/`.
