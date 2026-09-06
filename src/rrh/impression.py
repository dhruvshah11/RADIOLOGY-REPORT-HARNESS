"""IMPRESSION construction.

Two branches, both purely extractive:
  * the radiologist dictated a summary  -> reuse it (that is what the reference
    reports do), minus normal/negative filler;
  * no dictated summary                 -> condense the abnormal findings that
    were routed into FINDINGS and close with the template's normal impression.

Nothing is ever added that the dictation or template did not state.
"""
from __future__ import annotations

import re

from .dictation import POS_HINT
from .editor import NORMAL_STATE_RE, is_negative
from .template import resolve_placeholders
from .textutil import content_tokens, sim, squash, tidy_sentence

LEAD_EXISTENTIAL = re.compile(r"^there\s+(?:is|are|was|were)\s+(?:a|an|the)?\s*", re.I)
COPULA_TAIL = re.compile(
    r"\s+(?:is|are|was|were)\s+(?:identified|seen|noted|present|evident|visualized|"
    r"visualised|appreciated|demonstrated|observed)\b\.?$",
    re.I,
)
LEAD_ARTICLE = re.compile(r"^(?:a|an)\s+", re.I)
SPECIFICALLY = re.compile(r"^specifically,\s*", re.I)
# A template impression that asserts a normal study must not be appended next to
# abnormal findings - that would contradict the report.
TEMPLATE_NEGATIVE = re.compile(r"^\s*(no|without|negative for)\b", re.I)

DETAIL_TAIL = re.compile(
    r",?\s+(?:with|including|associated with|demonstrating|showing|producing|resulting in|"
    r"causing)\s+.+$",
    re.I,
)


def is_normal_statement(sentence: str) -> bool:
    return bool(NORMAL_STATE_RE.search(sentence)) and not POS_HINT.search(sentence)


def is_abnormal(sentence: str) -> bool:
    return (
        not is_negative(sentence)
        and not is_normal_statement(sentence)
        and bool(POS_HINT.search(sentence))
    )


def condense(text: str, trim_detail: bool = False) -> str:
    """Turn a findings sentence into an impression item (removal only)."""
    t = squash(text)
    t = LEAD_EXISTENTIAL.sub("", t)
    t = COPULA_TAIL.sub("", t)
    t = LEAD_ARTICLE.sub("", t)
    t = SPECIFICALLY.sub("", t)
    if trim_detail:
        head = DETAIL_TAIL.sub("", t)
        if len(content_tokens(head)) >= 3:
            t = head
    return tidy_sentence(t)


SEVERITY = (
    (re.compile(r"\b(severe|marked|extensive|large|complete|full-thickness|acute|"
                r"high-grade|gross|advanced)\b", re.I), 3.0),
    (re.compile(r"\b(moderate|moderate-to-severe|mild-to-moderate)\b", re.I), 2.0),
    (re.compile(r"\b(mild|minimal|small|trace|low-grade|early|subtle)\b", re.I), 1.0),
)


def severity(text: str) -> float:
    for pattern, weight in SEVERITY:
        if pattern.search(text):
            return weight
    return 1.5


def _dedupe(items: list[str], threshold: float = 0.82) -> list[str]:
    out: list[str] = []
    for it in items:
        if not squash(it):
            continue
        if any(sim(it, o) >= threshold for o in out):
            continue
        out.append(it)
    return out


def build_impression(
    dictated_summary: list[str],
    findings: list[str],
    template_impression: list[str],
    laterality: str | None,
    region: str | None,
    cfg,
) -> list[str]:
    tmpl_lines = [
        tidy_sentence(resolve_placeholders(x, laterality, region))
        for x in template_impression
        if squash(x)
    ]

    if dictated_summary:
        items = [condense(x) for x in dictated_summary]
        cap = cfg.summary_cap
    else:
        source = findings
        if cfg.findings_require_abnormal:
            abnormal = [x for x in findings if is_abnormal(x)]
            if not abnormal:
                # nothing abnormal was dictated: restating normal findings is
                # not an impression.  Fall back to the template's normal line,
                # optionally preceded by the dictation's own negative summary.
                if cfg.no_abnormal_fallback == "negatives":
                    source = [x for x in findings if is_negative(x)][-1:]
                else:
                    source = []
            else:
                source = abnormal
        items = [condense(x, trim_detail=cfg.trim_detail) for x in source]
        cap = cfg.findings_cap

    items = [x for x in items if not is_normal_statement(x)]
    if cfg.drop_negative_impression and not (
        not dictated_summary and cfg.no_abnormal_fallback == "negatives" and items
        and all(is_negative(x) for x in items)
    ):
        items = [x for x in items if not is_negative(x)]
    items = _dedupe(items, cfg.impression_dedupe)
    if cfg.rank_impression_by_severity and not dictated_summary:
        items = sorted(items, key=lambda x: -severity(x))
    if cap:
        items = items[:cap]

    if not dictated_summary and items and cfg.append_template_impression:
        closing = [x for x in tmpl_lines[:1] if TEMPLATE_NEGATIVE.match(x)]
        items = items + closing
    if not items:
        items = tmpl_lines or ["No acute abnormality."]

    if cfg.number_impression and len(items) > 1:
        return [f"{i}. {t}" for i, t in enumerate(items, 1)]
    return items
