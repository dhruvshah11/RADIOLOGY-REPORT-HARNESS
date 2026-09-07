"""Template editing: fold routed findings into the template's normal statements.

Guiding rule (RULE 2/3/6 of the task): replace only the normal statement that
the dictation contradicts, keep everything else byte-identical to the template.
"""
from __future__ import annotations

import re

from .lexicon import stem
from .splitting import split_negation
from .textutil import content_tokens, sim, split_sentences, squash, tidy_sentence

NEGATIVE_RE = re.compile(r"^\s*(no|there is no|there are no|without|negative for)\b", re.I)
NORMAL_STATE_RE = re.compile(
    r"\b(unremarkable|normal|intact|preserved|maintained|within normal limits|clear|"
    r"patent|not widened|no significant)\b",
    re.I,
)
BLANKET_RE = re.compile(
    r"^(the\s+)?[\w\s/-]{0,40}\s*(is|are)\s+(unremarkable|normal|preserved|maintained|"
    r"intact|clear|within normal (size )?limits?)\.?$",
    re.I,
)
FINITE_VERB = re.compile(
    r"\b(is|are|was|were|has|have|had|shows?|demonstrates?|reveals?|appears?|measures?|"
    r"noted|seen|identified|present|extends?|involves?|causes?|produces?|results?|"
    r"remains?|persists?|distends?|projects?)\b",
    re.I,
)
PLURAL_TAIL = re.compile(r"(?<![aiou])s$|(?<=[^s])es$", re.I)
PREPOSITION = re.compile(
    r"\b(of|in|at|along|about|within|with|involving|throughout|around|over|between)\b", re.I
)
LEADING_THERE = re.compile(r"^there\b", re.I)

COPULA_TAIL = re.compile(
    r"\s+(?:is|are|was|were)\s+(?:identified|seen|noted|present|evident|visualized|"
    r"visualised|appreciated|demonstrated|observed)\b",
    re.I,
)


def is_negative(sentence: str) -> bool:
    return bool(NEGATIVE_RE.match(sentence.strip()))


def negated_entities(sentence: str) -> list[str]:
    parts = split_negation(sentence)
    if not parts:
        m = re.match(r"^\s*(?:no|there is no|there are no)\s+(.+?)\s*[.]?$", sentence, re.I)
        return [m.group(1)] if m else []
    out = []
    for p in parts:
        m = re.match(r"^\s*No\s+(.+?)\s*[.]?$", p, re.I)
        if m:
            out.append(COPULA_TAIL.sub("", m.group(1)).strip())
    return out


def _stems(text: str) -> set[str]:
    return {stem(t) for t in content_tokens(text)}


def _asserted_positively(entity: str, routed: list[str]) -> bool:
    """Does any routed finding assert `entity` as present?"""
    ent = _stems(entity)
    if not ent:
        return False
    for r in routed:
        rs = _stems(r)
        if not rs:
            continue
        if len(ent & rs) / len(ent) < 0.7:
            continue
        if is_negative(r):
            # the routed sentence also negates it -> not a contradiction
            r_ents = negated_entities(r)
            if any(len(ent & _stems(e)) / len(ent) >= 0.7 for e in r_ents):
                continue
        return True
    return False


def _covered(sentence: str, routed: list[str], threshold: float) -> bool:
    st = _stems(sentence)
    if not st:
        return True
    union: set[str] = set()
    for r in routed:
        union |= _stems(r)
        if sim(sentence, r) >= 0.62:
            return True
    return len(st & union) / len(st) >= threshold


def _rebuild_negative(original: str, kept: list[str]) -> str:
    tail_m = COPULA_TAIL.search(original)
    tail = tail_m.group(0) if tail_m else ""
    if len(kept) == 1:
        body = kept[0]
    else:
        body = ", ".join(kept[:-1]) + " or " + kept[-1]
    return tidy_sentence(f"No {body}{tail}")


def _is_plural_head(text: str) -> bool:
    head = PREPOSITION.split(text, maxsplit=1)[0]
    if re.search(r"\band\b", head, re.I):
        return True
    for w in re.findall(r"[A-Za-z]+", head):
        low = w.lower()
        if low.endswith(("sis", "ss", "us", "is", "ous")):
            continue
        if PLURAL_TAIL.search(low):
            return True
    return False


def render_clause(text: str, cfg) -> str:
    """Render a routed dictation clause as a report sentence.

    Telegraphic noun phrases ("degenerative changes in left shoulder") are given
    the existential frame the reference reports use ("There are degenerative
    changes in the left shoulder.").  No content is added.
    """
    t = squash(text)
    verbless = t and not FINITE_VERB.search(t) and not NEGATIVE_RE.match(t)
    if verbless and not LEADING_THERE.match(t):
        if cfg.add_existential:
            t = f"There {'are' if _is_plural_head(t) else 'is'} {t[0].lower() + t[1:]}"
        elif cfg.add_copula:
            t = f"{t.rstrip('.')} {'are' if _is_plural_head(t) else 'is'} present"
    return tidy_sentence(t)


def _redundant_with_template(clause: str, tmpl_sents: list[str]) -> bool:
    """True when the template already says this, in its own words (RULE 6)."""
    c_ents = negated_entities(clause)
    c_st = _stems(clause)
    if not c_st:
        return True
    for ts in tmpl_sents:
        if sim(clause, ts) >= 0.55:
            return True
        if not is_negative(ts):
            continue
        t_ents = negated_entities(ts)
        if not c_ents or not t_ents:
            continue
        t_all = set()
        for e in t_ents:
            t_all |= _stems(e)
        if all(
            _stems(e) and len(_stems(e) & t_all) / len(_stems(e)) >= 0.7 for e in c_ents
        ):
            return True
    return False


def filter_redundant(routed: list[str], template_text: str, cfg) -> list[str]:
    """Drop dictated clauses that merely restate a template normal statement."""
    if not cfg.suppress_redundant_negatives or not routed:
        return routed
    tmpl_sents = split_sentences(template_text)
    if not tmpl_sents:
        return routed
    out = []
    for r in routed:
        negative = is_negative(r)
        normalish = bool(NORMAL_STATE_RE.search(r))
        if (negative or (cfg.suppress_redundant_normals and normalish)) and (
            _redundant_with_template(r, tmpl_sents)
        ):
            continue
        out.append(r)
    return out


MEASURE_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:x\s*\d+(?:\.\d+)?\s*)*(?:mm|cm|ml|cc)\b", re.I)


def dedupe_clauses(routed: list[str], threshold: float) -> list[str]:
    """Drop a clause the field already states (dictated per-level summaries).

    A clause carrying a measurement the field does not have yet is always kept:
    de-duplication must never silently lose a number.
    """
    kept: list[str] = []
    for r in routed:
        st = _stems(r)
        if st:
            prev_text = " ".join(kept)
            prev = _stems(prev_text)
            new_measures = {
                m.group(0).lower().replace(" ", "") for m in MEASURE_RE.finditer(r)
            } - {m.group(0).lower().replace(" ", "") for m in MEASURE_RE.finditer(prev_text)}
            if not new_measures and (
                len(st & prev) / len(st) >= threshold or any(sim(r, k) >= 0.7 for k in kept)
            ):
                continue
        kept.append(r)
    return kept


def edit_field(template_text: str, routed: list[str], cfg) -> str:
    """Return the new body for one field."""
    if cfg.dedupe_threshold:
        routed = dedupe_clauses(routed, cfg.dedupe_threshold)
    routed = filter_redundant(routed, template_text, cfg)
    if not routed:
        return template_text
    kept: list[str] = []
    for ts in split_sentences(template_text):
        if is_negative(ts):
            ents = negated_entities(ts)
            if ents:
                survivors = [e for e in ents if not _asserted_positively(e, routed)]
                if not survivors:
                    continue
                if len(survivors) < len(ents):
                    kept.append(_rebuild_negative(ts, survivors))
                    continue
            if _covered(ts, routed, cfg.cover_threshold):
                continue
            kept.append(ts)
        else:
            if _covered(ts, routed, cfg.cover_threshold):
                continue
            if cfg.soften_blanket and BLANKET_RE.match(ts) and any(
                not is_negative(r) for r in routed
            ):
                kept.append(_soften(ts))
            else:
                kept.append(ts)
    ordered = routed
    if cfg.abnormal_first:
        pos = [r for r in routed if not is_negative(r) and not NORMAL_STATE_RE.search(r)]
        rest = [r for r in routed if r not in pos]
        ordered = pos + rest
    body = " ".join(render_clause(r, cfg) for r in ordered if squash(r))
    if kept:
        body = (body + " " + " ".join(tidy_sentence(k) for k in kept)).strip()
    return squash(body)


def _soften(sentence: str) -> str:
    s = sentence
    s = re.sub(r"^The\s+", "The remaining ", s, count=1)
    s = re.sub(r"\s+(is|are)\s+", lambda m: f" {m.group(1)} otherwise ", s, count=1)
    return tidy_sentence(s)
