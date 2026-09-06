"""Decompose coordinated dictation sentences so each clause can be routed.

The reference reports routinely split a dictated sentence across fields, e.g.

    "No acute fracture or dislocation is identified."
        -> BONES:  No acute fracture is identified.
        -> JOINTS: No dislocation is identified.

A decomposition is only adopted (in `routing`) when its parts genuinely land in
different template fields; otherwise the sentence is kept verbatim.
"""
from __future__ import annotations

import re

from .textutil import content_tokens, squash

_NEG_LEAD = re.compile(
    r"^(?P<lead>no evidence of|there is no|there are no|no significant|no acute|no)\s+"
    r"(?P<body>.+?)(?P<tail>\s+(?:is|are|was|were)\s+"
    r"(?:identified|seen|noted|present|evident|visualized|visualised|appreciated|"
    r"demonstrated|observed))?\s*[.]?$",
    re.I,
)
_SUBJ_LIST = re.compile(
    r"^(?P<det>the\s+)?(?P<subj>.+?)\s+(?P<verb>are|were)\s+(?P<pred>.+?)\s*[.]?$", re.I
)
_LIST_SPLIT = re.compile(r"\s*,\s*(?:and\s+|or\s+)?|\s+and\s+|\s+or\s+", re.I)
_COMMA_SPLIT = re.compile(r"\s*[,;]\s*")

_MAX_PART_TOKENS = 8


def _ok_parts(parts: list[str], minimum: int = 2) -> bool:
    if len(parts) < minimum:
        return False
    for p in parts:
        n = len(content_tokens(p))
        if n < 1 or n > _MAX_PART_TOKENS:
            return False
    return True


def split_negation(text: str) -> list[str] | None:
    m = _NEG_LEAD.match(squash(text))
    if not m:
        return None
    lead = m.group("lead")
    body = m.group("body") or ""
    tail = m.group("tail") or ""
    if re.search(r"\b(with|without|causing|producing|resulting|extending)\b", body, re.I):
        return None
    parts = [p.strip() for p in _LIST_SPLIT.split(body) if p.strip()]
    if not _ok_parts(parts):
        return None
    tail = re.sub(r"\bare\b", "is", tail, flags=re.I)
    tail = re.sub(r"\bwere\b", "was", tail, flags=re.I)
    low = lead.lower()
    if low == "no evidence of":
        return [f"No evidence of {p}{tail}." for p in parts]
    if low in {"no acute", "no significant"}:
        # the qualifier belongs to the first item only:
        # "No acute fracture or dislocation" -> "No acute fracture." / "No dislocation."
        head = f"{lead.capitalize().replace('No ', 'No ')} {parts[0]}{tail}."
        return [head] + [f"No {p}{tail}." for p in parts[1:]]
    return [f"No {p}{tail}." for p in parts]


def split_subject_list(text: str) -> list[str] | None:
    t = squash(text)
    m = _SUBJ_LIST.match(t)
    if not m:
        return None
    subj, pred = m.group("subj"), m.group("pred")
    det = "The " if (m.group("det") or "").strip() else ""
    if re.search(r"\b(no|not|without)\b", subj, re.I):
        return None
    parts = [p.strip() for p in _LIST_SPLIT.split(subj) if p.strip()]
    if not _ok_parts(parts):
        return None
    verb = "is" if m.group("verb").lower() == "are" else "was"
    return [f"{det}{p} {verb} {pred}." for p in parts]


def split_clauses(text: str) -> list[str] | None:
    t = squash(text).rstrip(".")
    parts = [p.strip(" .") for p in _COMMA_SPLIT.split(t) if p.strip(" .")]
    if not _ok_parts(parts):
        return None
    if any(re.match(r"^(and|or|with|without|which|more|greatest|most)\b", p, re.I) for p in parts):
        return None
    return [p + "." for p in parts]


def candidate_splits(text: str) -> list[list[str]]:
    """Alternative decompositions of `text`, best first."""
    out: list[list[str]] = []
    for fn in (split_negation, split_subject_list, split_clauses):
        parts = fn(text)
        if parts and len(parts) >= 2:
            out.append([squash(p) for p in parts])
    # de-duplicate while preserving order
    seen: set[tuple[str, ...]] = set()
    uniq: list[list[str]] = []
    for p in out:
        k = tuple(p)
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return uniq
