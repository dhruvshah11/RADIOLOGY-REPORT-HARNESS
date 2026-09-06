"""Cost-sensitive selection of the IMPRESSION strategy.

Three strategies are available for any case: reuse the radiologist's dictated
summary, condense the abnormal findings, or keep the template's normal
impression.  Which one is closest to the reference varies by case.

The learned ranker experiment showed that optimising *classification accuracy*
on a proxy label is the wrong objective, so this chooser is fitted directly on
the quantity that matters: it searches a small space of one-feature decision
rules and keeps the one that minimises total impression edit distance on the
training folds.
"""
from __future__ import annotations

from dataclasses import dataclass

VARIANTS = ("summary", "findings", "template")

FEATURES = (
    "has_summary", "n_summary", "n_findings", "n_abnormal",
    "summary_tokens", "findings_tokens", "summary_ratio", "template_negative",
)

THRESHOLDS = {
    "has_summary": (0.5,),
    "n_summary": (0.5, 1.5, 2.5, 3.5, 5.5),
    "n_findings": (0.5, 1.5, 2.5, 4.5, 7.5),
    "n_abnormal": (0.5, 1.5, 2.5, 3.5),
    "summary_tokens": (0.5, 5.5, 12.5, 25.5),
    "findings_tokens": (5.5, 15.5, 30.5, 60.5),
    "summary_ratio": (0.05, 0.25, 0.5, 0.8, 1.2),
    "template_negative": (0.5,),
}


@dataclass
class Chooser:
    """A depth<=2 decision rule over `FEATURES` returning a variant name."""

    root: tuple[str, float] | None = None
    left: "Chooser | str" = "findings"
    right: "Chooser | str" = "summary"
    default: str = "summary"

    def choose(self, feat: dict[str, float]) -> str:
        if self.root is None:
            return self.default
        name, thr = self.root
        branch = self.left if feat.get(name, 0.0) <= thr else self.right
        return branch.choose(feat) if isinstance(branch, Chooser) else branch


def _best_leaf(rows) -> tuple[str, float]:
    best, best_cost = VARIANTS[0], float("inf")
    for v in VARIANTS:
        cost = sum(r["cost"][v] for r in rows)
        if cost < best_cost - 1e-12:
            best, best_cost = v, cost
    return best, best_cost


def _fit_stump(rows) -> tuple[tuple[str, float] | None, str, str, float]:
    base_leaf, base_cost = _best_leaf(rows)
    best = (None, base_leaf, base_leaf, base_cost)
    for name in FEATURES:
        for thr in THRESHOLDS[name]:
            left = [r for r in rows if r["feat"].get(name, 0.0) <= thr]
            right = [r for r in rows if r["feat"].get(name, 0.0) > thr]
            if len(left) < 20 or len(right) < 20:
                continue
            lv, lc = _best_leaf(left)
            rv, rc = _best_leaf(right)
            if lc + rc < best[3] - 1e-12:
                best = ((name, thr), lv, rv, lc + rc)
    return best


def fit_chooser(rows, depth: int = 2) -> Chooser:
    """`rows` is a list of {"feat": {...}, "cost": {variant: res}}."""
    if not rows:
        return Chooser()
    root, lv, rv, _ = _fit_stump(rows)
    if root is None:
        return Chooser(root=None, default=lv)
    name, thr = root
    left_rows = [r for r in rows if r["feat"].get(name, 0.0) <= thr]
    right_rows = [r for r in rows if r["feat"].get(name, 0.0) > thr]
    left: Chooser | str = lv
    right: Chooser | str = rv
    if depth > 1:
        sub_l = fit_chooser(left_rows, depth - 1)
        if sub_l.root is not None:
            left = sub_l
        sub_r = fit_chooser(right_rows, depth - 1)
        if sub_r.root is not None:
            right = sub_r
    return Chooser(root=root, left=left, right=right, default=lv)


def features(summary: list[str], findings: list[str], abnormal: list[str],
             template_impression: list[str]) -> dict[str, float]:
    from .textutil import content_tokens

    st = sum(len(content_tokens(x)) for x in summary)
    ft = sum(len(content_tokens(x)) for x in findings)
    neg = bool(template_impression) and template_impression[0].strip().lower().startswith(
        ("no ", "without", "negative")
    )
    return {
        "has_summary": 1.0 if summary else 0.0,
        "n_summary": float(len(summary)),
        "n_findings": float(len(findings)),
        "n_abnormal": float(len(abnormal)),
        "summary_tokens": float(st),
        "findings_tokens": float(ft),
        "summary_ratio": st / max(1.0, float(ft)),
        "template_negative": 1.0 if neg else 0.0,
    }


def build_training_rows(train_rows, model, cfg) -> list[dict]:
    """Cost of each impression strategy on every training row.

    The cost is the edit distance of the **whole report**, not of the impression
    alone: per-section means over-weight cases whose reference impression is one
    short line, and a chooser trained on those picks strategies that make the
    report as a whole worse.
    """
    from .dictation import segment_dictation
    from .impression import is_abnormal
    from .metrics import res_char, res_word
    from .pipeline import ReportGenerator
    from .template import parse_template

    gen = ReportGenerator(model, cfg)
    out = []
    for row in train_rows:
        tmpl = parse_template(row["template_content"])
        doc = segment_dictation(
            row["dictation"],
            normalize=cfg.normalize_shorthand,
            vocab=model.vocab if cfg.correct_spelling else None,
            summary_threshold=cfg.summary_threshold,
            summary_max_misses=cfg.summary_max_misses,
            summary_after_cues=cfg.summary_after_cues,
        )
        summary = [s.text for s in doc.impression]
        findings = [s.text for s in doc.findings]
        abnormal = [x for x in findings if is_abnormal(x)]
        ref = row["report"]
        cost = {}
        for v in VARIANTS:
            pred, _ = gen.generate(row, force_impression=v)
            cost[v] = (res_word(pred, ref) + res_char(pred, ref)) / 2
        out.append({
            "feat": features(summary, findings, abnormal, tmpl.impression),
            "cost": cost,
        })
    return out
