"""Run every exploration in order. Failures stop the batch."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = sorted((ROOT / "lab").glob("exp_*/run.py"))


def main():
    for script in SCRIPTS:
        print(f"\n=== {script.parent.name} ===", flush=True)
        completed = subprocess.run([sys.executable, str(script)], cwd=ROOT)
        if completed.returncode != 0:
            raise SystemExit(f"{script} failed with {completed.returncode}")


if __name__ == "__main__":
    main()
