"""Generate the Kaggle notebook from the package source.

The notebook is self-contained: it writes each pipeline module to disk with
%%writefile, then imports and runs it.  Keeping it generated guarantees the
notebook and the repository never drift apart.
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src", "rrh")
OUT = os.path.join(ROOT, "notebooks", "radiology-reporting-harness.ipynb")

MODULES = [
    "textutil", "lexicon", "template", "dictation", "splitting",
    "routing", "editor", "impression", "pipeline", "validate", "metrics",
]


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text.splitlines(keepends=True),
    }


def module_cell(name: str) -> dict:
    with open(os.path.join(SRC, f"{name}.py"), encoding="utf-8") as fh:
        body = fh.read()
    return code(f"%%writefile rrh/{name}.py\n{body}")


INTRO = """# Radiology Reporting Harness - minimal template editing pipeline

**Task.** Turn a telegraphic radiologist dictation into a complete structured
report by *minimally editing* the supplied normal template. The leaderboard
metric (RES, lower is better) rewards template-edit fidelity, not free-form
report writing.

**Approach - structured generation (Approach B/D), fully deterministic.**

```
dictation
   |-- segment .......... sentences, "Bones shows ..." cues, technique/history
   |                      boilerplate, and the dictated summary block
   |-- normalise ........ shorthand expansion + corpus-based spell repair
   |-- split ............ "No acute fracture or dislocation" -> two clauses
   |-- route ............ cue > field label > curated anatomy > template text
   |                      overlap > statistics mined from train reports
   |-- edit template .... replace only the contradicted normal statement,
   |                      keep every untouched field byte-identical
   |-- impression ....... reuse the dictated summary, else condense the
   |                      abnormal findings and close with the template line
   |-- validate ......... negation / laterality / measurements / no invented
                          content / untouched fields / no dropped findings
```

Everything runs offline with the standard library (plus pandas and an optional
rapidfuzz accelerator). **No API keys are used anywhere in this notebook**; an
optional LLM refinement hook is included at the end and is disabled unless an
API key is supplied through an environment variable / Kaggle Secret.

Re-running this notebook top to bottom regenerates `submission.csv` exactly -
no per-case manual editing anywhere in the pipeline.
"""

SETUP = """import os, sys, json, csv, subprocess

INPUT_DIR = "/kaggle/input/radiology-reporting-harness"
if not os.path.isdir(INPUT_DIR):
    # local / repository checkout fallback
    for cand in ("data", "../data", "/kaggle/input"):
        if os.path.isdir(cand) and os.path.exists(os.path.join(cand, "train.csv")):
            INPUT_DIR = cand
            break
        if os.path.isdir(cand):
            for sub in sorted(os.listdir(cand)):
                p = os.path.join(cand, sub)
                if os.path.isdir(p) and os.path.exists(os.path.join(p, "train.csv")):
                    INPUT_DIR = p
                    break
print("input dir:", INPUT_DIR, os.listdir(INPUT_DIR)[:8])

WORK = "/kaggle/working" if os.path.isdir("/kaggle/working") else "."
os.chdir(WORK)
os.makedirs("rrh", exist_ok=True)
open(os.path.join("rrh", "__init__.py"), "w").close()
sys.path.insert(0, os.getcwd())

try:
    import rapidfuzz  # noqa: F401
    print("rapidfuzz available")
except ImportError:
    print("rapidfuzz not available - the pure-python fallback is used (slower, identical output)")
"""

RUN = '''import importlib
import pandas as pd

for m in ["textutil", "lexicon", "template", "dictation", "splitting", "routing",
          "editor", "impression", "pipeline", "validate", "metrics"]:
    importlib.import_module(f"rrh.{m}")
    importlib.reload(sys.modules[f"rrh.{m}"])

from rrh.pipeline import Config, ReportGenerator
from rrh.routing import fit_router
from rrh.validate import validate

train = pd.read_csv(os.path.join(INPUT_DIR, "train.csv"))
test = pd.read_csv(os.path.join(INPUT_DIR, "test.csv"))
sample = pd.read_csv(os.path.join(INPUT_DIR, "sample_submission.csv"))
print(train.shape, test.shape, sample.shape)

CONFIG = json.loads("""
__CONFIG__
""")
cfg = Config(**CONFIG)
generator = ReportGenerator(fit_router(train.to_dict("records")), cfg)
print(json.dumps(CONFIG, indent=2, sort_keys=True))
'''

EVAL = '''from rrh.metrics import evaluate
from rrh.pipeline import ReportGenerator

# Honest cross-validation: the routing statistics are re-mined per fold so no
# fold ever sees its own reference report.
K = 5
rows = train.to_dict("records")
folds = [rows[i::K] for i in range(K)]
preds, gold = [], []
for f in range(K):
    tr_rows = [r for j in range(K) if j != f for r in folds[j]]
    g = ReportGenerator(fit_router(tr_rows), cfg)
    for r in folds[f]:
        preds.append(g.generate(r)[0])
        gold.append(r["report"])

from rrh.template import parse_template, render_report
baseline = []
for r in rows:
    t = parse_template(r["template_content"])
    baseline.append(render_report([(x.label, x.text) for x in t.fields], t.impression))

print("copy-the-template baseline :", evaluate(baseline, [r["report"] for r in rows]).as_row())
print("structured pipeline (5-CV) :", evaluate(preds, gold).as_row())
'''

PREDICT = '''reports, issue_counts = {}, {}
for row in test.to_dict("records"):
    report, trace = generator.generate(row)
    reports[row["case_id"]] = report.strip()
    for k, v in validate(row, report, trace).counts().items():
        issue_counts[k] = issue_counts.get(k, 0) + v

order = sample["case_id"].tolist()
assert set(order) == set(reports), "case_id set differs from sample_submission"
assert len(order) == len(set(order)) == len(test) == 132, "row count / duplicate check failed"

with open("submission.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh, quoting=csv.QUOTE_ALL, lineterminator="\\n")
    w.writerow(["case_id", "report"])
    for cid in order:
        w.writerow([cid, reports[cid]])

print("submission.csv rows:", len(order))
print("validation issues  :", json.dumps(issue_counts, sort_keys=True) or "none")
print()
print(reports[order[0]])
'''

LLM = '''"""OPTIONAL: LLM refinement pass (disabled by default).

The submitted `submission.csv` is produced by the deterministic pipeline above.
This cell shows how the same pipeline can be run as a hybrid (Approach D):
the deterministic editor proposes the report, and a hosted model is asked only
to *re-word* clauses it already contains - never to add findings.

No API key is stored in this notebook.  It is read from an environment
variable (Kaggle: Add-ons -> Secrets).  With no key present the cell is a
no-op, so the notebook still reproduces the submission exactly.
"""
API_KEY = os.environ.get("ANTHROPIC_API_KEY")  # or a Kaggle Secret of the same name
USE_LLM = bool(API_KEY) and os.environ.get("RRH_USE_LLM") == "1"

SYSTEM_PROMPT = """You are a precision report editor, not a radiologist.
You receive a normal template, a dictation, and a draft report built by editing
that template. Return the draft with wording corrections only.
Rules:
- Never add a finding, diagnosis, measurement or laterality that is not in the dictation.
- Never remove a dictated finding.
- Keep every field label and the field order exactly as in the template.
- Leave fields the dictation does not mention byte-identical to the template.
- Output only FINDINGS: ... IMPRESSION: ..."""

def refine(row, draft):
    if not USE_LLM:
        return draft
    import anthropic
    client = anthropic.Anthropic(api_key=API_KEY)
    msg = client.messages.create(
        model="claude-opus-5",
        max_tokens=2000,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content":
                   f"TEMPLATE:\\n{row['template_content']}\\n\\n"
                   f"DICTATION:\\n{row['dictation']}\\n\\nDRAFT:\\n{draft}"}],
    )
    return msg.content[0].text.strip()

print("LLM refinement enabled:", USE_LLM)
'''


def main() -> None:
    cfg_path = os.path.join(ROOT, "artifacts", "best_config.json")
    config = json.load(open(cfg_path)) if os.path.exists(cfg_path) else {}
    cells = [
        md(INTRO),
        md("## 1. Environment and data"),
        code(SETUP),
        md(
            "## 2. The pipeline\n\n"
            "Each cell below writes one module of the `rrh` package, so the whole "
            "implementation is visible in the notebook *and* importable by it."
        ),
    ]
    headings = {
        "textutil": "### 2.1 Text utilities - sentence splitting, similarity, edit distance",
        "lexicon": "### 2.2 Radiology lexicon - anatomy->field concepts, shorthand, spell repair",
        "template": "### 2.3 Template parsing and report rendering",
        "dictation": "### 2.4 Dictation segmentation - cues, boilerplate, dictated summary",
        "splitting": "### 2.5 Coordinated-clause splitting",
        "routing": "### 2.6 Field routing (mined from the training reports)",
        "editor": "### 2.7 Template editing - replace only what is contradicted",
        "impression": "### 2.8 Impression builder",
        "pipeline": "### 2.9 End-to-end pipeline",
        "validate": "### 2.10 Validation - negation, laterality, measurements, hallucination",
        "metrics": "### 2.11 Offline scoring (RES proxies)",
    }
    for name in MODULES:
        cells.append(md(headings[name]))
        cells.append(module_cell(name))
    cells += [
        md("## 3. Fit the routing model on the training set"),
        code(RUN.replace("__CONFIG__", json.dumps(config, indent=2, sort_keys=True))),
        md(
            "## 4. Cross-validated offline score\n\n"
            "RES is not published, so we track a family of edit-based proxies "
            "(word/char normalised edit distance to the reference, plus field-level "
            "fidelity, content recall and precision). Lower is better."
        ),
        code(EVAL),
        md("## 5. Generate `submission.csv`"),
        code(PREDICT),
        md("## 6. Optional hybrid LLM pass (off by default, no keys in the notebook)"),
        code(LLM),
    ]
    nb = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(nb, fh, indent=1)
        fh.write("\n")
    print("wrote", OUT, f"({len(cells)} cells)")


if __name__ == "__main__":
    main()
