"""Coordinate descent over the pipeline configuration.

RES is not published, so the objective hedges: the mean of the word-level and
character-level normalised edit distance to the reference.  Optimising either
one alone can trade off against the other.
"""
import os, sys, json, time, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd
from rrh.cache import load_or_build
from rrh.metrics import evaluate
from rrh.pipeline import Config, ReportGenerator, model_key
from rrh.routing import fit_ranked_router

ROOT = os.path.join(os.path.dirname(__file__), "..")
K = 5

GRID = {
    "cover_threshold": [0.0, 0.05, 0.12, 0.2, 0.3],
    "dedupe_threshold": [0.0, 0.6, 0.7, 0.8, 0.9],
    "min_route_score": [0.2, 0.45, 0.7, 1.0],
    "group_penalty": [0.5, 1.0, 1.6, 2.5],
    "cue_veto_penalty": [0.0, 0.4, 0.8, 1.4],
    "split_margin": [-0.6, -0.3, 0.0, 0.3],
    "w_cue": [2.0, 3.0, 4.5],
    "w_label": [1.4, 2.2, 3.0],
    "w_concept": [0.6, 1.2, 2.0],
    "w_template": [0.5, 1.0, 1.6],
    "w_mined": [0.6, 1.2, 2.0],
    "w_knn": [1.0, 1.6, 2.4],
    "w_continuity": [0.0, 0.3, 0.6],
    "w_backward": [0.5, 1.0, 1.6],
    "summary_threshold": [0.18, 0.23, 0.28],
    "summary_max_misses": [2, 3, 4],
    "findings_cap": [1, 2, 3],
    "summary_cap": [0, 6, 8],
    "findings_require_abnormal": [True, False],
    "trim_detail": [True, False],
    "drop_negative_impression": [True, False],
    "number_impression": [True, False],
    "abnormal_first": [True, False],
    "normalize_shorthand": [True, False],
    "correct_spelling": [True, False],
    "merge_extras": [True, False],
    "summary_after_cues": [True, False],
    "impression_dedupe": [0.7, 0.82, 0.95],
    "soften_blanket": [True, False],
    "suppress_redundant_negatives": [True, False],
    "append_template_impression": [True, False],
    "blank_between_fields": [True, False],
    "cue_match_min": [0.25, 0.34, 0.45],
}


def score(rows, refs, cfg):
    folds = [rows[i::K] for i in range(K)]
    models = load_or_build(
        os.path.join(ROOT, "artifacts"),
        lambda: [fit_ranked_router([r for j in range(K) if j != f for r in folds[j]], cfg)
                 for f in range(K)],
        key=model_key(cfg))
    preds, gold = [], []
    for f in range(K):
        gen = ReportGenerator(models[f], cfg)
        for r in folds[f]:
            preds.append(gen.generate(r)[0])
            gold.append(r["report"])
    sc = evaluate(preds, gold)
    return (sc.res_word + sc.res_char) / 2, sc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--out", default=os.path.join(ROOT, "artifacts", "best_config.json"))
    args = ap.parse_args()
    tr = pd.read_csv(os.path.join(ROOT, "data", "train.csv"))
    rows, refs = tr.to_dict("records"), tr.report.tolist()
    best = json.load(open(args.out))
    best_obj, sc = score(rows, refs, Config(**best))
    print(f"start  obj={best_obj:.5f}  {sc.as_row()}", flush=True)

    for rnd in range(args.rounds):
        improved = False
        for param, values in GRID.items():
            cur = best.get(param, getattr(Config(), param))
            for v in values:
                if v == cur:
                    continue
                trial = {**best, param: v}
                t0 = time.time()
                obj, sc = score(rows, refs, Config(**trial))
                tag = ""
                if obj < best_obj - 1e-6:
                    best, best_obj, cur, improved = trial, obj, v, True
                    tag = "  <-- keep"
                print(f"  r{rnd} {param}={v!r:>8} obj={obj:.5f} word={sc.res_word:.4f} "
                      f"char={sc.res_char:.4f} [{time.time()-t0:.0f}s]{tag}", flush=True)
            json.dump(best, open(args.out, "w"), indent=2, sort_keys=True)
        print(f"round {rnd} done: obj={best_obj:.5f}", flush=True)
        if not improved:
            break
    obj, sc = score(rows, refs, Config(**best))
    print(f"\nFINAL obj={obj:.5f}  {sc.as_row()}")
    print(json.dumps(best, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
