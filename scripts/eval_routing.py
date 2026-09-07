"""Field-routing accuracy against the field each finding occupies in the reference."""
import os, sys, json, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd
from rrh.dictation import segment_dictation
from rrh.pipeline import Config
from rrh.routing import build_context, fit_ranked_router, mine_row, score_segment
from rrh.template import parse_template

ROOT = os.path.join(os.path.dirname(__file__), "..")
ap = argparse.ArgumentParser()
ap.add_argument("--cfg", default=os.path.join(ROOT, "artifacts", "best_config.json"))
ap.add_argument("--errors", type=int, default=0)
ap.add_argument("--override", default="{}")
args = ap.parse_args()

_base = json.load(open(args.cfg)) if os.path.exists(args.cfg) else {}
cfg = Config(**{**_base, **json.loads(args.override)})
weights = {"cue": cfg.w_cue, "label": cfg.w_label, "concept": cfg.w_concept,
           "template": cfg.w_template, "mined": cfg.w_mined, "knn": cfg.w_knn,
           "continuity": cfg.w_continuity, "backward": cfg.w_backward,
           "use_ranker": 1.0 if cfg.use_ranker else 0.0}
tr = pd.read_csv(os.path.join(ROOT, "data", "train.csv"))
rows = tr.to_dict("records")
K = 5
folds = [rows[i::K] for i in range(K)]

correct = total = abstain = 0
errs = []
for k in range(K):
    model = fit_ranked_router([r for j in range(K) if j != k for r in folds[j]], cfg)
    for row in folds[k]:
        gold = {i: lab for i, _, lab, _ in mine_row(row)}
        if not gold:
            continue
        tmpl = parse_template(row["template_content"])
        ctx = build_context(tmpl)
        doc = segment_dictation(row["dictation"], vocab=model.vocab,
                                summary_threshold=cfg.summary_threshold,
                                summary_max_misses=cfg.summary_max_misses)
        units = doc.findings or doc.impression
        order = {f.label: f.order for f in tmpl.fields}
        prev_order = None
        for i, seg in enumerate(units):
            if i not in gold:
                continue
            scored = score_segment(seg.text, seg.cue, tmpl, model, ctx, weights, prev_order)
            pred = scored[0][1] if scored and scored[0][0] >= cfg.min_route_score else None
            total += 1
            prev_order = order.get(gold[i], prev_order)
            if pred == gold[i]:
                correct += 1
            else:
                abstain += pred is None
                if len(errs) < args.errors:
                    errs.append((row["body_part"], seg.text[:70], gold[i], pred))
print(f"routing accuracy: {correct}/{total} = {correct/max(1,total):.4f}   abstained={abstain}")
for e in errs:
    print("  ", e)
