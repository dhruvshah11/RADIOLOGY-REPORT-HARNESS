import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd
from rrh.template import parse_template, render_report
from rrh.metrics import evaluate
from rrh.textutil import tidy_sentence

tr = pd.read_csv(os.path.join(os.path.dirname(__file__), "..", "data", "train.csv"))

def passthrough(row, blank=True):
    T = parse_template(row.template_content)
    return render_report([(f.label, f.text) for f in T.fields], T.impression, blank_between_fields=blank)

def passthrough_plus_dict(row):
    T = parse_template(row.template_content)
    return render_report([(f.label, f.text) for f in T.fields],
                         [tidy_sentence(row.dictation)], blank_between_fields=True)

refs = tr.report.tolist()
for name, fn in [("template passthrough (blank sep)", lambda r: passthrough(r, True)),
                 ("template passthrough (no blank)", lambda r: passthrough(r, False)),
                 ("template + raw dictation impression", passthrough_plus_dict)]:
    preds = [fn(r) for _, r in tr.iterrows()]
    print(f"{name:38s} {evaluate(preds, refs).as_row()}")
