"""Score an LLM-refined batch against the deterministic drafts on the same cases."""
import os, sys, json, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd
from rrh.metrics import evaluate, res_word

ROOT = os.path.join(os.path.dirname(__file__), "..")
ap = argparse.ArgumentParser()
ap.add_argument("--packet", default=os.path.join(ROOT, "artifacts", "llm_packet.json"))
ap.add_argument("--refined", default=os.path.join(ROOT, "artifacts", "llm_refined_train.json"))
ap.add_argument("--per-case", action="store_true")
a = ap.parse_args()

packet = {c["case_id"]: c for c in json.load(open(a.packet))}
refined = json.load(open(a.refined))
train = pd.read_csv(os.path.join(ROOT, "data", "train.csv")).set_index("case_id")

ids = [cid for cid in refined if cid in packet and cid in train.index]
refs = [train.loc[cid, "report"] for cid in ids]
drafts = [packet[cid]["draft"] for cid in ids]
llm = [refined[cid].strip() for cid in ids]

d = evaluate(drafts, refs)
l = evaluate(llm, refs)
print(f"n = {len(ids)} cases\n")
print(f"deterministic  {d.as_row()}")
print(f"LLM pass       {l.as_row()}")
print()
for name, a_, b_ in (("RES_word", d.res_word, l.res_word), ("RES_char", d.res_char, l.res_char),
                     ("RES_sent", d.res_sent, l.res_sent)):
    delta = (b_ - a_) / a_ * 100
    print(f"  {name}: {a_:.4f} -> {b_:.4f}  ({delta:+.1f}%)")

wins = sum(1 for cid, r in zip(ids, refs)
           if res_word(refined[cid], r) < res_word(packet[cid]["draft"], r))
print(f"\nLLM better on {wins}/{len(ids)} cases")
if a.per_case:
    print(f"\n{'case':10s} {'determ':>8} {'llm':>8}  {'delta':>8}")
    rows = []
    for cid, r in zip(ids, refs):
        dw, lw = res_word(packet[cid]["draft"], r), res_word(refined[cid], r)
        rows.append((lw - dw, cid, dw, lw))
    for delta, cid, dw, lw in sorted(rows):
        print(f"{cid[:8]:10s} {dw:8.3f} {lw:8.3f}  {delta:+8.3f}")
