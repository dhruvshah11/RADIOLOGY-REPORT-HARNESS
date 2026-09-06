"""List template sentences the stage-2 reports deleted, for contradiction review.

References keep 57.8% of the template sentences in fields they edit; a deletion
is only correct when the dictation actually contradicts the sentence.
"""
import os, sys, json, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd
from rrh.template import parse_template
from rrh.textutil import sim, split_sentences, squash
from rrh.validate import report_sentences

ROOT = os.path.join(os.path.dirname(__file__), "..")
ap = argparse.ArgumentParser()
ap.add_argument("--split", default="test")
ap.add_argument("--refined", default=os.path.join(ROOT, "artifacts", "llm_refined_test.json"))
a = ap.parse_args()

df = pd.read_csv(os.path.join(ROOT, "data", f"{a.split}.csv")).set_index("case_id")
R = json.load(open(a.refined))

n = 0
for cid, mine in R.items():
    if cid not in df.index:
        continue
    row = df.loc[cid]
    tmpl = parse_template(row["template_content"])
    mine_fields = {f.label: f.text for f in parse_template(mine).fields if f.label}
    rs = report_sentences(mine)
    hits = []
    for f in tmpl.fields:
        if not f.label or f.label == "OTHER FINDINGS":
            continue
        for t in split_sentences(f.text):
            t = squash(t)
            if len(t.split()) < 3:
                continue
            if not any(sim(t, x) >= 0.62 for x in rs):
                hits.append((f.label, t))
    if not hits:
        continue
    n += 1
    print("=" * 96)
    print(f"{cid} | {row['modality']} | {row['study_description']}")
    for lab, t in hits:
        print(f"  DROPPED [{lab}] {t}")
        print(f"     mine [{lab}] {mine_fields.get(lab, '<field missing>')[:300]}")
print(f"\n{n} of {len(R)} reports drop at least one template sentence")
