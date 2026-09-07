"""Print an LLM-pass work packet: inputs + deterministic draft, no references.

Keeping the reference out of the packet is what makes the A/B comparison in
`scripts/llm_score.py` honest.
"""
import os, sys, json, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd
from rrh.cache import load_or_build
from rrh.pipeline import Config, ReportGenerator, model_key
from rrh.routing import fit_ranked_router

ROOT = os.path.join(os.path.dirname(__file__), "..")
K = 5
ap = argparse.ArgumentParser()
ap.add_argument("--split", default="train")
ap.add_argument("--every", type=int, default=24)
ap.add_argument("--offset", type=int, default=7)
ap.add_argument("--limit", type=int, default=100)
ap.add_argument("--ids", default="")
ap.add_argument("--out", default=os.path.join(ROOT, "artifacts", "llm_packet.json"))
a = ap.parse_args()

cfg = Config(**json.load(open(os.path.join(ROOT, "artifacts", "best_config.json"))))
train = pd.read_csv(os.path.join(ROOT, "data", "train.csv"))
rows_all = train.to_dict("records")

if a.split == "train":
    folds = [rows_all[i::K] for i in range(K)]
    models = load_or_build(
        os.path.join(ROOT, "artifacts"),
        lambda: [fit_ranked_router([r for j in range(K) if j != f for r in folds[j]], cfg)
                 for f in range(K)],
        key=model_key(cfg))
    gens = [ReportGenerator(models[f], cfg) for f in range(K)]
    fold_of = {r["case_id"]: f for f in range(K) for r in folds[f]}
    pool = rows_all
else:
    gen = ReportGenerator(fit_ranked_router(rows_all, cfg), cfg)
    pool = pd.read_csv(os.path.join(ROOT, "data", "test.csv")).to_dict("records")

if a.ids:
    wanted = set(a.ids.split(","))
    sel = [r for r in pool if r["case_id"] in wanted]
else:
    sel = pool[a.offset :: a.every][: a.limit]

packet = []
for r in sel:
    g = gens[fold_of[r["case_id"]]] if a.split == "train" else gen
    draft, _ = g.generate(r)
    packet.append({
        "case_id": r["case_id"],
        "modality": r["modality"],
        "body_part": r["body_part"],
        "study_description": r["study_description"],
        "sex": r["patient_sex"],
        "age": r["patient_age_band"],
        "template": r["template_content"],
        "dictation": r["dictation"],
        "draft": draft.strip(),
    })
json.dump(packet, open(a.out, "w"), indent=1)
print(f"wrote {a.out}: {len(packet)} cases ({a.split})")
