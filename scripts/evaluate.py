import os, sys, json, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd
from rrh.metrics import evaluate
from rrh.pipeline import Config, build_generator

ROOT = os.path.join(os.path.dirname(__file__), "..")


def cv_predict(rows, cfg, k=5):
    folds = [rows[i::k] for i in range(k)]
    preds = [None] * len(rows)
    index = {id(r): i for i, r in enumerate(rows)}
    for f in range(k):
        train = [r for j in range(k) if j != f for r in folds[j]]
        gen = build_generator(train, cfg)
        for r in folds[f]:
            preds[index[id(r)]] = gen.generate(r)[0]
    return preds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--overrides", default="{}")
    ap.add_argument("--name", default="pipeline")
    args = ap.parse_args()
    tr = pd.read_csv(os.path.join(ROOT, "data", "train.csv"))
    rows = tr.to_dict("records")
    cfg = Config(**json.loads(args.overrides))
    preds = cv_predict(rows, cfg)
    score = evaluate(preds, tr.report.tolist())
    print(f"{args.name:34s} {score.as_row()}")


if __name__ == "__main__":
    main()
