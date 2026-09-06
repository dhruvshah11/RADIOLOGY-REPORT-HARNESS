import os, sys, json, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd
from rrh.cache import load_or_build
from rrh.routing import fit_router
from rrh.metrics import res_word, split_parts
from rrh.pipeline import Config, ReportGenerator
from rrh.textutil import squash

ROOT = os.path.join(os.path.dirname(__file__), "..")
K = 5
ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=8)
ap.add_argument("--band", default="worst")
a = ap.parse_args()
tr = pd.read_csv(os.path.join(ROOT, "data", "train.csv"))
rows = tr.to_dict("records")
models = load_or_build(
    os.path.join(ROOT, "artifacts"),
    lambda: [fit_router([r for j in range(K) if j != f for r in rows[j::K]]) for f in range(K)],
)
cfg = Config(**json.load(open(os.path.join(ROOT, "artifacts", "best_config.json"))))
folds = [rows[i::K] for i in range(K)]
items = []
for f in range(K):
    gen = ReportGenerator(models[f], cfg)
    for r in folds[f]:
        pred, trace = gen.generate(r)
        _, pi = split_parts(pred); _, ri = split_parts(r["report"])
        items.append((res_word(pi, ri), r, pi.strip(), ri.strip(), bool(trace.dictated_impression)))
items.sort(key=lambda x: -x[0])
sel = items[: a.n] if a.band == "worst" else items[len(items)//3 : len(items)//3 + a.n]
print("mean imp RES:", sum(i[0] for i in items)/len(items))
print("with dictated summary:", sum(1 for i in items if i[4]), "/", len(items))
for s, r, p, g, hd in sel:
    print("=" * 100)
    print(f"RES={s:.2f} summary={hd} ({r['modality']} {r['body_part']})")
    print("  DICT:", squash(r["dictation"])[:400])
    print("  PRED:", p.replace("\n", " | ")[:400])
    print("  REF :", g.replace("\n", " | ")[:400])
