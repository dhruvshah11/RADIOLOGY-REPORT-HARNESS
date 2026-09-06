"""Headroom analysis: how much is left in routing and in the impression."""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd
from rrh.cache import load_or_build
from rrh.dictation import segment_dictation
from rrh.editor import edit_field
from rrh.impression import build_impression
from rrh.metrics import evaluate, res_word, split_parts
from rrh.pipeline import Config, ReportGenerator, infer_laterality, infer_region
from rrh.routing import fit_router, mine_row
from rrh.template import parse_template, render_report, resolve_placeholders

ROOT = os.path.join(os.path.dirname(__file__), "..")
K = 5
cfg = Config(**json.load(open(os.path.join(ROOT, "artifacts", "best_config.json"))))
tr = pd.read_csv(os.path.join(ROOT, "data", "train.csv"))
rows = tr.to_dict("records")
folds = [rows[i::K] for i in range(K)]
models = load_or_build(os.path.join(ROOT, "artifacts"),
                       lambda: [fit_router([r for j in range(K) if j != f for r in folds[j]])
                                for f in range(K)])

# ---------------------------------------------------------------- routing oracle
preds, oracle_preds, gold = [], [], []
for f in range(K):
    gen = ReportGenerator(models[f], cfg)
    for row in folds[f]:
        preds.append(gen.generate(row)[0])
        gold.append(row["report"])

        tmpl = parse_template(row["template_content"])
        doc = segment_dictation(row["dictation"], vocab=models[f].vocab,
                                summary_threshold=cfg.summary_threshold,
                                summary_max_misses=cfg.summary_max_misses)
        units = doc.findings or doc.impression
        gold_lab = {i: lab for i, _, lab, _ in mine_row(row)}
        routed, ordered = {}, []
        for i, seg in enumerate(units):
            lab = gold_lab.get(i)
            if lab:
                routed.setdefault(lab, []).append(seg.text)
            ordered.append(seg.text)
        lat, reg = infer_laterality(row), infer_region(row)
        fields = []
        for fld in tmpl.fields:
            if fld.is_free:
                fields.append(("", resolve_placeholders(fld.text, lat, reg)))
            elif fld.label == "OTHER FINDINGS":
                fields.append((fld.label, ""))
            else:
                body = edit_field(fld.text, routed.get(fld.label, []), cfg)
                fields.append((fld.label, resolve_placeholders(body, lat, reg)))
        imp = build_impression([s.text for s in doc.impression], ordered, tmpl.impression,
                               lat, reg, cfg)
        oracle_preds.append(render_report(fields, imp, [], cfg.blank_between_fields))

print("pipeline            :", evaluate(preds, gold).as_row())
print("oracle field routing:", evaluate(oracle_preds, gold).as_row())

# ------------------------------------------------------------- impression oracle
cur = orc = 0.0
choice = {"template": 0, "summary": 0, "findings": 0}
for f in range(K):
    gen = ReportGenerator(models[f], cfg)
    for row in folds[f]:
        pred, trace = gen.generate(row)
        _, pi = split_parts(pred)
        _, ri = split_parts(row["report"])
        cur += res_word(pi, ri)
        tmpl = parse_template(row["template_content"])
        doc = segment_dictation(row["dictation"], vocab=gen.model.vocab,
                               summary_threshold=cfg.summary_threshold,
                               summary_max_misses=cfg.summary_max_misses)
        lat, reg = infer_laterality(row), infer_region(row)
        variants = {
            "template": [resolve_placeholders(x, lat, reg) for x in tmpl.impression],
            "summary": build_impression([s.text for s in doc.impression], [], tmpl.impression,
                                        lat, reg, cfg),
            "findings": build_impression([], [s.text for s in doc.findings], tmpl.impression,
                                         lat, reg, cfg),
        }
        best_k, best_v = min(
            ((k, res_word("\n".join(v), ri)) for k, v in variants.items()), key=lambda x: x[1]
        )
        orc += best_v
        choice[best_k] += 1
n = len(rows)
print(f"\nimpression  current={cur/n:.4f}  oracle-choice={orc/n:.4f}   best variant counts={choice}")
