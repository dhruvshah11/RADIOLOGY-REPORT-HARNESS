import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd
from rrh.dictation import segment_dictation
from rrh.routing import (MIN_SCORE, build_context, fit_router, mine_row, score_segment)
from rrh.template import parse_template

tr = pd.read_csv(os.path.join(os.path.dirname(__file__), "..", "data", "train.csv"))
rows = tr.to_dict("records")
K = 5
folds = [rows[i::K] for i in range(K)]

correct = total = abstain = 0
errs = []
for k in range(K):
    test = folds[k]
    train = [r for j in range(K) if j != k for r in folds[j]]
    model = fit_router(train)
    for row in test:
        gold = {i: lab for i, _, lab, _ in mine_row(row)}
        if not gold:
            continue
        tmpl = parse_template(row["template_content"])
        ctx = build_context(tmpl)
        doc = segment_dictation(row["dictation"])
        units = doc.findings or doc.impression
        for i, seg in enumerate(units):
            if i not in gold:
                continue
            scored = score_segment(seg.text, seg.cue, tmpl, model, ctx)
            pred = scored[0][1] if scored and scored[0][0] >= MIN_SCORE else None
            total += 1
            if pred == gold[i]:
                correct += 1
            else:
                if pred is None:
                    abstain += 1
                if len(errs) < 25:
                    errs.append((row["body_part"], seg.text[:70], gold[i], pred,
                                 round(scored[0][0], 2) if scored else 0))
print(f"routing accuracy: {correct}/{total} = {correct/max(1,total):.3f}   abstained={abstain}")
for e in errs:
    print("  ", e)
