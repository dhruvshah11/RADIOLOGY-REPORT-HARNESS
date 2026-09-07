"""Measure the reference reports' editing conventions on train.csv.

Every rule in the stage-2 instruction set is either confirmed or rejected here,
so the instruction set is evidence rather than taste.  Run:  python scripts/style_study.py
"""
import os, re, sys, statistics as st
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd
from rrh.dictation import segment_dictation, _classify_boilerplate
from rrh.editor import is_negative
from rrh.impression import is_abnormal
from rrh.template import parse_template
from rrh.textutil import content_tokens, sim, split_sentences, squash
from rrh.lexicon import stem
from rrh.validate import report_sentences

ROOT = os.path.join(os.path.dirname(__file__), "..")
train = pd.read_csv(os.path.join(ROOT, "data", "train.csv"))


def impression(rep):
    i = rep.find("IMPRESSION:")
    return rep[i + len("IMPRESSION:"):].strip() if i >= 0 else ""


def items(imp):
    return [re.sub(r"^\d+[\.\)]\s*", "", l.strip()) for l in imp.split("\n") if l.strip()]


def hdr(n, q):
    print(f"\n[{n}] {q}")


# ---------------------------------------------------------------- 1,2: impression shape
num, plain, negpos = {}, {}, [0, 0, 0, 0]
for rep in train["report"]:
    raw = [l.strip() for l in impression(rep).split("\n") if l.strip()]
    it = items(impression(rep))
    if not it:
        continue
    k = min(len(it), 6)
    d = num if re.match(r"^\d+[\.\)]", raw[0]) else plain
    d[k] = d.get(k, 0) + 1
    if len(it) >= 2:
        negs = [is_negative(x) for x in it]
        if not any(negs): negpos[3] += 1
        elif all(negs): negpos[2] += 1
        elif negs[-1] and not negs[0]: negpos[1] += 1
        elif negs[0] and not negs[-1]: negpos[0] += 1

hdr(1, "Is the impression numbered?")
for k in sorted(set(num) | set(plain)):
    n, p = num.get(k, 0), plain.get(k, 0)
    print(f"    {k} item(s): numbered {100*n/max(n+p,1):5.1f}%   (n={n+p})")
hdr(2, "Where does the closing negative sit in a multi-item impression?")
print(f"    last {negpos[1]}   first {negpos[0]}   all-negative {negpos[2]}   none {negpos[3]}")

# ------------------------------------------- 3,4,5: template sentence survival and wording
kept_clean = tot_clean = kept_edit = tot_edit = 0
untouched_kept = untouched_tot = 0
para = {"tmpl": 0, "dict": 0, "tie": 0}
delta = []
for _, row in train.iterrows():
    tmpl, rep = parse_template(row["template_content"]), row["report"]
    rs = report_sentences(rep)
    out = {f.label: squash(f.text) for f in parse_template(rep).fields if f.label}
    dsents = [squash(s.text) for s in segment_dictation(row["dictation"] or "").all_reportable]
    for f in tmpl.fields:
        if not f.label:
            continue
        edited = out.get(f.label, "") != squash(f.text)
        for t in split_sentences(f.text):
            t = squash(t)
            if len(t.split()) < 3:
                continue
            kept = any(sim(t, x) >= 0.62 for x in rs)
            if edited: tot_edit += 1; kept_edit += kept
            else:      tot_clean += 1; kept_clean += kept
            best, bs = None, 0.0
            for d in dsents:
                s = sim(t, d)
                if s > bs: bs, best = s, d
            if best is not None and 0.40 <= bs < 0.90:
                a = max((sim(t, x) for x in rs), default=0.0)
                b = max((sim(best, x) for x in rs), default=0.0)
                para["tmpl" if a > b + 0.05 else "dict" if b > a + 0.05 else "tie"] += 1
                delta.append(len(best.split()) - len(t.split()))
            if bs < 0.25:
                tk = {stem(x) for x in content_tokens(t)}
                if tk and not any(len(tk & {stem(y) for y in content_tokens(d)}) / len(tk) > 0.5
                                  for d in dsents):
                    untouched_tot += 1
                    untouched_kept += any(sim(t, x) >= 0.62 for x in rs)

hdr(3, "Does the reference keep the template's sentences?")
print(f"    in fields it leaves alone : {100*kept_clean/max(tot_clean,1):5.1f}% (n={tot_clean})")
print(f"    in fields it edits        : {100*kept_edit/max(tot_edit,1):5.1f}% (n={tot_edit})")
hdr(4, "A template sentence the dictation never mentions:")
print(f"    kept by the reference     : {100*untouched_kept/max(untouched_tot,1):5.1f}% (n={untouched_tot})")
hdr(5, "The dictation paraphrases a template sentence - whose wording wins?")
print(f"    dictation {para['dict']}   template {para['tmpl']}   tie {para['tie']}   "
      f"median len(dict)-len(tmpl) = {st.median(delta):+.0f} words")

# ------------------------------------------------------------- 6: boilerplate survival
kept, tot = {}, {}
for _, row in train.iterrows():
    rs = report_sentences(row["report"])
    for s in split_sentences(row["dictation"] or ""):
        t = squash(s)
        if len(t.split()) < 3:
            continue
        k = _classify_boilerplate(t)
        if not k:
            for k2, pat in (("limitation", r"\blimited\b|\bsuboptimal\b|\bdegraded\b|\bincomplete\b"),
                            ("recommendation", r"\b(is|are)\s+(advised|recommended|suggested)\b|\brecommend")):
                if re.search(pat, t, re.I): k = k2; break
        if not k:
            continue
        tot[k] = tot.get(k, 0) + 1
        kept[k] = kept.get(k, 0) + any(sim(t, x) >= 0.55 for x in rs)
hdr(6, "Which non-finding dictation sentences survive into the reference?")
for k in sorted(tot, key=lambda x: -tot[x]):
    print(f"    {k:16s} {100*kept[k]/tot[k]:5.1f}% kept  (n={tot[k]})")

# --------------------------------------------------- 7: within-field ordering
ab_first = n_first = 0
for rep in train["report"]:
    for f in parse_template(rep).fields:
        if not f.label:
            continue
        ss = [squash(s) for s in split_sentences(f.text) if len(squash(s).split()) >= 3]
        kinds = ["A" if (is_abnormal(s) and not is_negative(s)) else "N" for s in ss]
        if "A" in kinds and "N" in kinds:
            if kinds.index("A") < kinds.index("N"): ab_first += 1
            else: n_first += 1
hdr(7, "Within a field, does the abnormal statement come first?")
print(f"    abnormal-first {100*ab_first/(ab_first+n_first):5.1f}%  (n={ab_first+n_first})  "
      "- note: is_abnormal() is noisy, treat as indicative only")

# ------------------------------------- 8: impression length vs the dictated summary
ratio, sw, nw = [], [], []
for _, row in train.iterrows():
    doc = segment_dictation(row["dictation"] or "")
    it = items(impression(row["report"]))
    if not it:
        continue
    (sw if doc.impression else nw).extend(len(x.split()) for x in it)
    if doc.impression:
        s = sum(len(x.text.split()) for x in doc.impression)
        if s: ratio.append(len(impression(row["report"]).split()) / s)
hdr(8, "Impression length")
print(f"    with a dictated summary : {st.median(sw):.0f} words/item, "
      f"reference/summary word ratio median {st.median(ratio):.2f}")
print(f"    without one             : {st.median(nw):.0f} words/item")
print("\nConclusion: reuse the dictated summary near-verbatim; do not aggressively trim it.")
