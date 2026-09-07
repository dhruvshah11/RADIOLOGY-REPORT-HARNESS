"""Validation layer.

Runs after generation and answers the questions the task brief asks for:
negation preserved, laterality preserved, measurements preserved, nothing
invented, untouched template fields untouched, dictated findings not dropped.

`validate` reports issues; `repair` fixes the ones that can be fixed
deterministically (a dropped finding is re-attached rather than lost).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field

from .dictation import LATERAL_RE, MEASURE_RE, segment_dictation
from .editor import is_negative
from .lexicon import stem
from .template import parse_template, resolve_placeholders
from .textutil import content_tokens, sim, split_sentences, squash


@dataclass
class Issue:
    kind: str
    detail: str
    severity: str = "warn"


@dataclass
class ValidationResult:
    issues: list[Issue] = dc_field(default_factory=list)

    def add(self, kind: str, detail: str, severity: str = "warn") -> None:
        self.issues.append(Issue(kind, detail, severity))

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for i in self.issues:
            out[i.kind] = out.get(i.kind, 0) + 1
        return out


def _lateralities(text: str) -> set[str]:
    out = set()
    for m in LATERAL_RE.finditer(text or ""):
        v = m.group(1).lower()
        out.add({"rt": "right", "lt": "left", "b/l": "bilateral", "bilat": "bilateral"}.get(v, v))
    return out


def _measurements(text: str) -> set[str]:
    return {squash(m.group(0)).lower().replace(" ", "") for m in MEASURE_RE.finditer(text or "")}


LABEL_PREFIX = re.compile(r"^[ \t]*[A-Z][A-Z0-9 ,'\-/&\.\(\)]{0,58}?:[ \t]*", re.M)


def report_sentences(report: str) -> list[str]:
    """Sentences of a report with the field labels stripped off."""
    return split_sentences(LABEL_PREFIX.sub("", report))


def validate(row: dict, report: str, trace, vocab: dict | None = None) -> ValidationResult:
    res = ValidationResult()
    tmpl = parse_template(row["template_content"])
    out = parse_template(report)
    doc = segment_dictation(row.get("dictation") or "", vocab=vocab)

    # ---- structure -----------------------------------------------------
    if "FINDINGS:" not in report or "IMPRESSION:" not in report:
        res.add("structure", "missing FINDINGS/IMPRESSION header", "error")
    t_labels = [f.label for f in tmpl.fields if f.label]
    o_labels = [f.label for f in out.fields if f.label]
    if t_labels != o_labels:
        res.add("structure", f"label sequence changed: {set(t_labels) ^ set(o_labels)}", "error")
    if re.search(r"\[[^\]]*\]", report):
        res.add("placeholder", "unresolved [placeholder] left in report", "error")

    # ---- untouched fields ---------------------------------------------
    out_by_label = {f.label: squash(f.text) for f in out.fields if f.label}
    for f in tmpl.fields:
        if not f.label or f.label == "OTHER FINDINGS":
            continue
        if trace.routed.get(f.label):
            continue
        expected = squash(
            resolve_placeholders(f.text, trace.laterality, trace.region)
            if "[" in f.text
            else f.text
        )
        if out_by_label.get(f.label, "") != expected:
            res.add("untouched_field", f"{f.label} changed without a routed finding", "error")

    # ---- laterality ----------------------------------------------------
    sentences = report_sentences(report)
    for seg in doc.findings:
        lat = _lateralities(seg.text)
        if not lat:
            continue
        matched = [s for s in sentences if sim(seg.text, s) >= 0.5]
        if matched and not any(_lateralities(s) & lat for s in matched):
            res.add("laterality", f"laterality {sorted(lat)} lost: {seg.text[:70]}", "error")

    # ---- negation ------------------------------------------------------
    for seg in doc.findings:
        if not is_negative(seg.text):
            continue
        toks = {stem(t) for t in content_tokens(seg.text)}
        if not toks:
            continue
        matches = [
            s
            for s in sentences
            if (st := {stem(t) for t in content_tokens(s)}) and len(toks & st) / len(toks) >= 0.8
        ]
        if not matches:
            continue
        # the negation is preserved as long as *some* matching sentence still
        # states it negatively (the same phrase may also appear, correctly, as a
        # positive finding at another level or site)
        if not any(
            is_negative(s) or "without" in s.lower() or " no " in f" {s.lower()} "
            for s in matches
        ):
            res.add("negation", f"negated finding rendered positive: {seg.text[:70]}", "error")

    # ---- measurements --------------------------------------------------
    dict_meas = set()
    for seg in doc.findings + doc.impression:
        dict_meas |= _measurements(seg.text)
    lost = dict_meas - _measurements(report)
    for m in sorted(lost):
        res.add("measurement", f"measurement dropped: {m}")

    # ---- unsupported content (hallucination) ---------------------------
    allowed = set()
    normalised = " ".join(s.text for s in doc.preamble + doc.findings + doc.impression)
    for src in (row["template_content"], row.get("dictation") or "", normalised):
        allowed |= {stem(t) for t in content_tokens(src)}
    allowed |= {stem(t) for t in content_tokens(str(row.get("body_part") or ""))}
    allowed |= {stem(t) for t in content_tokens(str(row.get("study_description") or ""))}
    allowed |= {"remaining", "otherwise", "left", "right", "bilateral", "lumbar", "thoracic",
                "cervical", "lumbosacral", "sacral"}
    unseen = sorted({stem(t) for t in content_tokens(report)} - allowed)
    for t in unseen:
        res.add("unsupported_term", f"term not present in template or dictation: {t}", "error")

    # ---- omissions -----------------------------------------------------
    for seg in doc.findings:
        if len(content_tokens(seg.text)) < 2:
            continue
        toks = {stem(t) for t in content_tokens(seg.text)}
        rep_toks = {stem(t) for t in content_tokens(report)}
        if len(toks & rep_toks) / len(toks) < 0.6:
            res.add("omission", f"dictated finding not represented: {seg.text[:70]}")
    return res


def repair(row: dict, report: str, trace, result: ValidationResult) -> str:
    """Re-attach dictated findings that were dropped, before IMPRESSION."""
    missing = [i.detail.split(": ", 1)[1] for i in result.issues if i.kind == "omission"]
    if not missing:
        return report
    doc = segment_dictation(row.get("dictation") or "")
    texts = []
    for seg in doc.findings:
        if any(seg.text[:70] == m for m in missing):
            texts.append(squash(seg.text))
    if not texts:
        return report
    idx = report.find("IMPRESSION:")
    if idx < 0:
        return report
    block = "\n" + "\n\n".join(texts) + "\n\n"
    return report[:idx].rstrip("\n") + "\n" + block + report[idx:]
