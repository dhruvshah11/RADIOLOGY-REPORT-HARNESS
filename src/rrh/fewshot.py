"""Retrieve worked examples of the *same template* to teach the house phrasing.

117 of the 132 test cases share a template with the training set (median 19
examples each).  The measured residual after routing and formatting are correct
is *phrasing*, and a worked example of the same template is the most direct
signal for it available.

The pool never includes the case being refined: when a training case is refined
for measurement, its own reference is excluded, so the score stays honest.
"""
from __future__ import annotations

from dataclasses import dataclass

from .routing import template_key
from .textutil import sim, squash


@dataclass
class Example:
    case_id: str
    study: str
    dictation: str
    report: str


class FewShotIndex:
    """Groups training rows by template so examples can be pulled per case."""

    def __init__(self, rows: list[dict]) -> None:
        self.by_template: dict[str, list[dict]] = {}
        for r in rows:
            key = template_key(r.get("template_content") or "")
            self.by_template.setdefault(key, []).append(r)

    def examples(self, row: dict, k: int = 4, exclude_case: str | None = None) -> list[Example]:
        """The k most dictation-similar training cases sharing this row's template."""
        key = template_key(row.get("template_content") or "")
        pool = self.by_template.get(key, [])
        target = squash(row.get("dictation") or "")
        scored = []
        for cand in pool:
            cid = cand.get("case_id")
            if exclude_case is not None and cid == exclude_case:
                continue  # never show a case its own reference
            if not (cand.get("report") or "").strip():
                continue
            scored.append((sim(target, squash(cand.get("dictation") or "")), cid, cand))
        # deterministic: similarity desc, then case_id
        scored.sort(key=lambda t: (-t[0], str(t[1])))
        out = []
        for _s, cid, cand in scored[:k]:
            out.append(Example(
                case_id=str(cid),
                study=str(cand.get("study_description") or ""),
                dictation=(cand.get("dictation") or "").strip(),
                report=(cand.get("report") or "").strip(),
            ))
        return out

    def coverage(self, rows: list[dict]) -> dict:
        counts = [len(self.by_template.get(template_key(r.get("template_content") or ""), []))
                  for r in rows]
        return {
            "cases": len(counts),
            "with_any": sum(1 for c in counts if c > 0),
            "with_3plus": sum(1 for c in counts if c >= 3),
            "median": sorted(counts)[len(counts) // 2] if counts else 0,
        }
