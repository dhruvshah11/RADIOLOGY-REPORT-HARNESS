"""Cross-validated config sweep with cached per-fold routing models."""
import os, sys, json, itertools, time, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd
from rrh.cache import load_or_build
from rrh.metrics import evaluate
from rrh.pipeline import Config, ReportGenerator
from rrh.routing import fit_router

ROOT = os.path.join(os.path.dirname(__file__), "..")
K = 5


def fold_models(rows):
    folds = [rows[i::K] for i in range(K)]

    def build():
        return [
            fit_router([r for j in range(K) if j != f for r in folds[j]]) for f in range(K)
        ]

    return load_or_build(os.path.join(ROOT, "artifacts"), build)


def cv_score(rows, refs, models, cfg):
    folds = [rows[i::K] for i in range(K)]
    preds, gold = [], []
    for f in range(K):
        gen = ReportGenerator(models[f], cfg)
        for r in folds[f]:
            preds.append(gen.generate(r)[0])
            gold.append(r["report"])
    return evaluate(preds, gold)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", required=True, help="JSON dict of param -> list of values")
    ap.add_argument("--base", default="{}")
    args = ap.parse_args()
    tr = pd.read_csv(os.path.join(ROOT, "data", "train.csv"))
    rows = tr.to_dict("records")
    models = fold_models(rows)
    base = json.loads(args.base)
    grid = json.loads(args.grid)
    keys = list(grid)
    results = []
    for combo in itertools.product(*(grid[k] for k in keys)):
        over = dict(zip(keys, combo))
        cfg = Config(**{**base, **over})
        t0 = time.time()
        sc = cv_score(rows, tr.report.tolist(), models, cfg)
        results.append((sc.res_word, over, sc))
        print(f"word={sc.res_word:.4f} char={sc.res_char:.4f} raw={sc.res_raw:.4f} "
              f"find={sc.findings_res:.4f} imp={sc.impression_res:.4f} "
              f"fx={sc.field_exact:.3f} cRec={sc.content_recall:.3f} | {json.dumps(over)} "
              f"[{time.time()-t0:.0f}s]", flush=True)
    results.sort(key=lambda x: x[0])
    print("\n### TOP 5 ###")
    for r in results[:5]:
        print(f"  {r[0]:.4f}  {json.dumps(r[1])}")
    with open(os.path.join(ROOT, "artifacts", "sweep_last.json"), "w") as fh:
        json.dump([{"res_word": r[0], "cfg": r[1]} for r in results], fh, indent=2)


if __name__ == "__main__":
    main()
