"""Which impression variant wins, and can a simple rule tell in advance?"""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd
from rrh.cache import load_or_build
from rrh.dictation import segment_dictation
from rrh.impression import build_impression, is_abnormal
from rrh.metrics import res_word, split_parts
from rrh.pipeline import Config, infer_laterality, infer_region, model_key
from rrh.routing import fit_ranked_router
from rrh.template import parse_template, resolve_placeholders
from rrh.textutil import content_tokens

ROOT = os.path.join(os.path.dirname(__file__), "..")
K = 5
cfg = Config(**json.load(open(os.path.join(ROOT, "artifacts", "best_config.json"))))
tr = pd.read_csv(os.path.join(ROOT, "data", "train.csv"))
rows = tr.to_dict("records")
folds = [rows[i::K] for i in range(K)]
models = load_or_build(
    os.path.join(ROOT, "artifacts"),
    lambda: [fit_ranked_router([r for j in range(K) if j != f for r in folds[j]], cfg)
             for f in range(K)],
    key=model_key(cfg))

recs = []
for f in range(K):
    for row in folds[f]:
        tmpl = parse_template(row["template_content"])
        doc = segment_dictation(row["dictation"], vocab=models[f].vocab,
                                summary_threshold=cfg.summary_threshold,
                                summary_max_misses=cfg.summary_max_misses)
        lat, reg = infer_laterality(row), infer_region(row)
        _, ri = split_parts(row["report"])
        summary = [s.text for s in doc.impression]
        findings = [s.text for s in doc.findings]
        variants = {
            "template": [resolve_placeholders(x, lat, reg) for x in tmpl.impression],
            "summary": build_impression(summary, [], tmpl.impression, lat, reg, cfg),
            "findings": build_impression([], findings, tmpl.impression, lat, reg, cfg),
        }
        scores = {k: res_word("\n".join(v), ri) for k, v in variants.items()}
        best = min(scores, key=scores.get)
        n_abn = sum(1 for x in findings if is_abnormal(x))
        recs.append(dict(
            best=best, has_summary=bool(summary), n_summary=len(summary), n_abn=n_abn,
            n_find=len(findings),
            sum_tokens=sum(len(content_tokens(x)) for x in summary),
            find_tokens=sum(len(content_tokens(x)) for x in findings),
            tmpl_neg=bool(tmpl.impression) and tmpl.impression[0].lower().startswith(("no ", "without")),
            **{f"s_{k}": v for k, v in scores.items()},
        ))
df = pd.DataFrame(recs)
print("oracle mean:", df[["s_template", "s_summary", "s_findings"]].min(axis=1).mean().round(4))
print("current rule (summary if present else findings):",
      df.apply(lambda r: r.s_summary if r.has_summary else r.s_findings, axis=1).mean().round(4))
print()
print(df.groupby(["has_summary", "best"]).size())
print()
sub = df[df.has_summary]
print("WITH summary: summary=%.4f findings=%.4f template=%.4f  n=%d"
      % (sub.s_summary.mean(), sub.s_findings.mean(), sub.s_template.mean(), len(sub)))
sub2 = df[~df.has_summary]
print("NO   summary: summary=%.4f findings=%.4f template=%.4f  n=%d"
      % (sub2.s_summary.mean(), sub2.s_findings.mean(), sub2.s_template.mean(), len(sub2)))
print()
for thr in (0, 1, 2, 3, 4, 6, 8):
    rule = df.apply(
        lambda r: r.s_summary if (r.has_summary and r.n_summary >= thr) else r.s_findings, axis=1)
    print(f"  use summary only when n_summary >= {thr}: {rule.mean():.4f}")
print()
for thr in (0.0, 0.4, 0.7, 1.0, 1.5):
    rule = df.apply(
        lambda r: r.s_summary
        if (r.has_summary and r.sum_tokens >= thr * max(1, r.find_tokens))
        else r.s_findings, axis=1)
    print(f"  use summary only when sum_tokens >= {thr}*find_tokens: {rule.mean():.4f}")
print()
for thr in (0, 1, 2, 3):
    rule = df.apply(
        lambda r: r.s_template if r.n_abn <= thr and not r.has_summary
        else (r.s_summary if r.has_summary else r.s_findings), axis=1)
    print(f"  template when n_abn <= {thr} and no summary: {rule.mean():.4f}")
