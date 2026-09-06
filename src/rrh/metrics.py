"""Offline scoring.

The leaderboard metric (RES - Radiology Edit Score, lower is better) is not
published, so we optimise a *family* of edit-based proxies and report them all.
`res_word` is the headline number used for tuning; `res_char` and the
structural scores guard against over-fitting one particular formulation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .template import parse_template
from .textutil import key, levenshtein, squash, token_set


def _words(text: str) -> list[str]:
    return key(text).split()


def res_word(pred: str, ref: str) -> float:
    r = _words(ref)
    p = _words(pred)
    if not r:
        return 0.0 if not p else 1.0
    return levenshtein(p, r) / len(r)


def res_char(pred: str, ref: str) -> float:
    r = squash(ref)
    p = squash(pred)
    if not r:
        return 0.0 if not p else 1.0
    return levenshtein(p, r) / len(r)


def res_raw(pred: str, ref: str) -> float:
    """Formatting-sensitive variant: raw characters, nothing normalised."""
    r = (ref or "").strip()
    p = (pred or "").strip()
    if not r:
        return 0.0 if not p else 1.0
    return levenshtein(p, r) / len(r)


def field_scores(pred: str, ref: str) -> dict[str, float]:
    """Per-field agreement: did we edit the same fields, the same way?"""
    P = {f.label: squash(f.text) for f in parse_template(pred).fields if f.label}
    R = {f.label: squash(f.text) for f in parse_template(ref).fields if f.label}
    if not R:
        return {"field_label_f1": 1.0, "field_exact": 1.0, "field_res": 0.0}
    inter = set(P) & set(R)
    prec = len(inter) / len(P) if P else 0.0
    rec = len(inter) / len(R)
    f1 = 0.0 if prec + rec == 0 else 2 * prec * rec / (prec + rec)
    exact = sum(1 for k in inter if key(P[k]) == key(R[k])) / len(R)
    fres = sum(res_word(P.get(k, ""), R[k]) for k in R) / len(R)
    return {"field_label_f1": f1, "field_exact": exact, "field_res": fres}


_IMP = re.compile(r"^[ \t]*IMPRESSION[ \t]*:[ \t]*", re.I | re.M)


def split_parts(text: str) -> tuple[str, str]:
    m = _IMP.search(text)
    return (text[: m.start()], text[m.end() :]) if m else (text, "")


@dataclass
class Score:
    n: int
    res_word: float
    res_char: float
    res_raw: float
    findings_res: float
    impression_res: float
    field_label_f1: float
    field_exact: float
    field_res: float
    content_recall: float
    content_precision: float

    def as_row(self) -> str:
        return (
            f"n={self.n}  RES_word={self.res_word:.4f}  RES_char={self.res_char:.4f}  "
            f"RES_raw={self.res_raw:.4f}  "
            f"find={self.findings_res:.4f}  imp={self.impression_res:.4f}  "
            f"labelF1={self.field_label_f1:.4f}  fieldExact={self.field_exact:.4f}  "
            f"fieldRES={self.field_res:.4f}  cRec={self.content_recall:.3f}  "
            f"cPrec={self.content_precision:.3f}"
        )


def evaluate(preds: list[str], refs: list[str]) -> Score:
    acc = {
        k: 0.0
        for k in (
            "res_word res_char res_raw findings_res impression_res field_label_f1 "
            "field_exact field_res content_recall content_precision"
        ).split()
    }
    n = len(refs)
    for p, r in zip(preds, refs):
        acc["res_word"] += res_word(p, r)
        acc["res_char"] += res_char(p, r)
        acc["res_raw"] += res_raw(p, r)
        pf, pi = split_parts(p)
        rf, ri = split_parts(r)
        acc["findings_res"] += res_word(pf, rf)
        acc["impression_res"] += res_word(pi, ri)
        for k, v in field_scores(p, r).items():
            acc[k] += v
        tp, tr_ = token_set(p), token_set(r)
        acc["content_recall"] += len(tp & tr_) / max(1, len(tr_))
        acc["content_precision"] += len(tp & tr_) / max(1, len(tp))
    return Score(n=n, **{k: v / max(1, n) for k, v in acc.items()})
