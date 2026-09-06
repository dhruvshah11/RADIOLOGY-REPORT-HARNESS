"""Parsing and rendering of the supplied normal template.

The template is the *starting report*: the renderer therefore reproduces the
template's field labels and field order exactly, only upper-casing labels and
inserting the blank-line separators used by the reference reports.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field

from .textutil import cap_first, clean_ws, split_sentences, squash

HEAD_FINDINGS = re.compile(r"^[ \t]*FINDINGS[ \t]*:[ \t]*", re.I | re.M)
HEAD_IMPRESSION = re.compile(r"^[ \t]*IMPRESSION[ \t]*:[ \t]*", re.I | re.M)

# A label is a short, colon-terminated prefix at the start of a line.
LABEL_RE = re.compile(r"^[ \t]*([A-Za-z][A-Za-z0-9 ,'\-/&\.\(\)]{0,58}?)[ \t]*:[ \t]*(.*)$")

# Labels that the reference reports always leave empty.
ALWAYS_EMPTY = {"OTHER FINDINGS"}


def _is_label(line: str) -> tuple[str, str] | None:
    m = LABEL_RE.match(line)
    if not m:
        return None
    label, rest = m.group(1).strip(), m.group(2).strip()
    if not label or len(label.split()) > 7:
        return None
    # reject prose that merely happens to contain a colon
    if re.search(r"[.!?]\s", label):
        return None
    return label, rest


@dataclass
class Field:
    label_raw: str
    label: str
    text: str
    is_group: bool
    order: int
    is_free: bool = False
    sentences: list[str] = dc_field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.sentences:
            self.sentences = split_sentences(self.text)


@dataclass
class Template:
    raw: str
    fields: list[Field]
    impression: list[str]
    findings_free: list[str]

    @property
    def labels(self) -> list[str]:
        return [f.label for f in self.fields]

    def by_label(self, label: str) -> Field | None:
        for f in self.fields:
            if f.label == label:
                return f
        return None


def parse_template(text: str) -> Template:
    text = clean_ws(text)
    mf = HEAD_FINDINGS.search(text)
    mi = HEAD_IMPRESSION.search(text)
    if mf and mi and mi.start() > mf.start():
        body, imp = text[mf.end() : mi.start()], text[mi.end() :]
    elif mf:
        body, imp = text[mf.end() :], ""
    elif mi:
        body, imp = text[: mi.start()], text[mi.end() :]
    else:
        body, imp = text, ""

    fields: list[Field] = []
    free: list[str] = []
    order = 0
    for line in body.split("\n"):
        line = line.strip()
        if not line:
            continue
        parsed = _is_label(line)
        if parsed:
            label_raw, rest = parsed
            fields.append(
                Field(
                    label_raw=label_raw,
                    label=label_raw.upper(),
                    text=rest,
                    is_group=(rest == ""),
                    order=order,
                )
            )
            order += 1
        else:
            # Prose templates (no labels) keep every line as its own block.
            free.append(line)
            fields.append(
                Field(
                    label_raw="",
                    label="",
                    text=line,
                    is_group=False,
                    order=order,
                    is_free=True,
                )
            )
            order += 1

    impression = [ln.strip() for ln in imp.split("\n") if ln.strip()]
    return Template(raw=text, fields=fields, impression=impression, findings_free=free)


# ------------------------------------------------------------------ render


def render_report(
    field_texts: list[tuple[str, str]],
    impression_lines: list[str],
    extra_paragraphs: list[str] | None = None,
    blank_between_fields: bool = True,
) -> str:
    """Assemble the final report.

    `field_texts` is an ordered list of (UPPERCASE label, body text) pairs; the
    body may be empty for group headers and for OTHER FINDINGS.
    """
    lines: list[str] = ["FINDINGS:"]
    first = True
    for label, body in field_texts:
        if blank_between_fields and not first:
            lines.append("")
        first = False
        body = squash(body)
        if not label:
            if body:
                lines.append(body)
            continue
        lines.append(f"{label}: {body}".rstrip() if body else f"{label}:")
    for para in extra_paragraphs or []:
        para = squash(para)
        if para:
            lines.append("")
            lines.append(para)
    lines.append("")
    lines.append("IMPRESSION:")
    lines.extend(squash(x) for x in impression_lines if squash(x))
    out = "\n".join(lines).rstrip() + "\n"
    return out


def resolve_placeholders(text: str, laterality: str | None, region: str | None) -> str:
    """Fill `[left/right]` / `[generic]` style slots left in template prose."""
    if "[" not in text:
        return text

    def repl(m: re.Match) -> str:
        inner = m.group(1).strip()
        low = inner.lower()
        if any(w in low for w in ("left", "right", "bilateral", "laterality")):
            return laterality or ""
        if "generic" in low or "region" in low or "body" in low:
            return region or ""
        if "/" in inner:  # unresolved option list -> first option
            return inner.split("/")[0].strip()
        return ""

    text = re.sub(r"\[([^\]]*)\]", repl, text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"\bthe\s+(?=[.,])", "", text)
    return cap_first(text.strip())
