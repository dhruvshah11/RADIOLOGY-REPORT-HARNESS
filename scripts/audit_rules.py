"""Flag every violation of the measured reference conventions in a refined batch.

Each rule cites the statistic from scripts/style_study.py that justifies it.
Output is a per-case work queue ordered by violation count.
"""
import os, sys, re, json, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd
from rrh.dictation import segment_dictation, is_layout_header
from rrh.editor import is_negative
from rrh.impression import is_abnormal
from rrh.template import parse_template
from rrh.textutil import content_tokens, sim, split_sentences, squash
from rrh.lexicon import stem
from rrh.validate import report_sentences

ROOT = os.path.join(os.path.dirname(__file__), "..")
ap = argparse.ArgumentParser()
ap.add_argument("--split", default="test")
ap.add_argument("--refined", default=os.path.join(ROOT, "artifacts", "llm_refined_test.json"))
ap.add_argument("--quiet", action="store_true")
a = ap.parse_args()
df = pd.read_csv(os.path.join(ROOT, "data", f"{a.split}.csv")).set_index("case_id")
R = json.load(open(a.refined))
LIM = re.compile(r"\blimited\b|\bsuboptimal\b|\bdegraded\b|\bincomplete\b", re.I)

def imp_of(rep):
    i = rep.find("IMPRESSION:")
    return rep[i + len("IMPRESSION:"):].strip() if i >= 0 else ""

queue = []
for cid, mine in R.items():
    if cid not in df.index:
        continue
    row = df.loc[cid]
    tmpl = parse_template(row["template_content"])
    mf = {f.label: squash(f.text) for f in parse_template(mine).fields if f.label}
    rs = report_sentences(mine)
    doc = segment_dictation(row["dictation"] or "")
    dsents = [squash(s.text) for s in doc.all_reportable]
    v = []

    for f in tmpl.fields:
        if not f.label or f.label == "OTHER FINDINGS":
            continue
        t_all = squash(f.text)
        m = mf.get(f.label, "")
        # R4: a template sentence the dictation never mentions is kept 92.3% of the time
        for t in split_sentences(f.text):
            t = squash(t)
            if len(t.split()) < 3:
                continue
            if max((sim(t, d) for d in dsents), default=0.0) >= 0.25:
                continue
            tk = {stem(x) for x in content_tokens(t)}
            if not tk or any(len(tk & {stem(y) for y in content_tokens(d)}) / len(tk) > 0.5
                             for d in dsents):
                continue
            if not any(sim(t, x) >= 0.62 for x in rs):
                v.append(("R4 dropped-unmentioned-template", f"[{f.label}] {t}"))
        # R6: reference field text never sits below BOTH sources (median delta 0 words).
        # Matching a shorter dictation sentence is correct - dictation wording wins 6:1 -
        # so only flag text shorter than the template AND than its own dictated source.
        if m and t_all and not is_abnormal(m) and len(m.split()) < len(t_all.split()) - 2:
            best, bs = "", 0.0
            for d in dsents:
                sc = sim(m, d)
                if sc > bs:
                    bs, best = sc, d
            if not (bs >= 0.45 and len(m.split()) >= len(best.split()) - 2):
                v.append(("R6 compressed-below-both", f"[{f.label}] {m[:70]} << {t_all[:70]}"))
        # R8: abnormal statement first within a field (85.0%)
        ss = [squash(s) for s in split_sentences(m) if len(squash(s).split()) >= 3]
        k = ["A" if (is_abnormal(s) and not is_negative(s)) else "N" for s in ss]
        if "A" in k and "N" in k and k.index("A") > k.index("N"):
            v.append(("R8 normal-before-abnormal", f"[{f.label}] {''.join(k)}"))

    # R7: limitation statements survive 85.3%
    for s in split_sentences(row["dictation"] or ""):
        s = squash(s)
        if len(s.split()) >= 3 and LIM.search(s) and not any(sim(s, x) >= 0.55 for x in rs):
            v.append(("R7 dropped-limitation", s[:80]))
    # R5: dictation layout headers are kept only 5.4% - they must not appear
    for s in rs:
        if is_layout_header(squash(s)):
            v.append(("R5 leaked-layout-header", squash(s)[:60]))

    imp = imp_of(mine)
    items = [re.sub(r"^\d+[\.\)]\s*", "", l.strip()) for l in imp.split("\n") if l.strip()]
    raw = [l.strip() for l in imp.split("\n") if l.strip()]
    if items:
        # R1: numbered at >=2 items (92%), plain at 1 item (82%)
        numbered = bool(re.match(r"^\d+[\.\)]", raw[0]))
        if len(items) >= 2 and not numbered:
            v.append(("R1 impression-not-numbered", f"{len(items)} items"))
        if len(items) == 1 and numbered:
            v.append(("R1 single-item-numbered", raw[0][:60]))
        # R2: the closing negative goes last (325 vs 34)
        negs = [is_negative(x) for x in items]
        if len(items) >= 2 and any(negs) and not all(negs) and negs[0] and not negs[-1]:
            v.append(("R2 negative-first", items[0][:70]))
    queue.append((len(v), cid, row["study_description"], v))

queue.sort(key=lambda x: -x[0])
counts = {}
for n, _, _, vs in queue:
    for k, _d in vs:
        counts[k] = counts.get(k, 0) + 1
print(f"{sum(n for n,_,_,_ in queue)} violations across {sum(1 for n,_,_,_ in queue if n)} of {len(queue)} cases\n")
for k in sorted(counts, key=lambda x: -counts[x]):
    print(f"  {counts[k]:4d}  {k}")
if not a.quiet:
    print()
    for n, cid, desc, vs in queue:
        if not n:
            continue
        print("=" * 96)
        print(f"{cid} | {desc} | {n} violations")
        for k, d in vs:
            print(f"   {k:32s} {d}")
