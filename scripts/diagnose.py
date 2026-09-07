"""Show where predictions diverge from the reference, field by field."""
import os, sys, json, argparse
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default="{}")
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--mode", default="worst", choices=["worst", "random", "field"])
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    tr = pd.read_csv(os.path.join(ROOT, "data", "train.csv"))
    rows = tr.to_dict("records")
    models = load_or_build(
        os.path.join(ROOT, "artifacts"),
        lambda: [fit_router([r for j in range(K) if j != f for r in rows[j::K]]) for f in range(K)],
    )
    cfg = Config(**json.loads(args.cfg))
    folds = [rows[i::K] for i in range(K)]
    recs = []
    for f in range(K):
        gen = ReportGenerator(models[f], cfg)
        for r in folds[f]:
            pred, trace = gen.generate(r)
            recs.append((res_word(pred, r["report"]), r, pred, trace))
    if args.mode == "field":
        from collections import Counter
        agg, cnt = Counter(), Counter()
        for s, r, pred, _ in recs:
            P = {f.label: squash(f.text) for f in parse_template(pred).fields if f.label}
            R = {f.label: squash(f.text) for f in parse_template(r["report"]).fields if f.label}
            for lab, txt in R.items():
                agg[lab] += res_word(P.get(lab, ""), txt)
                cnt[lab] += 1
        print(f"{'FIELD':38s} {'n':>4} {'meanRES':>8}")
        for lab, c in cnt.most_common(40):
            print(f"{lab:38s} {c:4d} {agg[lab]/c:8.3f}")
        return
    recs.sort(key=lambda x: -x[0])
    if args.mode == "random":
        import random
        random.Random(args.seed).shuffle(recs)
    for s, r, pred, trace in recs[: args.n]:
        print("=" * 100)
        print(f"RES={s:.3f}  {r['modality']} | {r['body_part']} | {r['study_description']}")
        print("--- DICTATION ---"); print(r["dictation"][:900])
        print("--- TEMPLATE ---"); print(r["template_content"][:900])
        print("--- PRED ---"); print(pred)
        print("--- REF ---"); print(r["report"])


if __name__ == "__main__":
    main()
