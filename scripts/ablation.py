"""One-at-a-time ablation of the tuned configuration (5-fold CV)."""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd
from rrh.cache import load_or_build
from rrh.metrics import evaluate
from rrh.pipeline import Config, ReportGenerator
from rrh.routing import fit_router
from rrh.template import parse_template, render_report

ROOT = os.path.join(os.path.dirname(__file__), "..")
K = 5


ABLATIONS = [
    ("full pipeline", {}),
    ("- coordinated-clause splitting", {"allow_splitting": False}),
    ("- abnormal findings first in a field", {"abnormal_first": False}),
    ("- within-field de-duplication", {"dedupe_threshold": 0.0}),
    ("- shorthand expansion", {"normalize_shorthand": False}),
    ("- corpus spell repair", {"correct_spelling": False}),
    ("- cue-mismatch penalty", {"cue_veto_penalty": 0.0}),
    ("- trailing paragraph for unroutable findings", {"keep_unrouted": False}),
    ("- dictated-summary reuse (impression)", {"summary_cap": 1}),
    ("- detail trimming (impression)", {"trim_detail": False}),
    ("- drop negatives from impression", {"drop_negative_impression": False}),
    ("- template closing line (impression)", {"append_template_impression": False}),
    ("- numbered impression", {"number_impression": False}),
    ("- blank line between fields", {"blank_between_fields": False}),
    ("+ existential framing (rejected)", {"add_existential": True}),
    ("+ 'is present' framing (rejected)", {"add_copula": True}),
    ("+ soften blanket normals (rejected)", {"soften_blanket": True}),
    ("+ reference-phrasing transfer (rejected)", {"style_threshold": 0.8}),
    ("+ suppress redundant negatives (rejected)", {"suppress_redundant_negatives": True}),
    ("+ severity-ranked impression (rejected)", {"rank_impression_by_severity": True}),
    ("+ recover summary into findings (rejected)", {"recover_summary": True}),
]


def main() -> None:
    tr = pd.read_csv(os.path.join(ROOT, "data", "train.csv"))
    rows = tr.to_dict("records")
    folds = [rows[i::K] for i in range(K)]
    models = load_or_build(
        os.path.join(ROOT, "artifacts"),
        lambda: [
            fit_router([r for j in range(K) if j != f for r in folds[j]]) for f in range(K)
        ],
    )
    base = json.load(open(os.path.join(ROOT, "artifacts", "best_config.json")))

    tmpl_preds, gold_all = [], []
    for f in range(K):
        for r in folds[f]:
            t = parse_template(r["template_content"])
            tmpl_preds.append(render_report([(x.label, x.text) for x in t.fields], t.impression))
            gold_all.append(r["report"])
    results = [("copy the template unchanged", evaluate(tmpl_preds, gold_all))]

    for name, over in ABLATIONS:
        cfg = Config(**{**base, **over})
        preds, gold = [], []
        for f in range(K):
            gen = ReportGenerator(models[f], cfg)
            for r in folds[f]:
                preds.append(gen.generate(r)[0])
                gold.append(r["report"])
        results.append((name, evaluate(preds, gold)))

    print(f"| {'variant':46s} | RES_word | RES_char | RES_raw | FINDINGS | IMPRESSION | cRecall |")
    print(f"|{'-'*48}|---------:|---------:|--------:|---------:|-----------:|--------:|")
    for name, sc in results:
        print(
            f"| {name:46s} | {sc.res_word:8.4f} | {sc.res_char:8.4f} | {sc.res_raw:7.4f} | "
            f"{sc.findings_res:8.4f} | {sc.impression_res:10.4f} | {sc.content_recall:7.3f} |"
        )


if __name__ == "__main__":
    main()
