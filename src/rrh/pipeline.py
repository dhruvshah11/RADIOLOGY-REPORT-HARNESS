"""End-to-end structured-generation pipeline.

    dictation ─▶ segment ─▶ split ─▶ route ─▶ edit template ─▶ impression ─▶ validate
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field

from .dictation import segment_dictation
from .editor import edit_field, is_negative, render_clause
from .impression import build_impression
from .routing import (RoutingModel, build_context, cue_supported, field_candidates,
                      fit_router, score_segment)
from .splitting import candidate_splits
from .template import parse_template, render_report, resolve_placeholders
from .lexicon import stem
from .textutil import content_tokens, squash


@dataclass
class Config:
    # routing
    min_route_score: float = 0.45
    group_penalty: float = 1.0
    allow_splitting: bool = True
    cue_veto_penalty: float = 0.8
    cue_match_min: float = 0.34
    split_margin: float = 0.0
    # editing
    cover_threshold: float = 0.12
    dedupe_threshold: float = 0.0  # 0 disables within-field de-duplication
    soften_blanket: bool = False
    add_copula: bool = False
    add_existential: bool = False
    abnormal_first: bool = False
    style_threshold: float = 0.0  # 0 disables reference-phrasing transfer
    correct_spelling: bool = True
    suppress_redundant_negatives: bool = False
    suppress_redundant_normals: bool = False
    normalize_shorthand: bool = True
    summary_threshold: float = 0.34
    summary_max_misses: int = 3
    recover_summary: bool = True
    summary_recover_threshold: float = 0.6
    # impression
    append_template_impression: bool = True
    number_impression: bool = True
    drop_negative_impression: bool = True
    trim_detail: bool = True
    rank_impression_by_severity: bool = False
    summary_cap: int = 6
    findings_cap: int = 2
    # rendering
    blank_between_fields: bool = True
    keep_unrouted: bool = True


LATERAL_WORDS = {
    "rt": "right", "r": "right", "right": "right",
    "lt": "left", "l": "left", "left": "left",
    "bilateral": "bilateral", "b/l": "bilateral", "bilat": "bilateral", "both": "bilateral",
}
REGION_WORDS = {
    "lumbar spine": "lumbar", "lsspine": "lumbosacral", "thoracic spine": "thoracic",
    "cervical spine": "cervical", "spine sacrum": "sacral", "sacrum": "sacral",
}


def infer_laterality(row) -> str | None:
    for src in (row.get("study_description") or "", row.get("dictation") or ""):
        for m in re.finditer(r"\b(rt|lt|right|left|bilateral|bilat|b/l|both)\b", src, re.I):
            return LATERAL_WORDS.get(m.group(1).lower())
    return None


def infer_region(row) -> str | None:
    bp = (row.get("body_part") or "").strip().lower()
    if bp in REGION_WORDS:
        return REGION_WORDS[bp]
    sd = (row.get("study_description") or "").lower()
    for kw, val in (("lsp", "lumbar"), ("tsp", "thoracic"), ("csp", "cervical"),
                    ("lumbo", "lumbosacral"), ("lumbar", "lumbar"),
                    ("thoracic", "thoracic"), ("cervical", "cervical")):
        if kw in sd:
            return val
    return bp or None


@dataclass
class Trace:
    """What the pipeline decided - used by the validator and for auditing."""
    routed: dict[str, list[str]] = dc_field(default_factory=dict)
    extras: list[str] = dc_field(default_factory=list)
    dictated_impression: list[str] = dc_field(default_factory=list)
    abnormal: list[str] = dc_field(default_factory=list)
    unrouted_scores: list[tuple[str, float]] = dc_field(default_factory=list)
    normal_case: bool = False
    laterality: str | None = None
    region: str | None = None


class ReportGenerator:
    def __init__(self, model: RoutingModel, cfg: Config | None = None):
        self.model = model
        self.cfg = cfg or Config()

    # -------------------------------------------------------------- routing
    def _route_one(self, text: str, cue: str | None, tmpl, ctx):
        scored = score_segment(text, cue, tmpl, self.model, ctx)
        if not scored:
            return None, 0.0
        groups = {f.label for f in field_candidates(tmpl) if f.is_group}
        adjusted = [
            (s - (self.cfg.group_penalty if lab in groups else 0.0), lab) for s, lab in scored
        ]
        adjusted.sort(key=lambda x: (-x[0], x[1]))
        best_score, best_label = adjusted[0]
        if self.cfg.cue_veto_penalty and not cue_supported(
            cue, tmpl, ctx, self.cfg.cue_match_min
        ):
            best_score -= self.cfg.cue_veto_penalty
        if best_score < self.cfg.min_route_score:
            return None, best_score
        return best_label, best_score

    def _route_segment(self, text: str, cue: str | None, tmpl, ctx):
        """Return list of (clause text, label|None, score)."""
        label, score = self._route_one(text, cue, tmpl, ctx)
        whole = [(text, label, score)]
        if not self.cfg.allow_splitting:
            return whole
        for parts in candidate_splits(text):
            routed = [self._route_one(p, cue, tmpl, ctx) for p in parts]
            labels = [lab for lab, _ in routed]
            if any(lab is None for lab in labels):
                continue
            if len(set(labels)) < 2:
                continue
            avg = sum(s for _, s in routed) / len(routed)
            if avg + self.cfg.split_margin >= score:
                return [(p, lab, s) for p, (lab, s) in zip(parts, routed)]
        return whole

    # ------------------------------------------------------------- generate
    def generate(self, row: dict) -> tuple[str, Trace]:
        cfg = self.cfg
        tmpl = parse_template(row["template_content"])
        ctx = build_context(tmpl)
        doc = segment_dictation(
            row.get("dictation") or "",
            normalize=cfg.normalize_shorthand,
            vocab=self.model.vocab if cfg.correct_spelling else None,
            summary_threshold=cfg.summary_threshold,
            summary_max_misses=cfg.summary_max_misses,
        )
        laterality = infer_laterality(row)
        region = infer_region(row)
        trace = Trace(
            normal_case=doc.is_normal or not doc.findings,
            laterality=laterality,
            region=region,
        )

        routed: dict[str, list[str]] = {}
        extras: list[str] = []
        ordered_findings: list[str] = []
        units = list(doc.findings)
        if cfg.recover_summary and doc.impression:
            # A sentence in the dictated summary that restates nothing from the
            # body is not a summary at all - it is a finding, and must not be
            # lost just because it was dictated last.
            seen = {stem(t) for seg in doc.findings for t in content_tokens(seg.text)}
            for seg in doc.impression:
                st = {stem(t) for t in content_tokens(seg.text)}
                if st and len(st & seen) / len(st) < cfg.summary_recover_threshold:
                    units.append(seg)
        for seg in units:
            for clause, label, score in self._route_segment(seg.text, seg.cue, tmpl, ctx):
                clause = squash(clause)
                if not clause:
                    continue
                if cfg.style_threshold:
                    styled = self.model.style_match(clause, cfg.style_threshold)
                    if styled:
                        clause = styled
                if label is None:
                    if cfg.keep_unrouted:
                        extras.append(clause)
                    trace.unrouted_scores.append((clause, score))
                else:
                    routed.setdefault(label, []).append(clause)
                ordered_findings.append(clause)

        field_texts: list[tuple[str, str]] = []
        for f in tmpl.fields:
            if f.is_free:
                field_texts.append(("", resolve_placeholders(f.text, laterality, region)))
                continue
            if f.label == "OTHER FINDINGS":
                field_texts.append((f.label, ""))
                continue
            body = edit_field(f.text, routed.get(f.label, []), cfg)
            field_texts.append((f.label, resolve_placeholders(body, laterality, region)))

        impression = build_impression(
            [s.text for s in doc.impression],
            ordered_findings,
            tmpl.impression,
            laterality,
            region,
            cfg,
        )
        report = render_report(
            field_texts,
            impression,
            extra_paragraphs=[render_clause(e, cfg) for e in extras],
            blank_between_fields=cfg.blank_between_fields,
        )
        trace.routed = routed
        trace.extras = extras
        trace.dictated_impression = [s.text for s in doc.impression]
        trace.abnormal = [f for f in ordered_findings if not is_negative(f)]
        return report, trace


def build_generator(train_rows, cfg: Config | None = None) -> ReportGenerator:
    return ReportGenerator(fit_router(train_rows), cfg)
