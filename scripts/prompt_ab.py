"""Score a scripted stage-2 batch, or A/B two of them, with honest error bars.

    python scripts/prompt_ab.py artifacts/r_v1.json                  # vs the stage-1 draft
    python scripts/prompt_ab.py artifacts/r_v1.json artifacts/r_v2.json   # paired A/B

Only training cases are scored (they are the ones with references).  The paired
A/B is the number to steer by: same cases both sides, so its error bar is far
tighter than either absolute score.
"""
import os, sys, json, argparse, statistics as st
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd
from rrh.metrics import evaluate, res_word
from rrh.pipeline import Config, ReportGenerator
from rrh.routing import fit_ranked_router
from rrh.validate import validate

ROOT = os.path.join(os.path.dirname(__file__), "..")
ap = argparse.ArgumentParser()
ap.add_argument("batch")
ap.add_argument("batch_b", nargs="?")
ap.add_argument("--offset", type=float, default=0.008,
                help="proxy -> real RES bias, measured from two leaderboard readings")
a = ap.parse_args()

train = pd.read_csv(os.path.join(ROOT, "data", "train.csv"))
ti = train.set_index("case_id")
rows = train.to_dict("records")
cfg = Config(**json.load(open(os.path.join(ROOT, "artifacts", "best_config.json"))))
gen = ReportGenerator(fit_ranked_router(rows, cfg), cfg)

A = json.load(open(a.batch))
ids = [c for c in A if c in ti.index]
if not ids:
    sys.exit("no scorable cases: this batch holds no training case_ids")
refs = [ti.loc[c, "report"] for c in ids]
drafts, traces = {}, {}
for c in ids:
    row = ti.loc[c].to_dict(); row["case_id"] = c
    d, t = gen.generate(row); drafts[c], traces[c] = d, t

def block(name, texts):
    s = evaluate(texts, refs)
    return s, f"{name:24s} n={len(ids):4d}  RES_word={s.res_word:.4f}  RES_char={s.res_char:.4f}"

sd, ld = block("stage-1 draft", [drafts[c] for c in ids])
sa, la = block(f"A {os.path.basename(a.batch)}", [A[c] for c in ids])
print(ld); print(la)
per_a = [res_word(A[c], ti.loc[c, "report"]) for c in ids]
se = st.stdev(per_a) / len(ids) ** 0.5
print(f"{'':24s}  SE {se:.4f}   estimated real RES ~ {sa.res_word + a.offset:.4f}")

def paired(diffs, label):
    m = st.mean(diffs)
    sed = st.stdev(diffs) / len(diffs) ** 0.5 if len(diffs) > 1 else 0.0
    if sed == 0.0:
        print(f"{label}: {m:+.4f}  (identical outputs - nothing to compare)")
        return m, sed
    print(f"{label}: {m:+.4f}  SE {sed:.4f}  ({m/sed:+.1f} SE)"
          f"  {'REAL' if abs(m) > 2*sed else 'not significant'}")
    return m, sed

d = [res_word(drafts[c], ti.loc[c, "report"]) - per_a[i] for i, c in enumerate(ids)]
paired(d, "\nA vs stage-1 draft")

if a.batch_b:
    B = json.load(open(a.batch_b))
    both = [c for c in ids if c in B]
    if not both:
        sys.exit("the two batches share no case")
    sb, lb = block(f"B {os.path.basename(a.batch_b)}", [B[c] for c in both])
    print("\n" + lb)
    dd = [res_word(A[c], ti.loc[c, "report"]) - res_word(B[c], ti.loc[c, "report"]) for c in both]
    m, s2 = paired(dd, f"A - B (n={len(both)})")
    if s2:
        print("  ->", "B IS BETTER" if m > 2*s2 else "A IS BETTER" if m < -2*s2 else
              "no significant difference - do not switch on this")

# safety: did the model invent anything?
counts = {}
for c in ids:
    row = ti.loc[c].to_dict(); row["case_id"] = c
    for i in validate(row, A[c], traces[c], vocab=gen.model.vocab).issues:
        if i.kind == "untouched_field":
            continue
        counts[i.kind] = counts.get(i.kind, 0) + 1
print("\nvalidator on batch A:", json.dumps(counts, sort_keys=True) or "clean")
