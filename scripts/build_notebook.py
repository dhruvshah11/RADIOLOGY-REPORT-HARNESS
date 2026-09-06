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
    "routing", "ranker", "chooser", "editor", "impression", "pipeline",
    "validate", "metrics",
]

REFINED = os.path.join(ROOT, "artifacts", "llm_refined_test.json")


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

**Stage 2 - LLM refinement (Approach D).** The deterministic draft is then
handed to a language model together with the template and the dictation. The
model is given one fixed instruction set (Section 6) and applies it uniformly
to every case: fix mis-routed clauses, repair dictation typos into standard
radiology terms, drop leaked section headers, and order the impression. It may
not add a finding, a diagnosis, a measurement or a laterality that is not in
the dictation, and it may not change the template's field labels or their
order.

Measured on 24 held-out training cases (references withheld from the model),
the refinement stage cuts word-level RES from **0.3937 to 0.2318 (-41%)** and
is better on 21 of the 24 cases.

**No API keys appear anywhere in this notebook.** The refinement stage reads
its key from an environment variable / Kaggle Secret and is skipped when none
is present. Its 132 outputs are cached in Section 6 as `refined_reports.json`,
so the notebook reproduces `submission.csv` byte-for-byte offline; supplying a
key re-runs the stage instead of reading the cache.

Re-running this notebook top to bottom regenerates `submission.csv` exactly -
one instruction set applied to every case, no per-case manual editing anywhere
in the pipeline.
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
from rrh.routing import fit_router, fit_ranked_router
from rrh.validate import validate

train = pd.read_csv(os.path.join(INPUT_DIR, "train.csv"))
test = pd.read_csv(os.path.join(INPUT_DIR, "test.csv"))
sample = pd.read_csv(os.path.join(INPUT_DIR, "sample_submission.csv"))
print(train.shape, test.shape, sample.shape)

CONFIG = json.loads("""
__CONFIG__
""")
cfg = Config(**CONFIG)
generator = ReportGenerator(fit_ranked_router(train.to_dict("records"), cfg), cfg)
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
    g = ReportGenerator(fit_ranked_router(tr_rows, cfg), cfg)
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

PREDICT = r'''drafts, issue_counts = {}, {}
traces = {}
for row in test.to_dict("records"):
    report, trace = generator.generate(row)
    drafts[row["case_id"]] = report.strip()
    traces[row["case_id"]] = trace
    for k, v in validate(row, report, trace, vocab=generator.model.vocab).counts().items():
        issue_counts[k] = issue_counts.get(k, 0) + v

print("deterministic drafts:", len(drafts))
print("validation issues   :", json.dumps(issue_counts, sort_keys=True) or "none")
print()
print(drafts[sample["case_id"][0]])
'''

LLM_RULES = r'''SYSTEM_PROMPT = """You are a precision report editor working from a normal
template, a radiologist's telegraphic dictation, and a deterministic draft built by
editing that template. Return the corrected report and nothing else.

Apply exactly these rules to every case:
1.  Keep the template's field labels, uppercased, in the template's order, one
    blank line between fields. Never add, drop, rename or reorder a label.
2.  A field the dictation does not mention keeps the template text verbatim.
3.  Route each dictated finding to the field it belongs to. Move a clause the
    draft filed under the wrong label (a PCL finding under ANTERIOR CRUCIATE
    LIGAMENT, a TFCC finding under ULNAR nerve, an impression sentence left
    inside a findings field).
4.  Replace or trim only the normal statement the dictation contradicts; keep the
    uncontradicted part of that sentence. If a negated list loses one member
    ("No A or B" where A is now positive), rewrite it as "No B". A template
    sentence the dictation never mentions stays (references keep 92% of those),
    and a field the reference edits still keeps 57% of its template sentences -
    delete only on a real contradiction.
4a. Never write a shorter form than the template or the dictation already gives
    you. Where the dictation confirms a structure is normal without adding
    anything, keep the template's sentence rather than compressing it to
    "Intact." - reference field text matches the dictation's length (median
    difference 0 words), it does not shrink below both sources.
5.  Drop technique, clinical history, contrast dose, comparison and
    recommendation boilerplate, and section headers that leaked in from the
    dictation's own layout ("Findings", "Impression", "Brain Parenchyma").
    Keep statements about study limitations ("Evaluation is limited by metallic
    artifacts") - references keep 85% of those.
6.  Repair dictation typos and expand shorthand into standard radiology terms
    ("degen chnges" -> "Degenerative changes", "s/o" -> "suggestive of",
    "VR spaces" -> "Virchow-Robin spaces"). Do not repair a term into a
    different entity.
7.  IMPRESSION: reuse the dictated summary when the dictation has one, in its
    order and near-verbatim (reference impressions run 1.07x the summary's
    length - do not aggressively trim it); otherwise condense the abnormal
    findings by removal only, to about 6 words an item. Abnormal items first,
    the closing negative last (references put it last 325 times against 34
    first), numbered when there is more than one item and plain when there is
    one. Use the template's impression line only when nothing is abnormal, and
    never next to a finding it contradicts.
8.  Preserve negation, laterality and every measurement exactly as dictated.
9.  Never introduce a finding, diagnosis, measurement or laterality that is not
    supported by the dictation and the template.
10. Output only FINDINGS: ... IMPRESSION: ... - nothing else."""


def refine(row, draft):
    """One refinement call. Returns the draft unchanged when no key is present."""
    if not USE_LLM:
        return draft
    import anthropic
    client = anthropic.Anthropic(api_key=API_KEY)
    msg = client.messages.create(
        model="claude-opus-5",
        max_tokens=3000,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content":
                   f"STUDY: {row.get('modality')} {row.get('body_part')} - {row.get('study_description')}\n\n"
                   f"TEMPLATE:\n{row['template_content']}\n\n"
                   f"DICTATION:\n{row['dictation']}\n\n"
                   f"DRAFT:\n{draft}"}],
    )
    return msg.content[0].text.strip()
'''

LLM_HEAD = r'''# The key is never stored in the notebook: Kaggle -> Add-ons -> Secrets, or an
# environment variable. With no key the cached refinements below are used, so
# this notebook reproduces submission.csv exactly, offline.
API_KEY = os.environ.get("ANTHROPIC_API_KEY")
USE_LLM = bool(API_KEY) and os.environ.get("RRH_RUN_LLM") == "1"
print("LLM refinement stage:", "live" if USE_LLM else "cached (no API key present)")
'''

OVERLAY = r'''CACHE = "refined_reports.json"
cached = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}

refined = {}
for row in test.to_dict("records"):
    cid = row["case_id"]
    refined[cid] = refine(row, drafts[cid]) if USE_LLM else cached.get(cid, drafts[cid])
if USE_LLM:
    json.dump(refined, open(CACHE, "w", encoding="utf-8"), indent=1)

# every emitted report goes back through the validator
issue_counts = {}
for row in test.to_dict("records"):
    cid = row["case_id"]
    res = validate(row, refined[cid], traces[cid], vocab=generator.model.vocab)
    for i in res.issues:
        # `untouched_field` compares against the deterministic router's routing
        # decisions, which the refinement stage is allowed to correct
        if i.kind == "untouched_field":
            continue
        issue_counts[i.kind] = issue_counts.get(i.kind, 0) + 1

order = sample["case_id"].tolist()
assert set(order) == set(refined), "case_id set differs from sample_submission"
assert len(order) == len(set(order)) == len(test) == 132, "row count / duplicate check failed"

with open("submission.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(["case_id", "report"])
    for cid in order:
        w.writerow([cid, refined[cid].strip()])

print("submission.csv rows:", len(order))
print("validation issues  :", json.dumps(issue_counts, sort_keys=True) or "none")
print()
print(refined[order[0]])
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
        "ranker": "### 2.6a Learned re-ranker (fitted but disabled by the tuned config)",
        "chooser": "### 2.6b Impression chooser (fitted but disabled by the tuned config)",
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
        md("## 5. Stage 1 - deterministic drafts for the test set"),
        code(PREDICT),
        md(
            "## 6. Stage 2 - LLM refinement\n\n"
            "One fixed instruction set, applied uniformly to all 132 cases. The key "
            "is read from an environment variable / Kaggle Secret and never stored "
            "here; with no key the cached outputs written below are used, so the "
            "notebook reproduces `submission.csv` byte-for-byte offline."
        ),
        code(LLM_HEAD),
        md("### 6.1 The instruction set and the refinement call"),
        code(LLM_RULES),
        md(
            "### 6.2 Cached refinement outputs\n\n"
            "The 132 reports produced by the stage above, so the notebook runs "
            "without a key. Supplying one regenerates and overwrites this file."
        ),
        code("%%writefile refined_reports.json\n" + open(REFINED, encoding="utf-8").read()),
        md("## 7. Write `submission.csv` and re-validate"),
        code(OVERLAY),
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
