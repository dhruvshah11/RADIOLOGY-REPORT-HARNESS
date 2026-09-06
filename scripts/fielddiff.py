import os, sys, json, argparse, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd
from rrh.cache import load_or_build
from rrh.routing import fit_router
from rrh.metrics import res_word
from rrh.pipeline import Config, ReportGenerator
from rrh.template import parse_template
from rrh.textutil import squash

ROOT = os.path.join(os.path.dirname(__file__), "..")
K = 5
ap = argparse.ArgumentParser()
ap.add_argument("--label", default=None)
ap.add_argument("--n", type=int, default=10)
ap.add_argument("--seed", type=int, default=1)
args = ap.parse_args()

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
        pred, _ = gen.generate(r)
        P = {x.label: squash(x.text) for x in parse_template(pred).fields if x.label}
        R = {x.label: squash(x.text) for x in parse_template(r["report"]).fields if x.label}
        for lab in R:
            if args.label and lab != args.label:
                continue
            s = res_word(P.get(lab, ""), R[lab])
            if s > 0.05:
                items.append((s, lab, r, P.get(lab, ""), R[lab]))
random.Random(args.seed).shuffle(items)
items.sort(key=lambda x: -x[0])
step = max(1, len(items) // args.n)
for s, lab, r, p, g in items[::step][: args.n]:
    print("=" * 100)
    print(f"{lab}  RES={s:.2f}  ({r['modality']} {r['body_part']})")
    print(f"  DICT : {squash(r['dictation'])[:260]}")
    print(f"  TMPL : {squash(parse_template(r['template_content']).by_label(lab).text) if parse_template(r['template_content']).by_label(lab) else '-'}")
    print(f"  PRED : {p}")
    print(f"  REF  : {g}")
