"""A learned field router.

The hand-weighted scorer in `routing.py` combines six signals with weights set
by hand.  This module fits those weights instead: a conditional-logit (softmax
over the candidate fields of a template) trained on the `(clause -> field)`
pairs mined from the training reports, optimised with plain gradient ascent so
it stays dependency-free and deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field

from .routing import FEATURES

_INIT_SEED = {
    "cue": 3.0, "label": 2.2, "concept": 1.2, "template": 1.0, "mined": 1.2,
    "knn": 1.6, "group": -1.0, "same_prev": 0.3, "backward": -1.0, "forward": 0.0,
}
# every feature must have a weight, including ones added after this seed
INIT = {k: _INIT_SEED.get(k, 0.0) for k in FEATURES}


@dataclass
class Ranker:
    weights: dict[str, float] = dc_field(default_factory=lambda: dict(INIT))
    bias: float = 0.0

    def score(self, feat: dict[str, float]) -> float:
        w = self.weights
        return sum(w[k] * feat.get(k, 0.0) for k in FEATURES)


def _softmax(scores: list[float]) -> list[float]:
    m = max(scores)
    exps = [pow(2.718281828459045, s - m) for s in scores]
    tot = sum(exps) or 1.0
    return [e / tot for e in exps]


def fit_ranker(examples, epochs: int = 300, lr: float = 0.25, l2: float = 1e-3) -> Ranker:
    """`examples` is a list of (list[(label, features)], gold_label)."""
    w = dict(INIT)
    data = [
        (cands, gold)
        for cands, gold in examples
        if len(cands) > 1 and any(lab == gold for lab, _ in cands)
    ]
    if not data:
        return Ranker(weights=w)
    n = len(data)
    for _ in range(epochs):
        grad = {k: 0.0 for k in FEATURES}
        for cands, gold in data:
            scores = [sum(w[k] * f.get(k, 0.0) for k in FEATURES) for _, f in cands]
            probs = _softmax(scores)
            for (lab, f), p in zip(cands, probs):
                coeff = ((1.0 if lab == gold else 0.0) - p)
                for k in FEATURES:
                    v = f.get(k, 0.0)
                    if v:
                        grad[k] += coeff * v
        for k in FEATURES:
            w[k] += lr * (grad[k] / n - l2 * w[k])
    return Ranker(weights=w)


def build_examples(rows, model, cfg) -> list:
    """Feature/label pairs for every mined (clause, field) supervision item."""
    from .dictation import segment_dictation
    from .routing import build_context, field_features, mine_row
    from .template import parse_template

    out = []
    for row in rows:
        gold = {i: lab for i, _, lab, _ in mine_row(row)}
        if not gold:
            continue
        tmpl = parse_template(row["template_content"])
        ctx = build_context(tmpl)
        order = {f.label: f.order for f in tmpl.fields}
        doc = segment_dictation(
            row["dictation"],
            normalize=cfg.normalize_shorthand,
            vocab=model.vocab if cfg.correct_spelling else None,
            summary_threshold=cfg.summary_threshold,
            summary_max_misses=cfg.summary_max_misses,
        )
        units = doc.findings or doc.impression
        prev_order = None
        for i, seg in enumerate(units):
            lab = gold.get(i)
            if lab is None:
                continue
            feats = field_features(seg.text, seg.cue, tmpl, model, ctx, prev_order)
            if feats:
                out.append((feats, lab))
            prev_order = order.get(lab, prev_order)
    return out
