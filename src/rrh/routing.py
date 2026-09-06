"""Field routing: decide which template field each dictated finding belongs to.

Signals, in decreasing order of trust:
  1. an explicit dictation cue ("Bones shows ...", "L4-L5: ...")
  2. the field label itself appearing in the finding
  3. curated anatomy->field concepts (`lexicon.py`)
  4. overlap with the field's own normal statement in the template
  5. statistics mined from the training reports

The mined statistics are fitted only on training rows, so the evaluation can
hold folds out honestly.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field as dc_field

from .lexicon import body_region, concept_for_label, concept_hits, stem
from .template import Template, parse_template
from .textutil import content_tokens, key, sim, split_sentences, squash

MINE_THRESHOLD = 0.5

LEVEL_RE = re.compile(r"^([ctls])\s*(\d{1,2})\s*[-/]\s*(?:([ctls])\s*)?(\d{1,2}|s1)$", re.I)

# Reporting verbs and connectives a reference sentence may add without adding
# any clinical content.
NEUTRAL_STEMS = {
    stem(w)
    for w in (
        "present", "noted", "seen", "identified", "evident", "demonstrated", "observed",
        "visualized", "visualised", "appreciated", "there", "remaining", "otherwise",
        "again", "also", "overall", "appears", "appear", "the", "are", "is", "which",
    )
}


def normalize_level(label: str) -> str | None:
    lab = key(label).replace(" ", "")
    lab = re.sub(r"^([ctls])(\d{1,2})([ctls])?(\d{1,2})$", r"\1\2-\4", lab)
    m = LEVEL_RE.match(lab.replace(" ", ""))
    if not m:
        m = LEVEL_RE.match(re.sub(r"([a-z])(\d+)-([a-z]?)(\d+)", r"\1\2-\4", lab))
    if not m:
        return None
    a, n1, _, n2 = m.groups()
    return f"{a.lower()}{int(n1)}-{n2.lower() if not n2.isdigit() else int(n2)}"


def label_tokens(label: str) -> set[str]:
    return {stem(t) for t in content_tokens(label)}


def _label_match(text: str, label: str, weights: dict[str, float] | None = None) -> float:
    """How strongly does `text` name `label`?"""
    if not label:
        return 0.0
    lv, tv = normalize_level(label), normalize_level(text)
    if lv and tv:
        return 1.0 if lv == tv else 0.0
    if lv and not tv:
        toks = re.findall(r"\b[ctls]\s*\d{1,2}\s*[-/]\s*[ctls]?\s*(?:\d{1,2}|s1)\b", key(text))
        if any(normalize_level(t) == lv for t in toks):
            return 1.0
        return 0.0
    lt = label_tokens(label)
    if not lt:
        return 0.0
    tt = {stem(t) for t in content_tokens(text)}
    if not tt:
        return 0.0
    if weights:
        num = sum(weights.get(t, 1.0) for t in sorted(lt & tt))
        den = sum(weights.get(t, 1.0) for t in sorted(lt)) or 1.0
        return min(1.0, num / den)
    return len(lt & tt) / len(lt)


@dataclass
class RegionStats:
    """Mined (token -> field) statistics for one coarse body region."""

    token_label: dict[str, Counter] = dc_field(default_factory=lambda: defaultdict(Counter))
    label_total: Counter = dc_field(default_factory=Counter)
    token_total: Counter = dc_field(default_factory=Counter)
    n_pairs: int = 0
    postings: dict[str, list[int]] = dc_field(default_factory=lambda: defaultdict(list))
    examples: list[tuple[frozenset, str]] = dc_field(default_factory=list)

    def add(self, toks: set[str], label: str) -> None:
        self.n_pairs += 1
        self.label_total[label] += 1
        idx = len(self.examples)
        self.examples.append((frozenset(toks), label))
        for t in sorted(toks):
            self.token_label[t][label] += 1
            self.token_total[t] += 1
            self.postings[t].append(idx)

    def score(self, tokens: set[str], label: str) -> float:
        if label not in self.label_total or not tokens:
            return 0.0
        total = self.label_total[label]
        acc = 0.0
        for t in sorted(tokens):
            c = self.token_label.get(t)
            if not c:
                continue
            p_t_l = c.get(label, 0) / total
            p_t = self.token_total[t] / max(1, self.n_pairs)
            if p_t_l > 0:
                acc += math.log((p_t_l + 1e-4) / (p_t + 1e-4))
        return max(0.0, min(1.0, acc / (2.0 * max(1, len(tokens)))))

    def knn(self, tokens: set[str], allowed: set[str], k: int = 12) -> dict[str, float]:
        if not tokens or not self.examples:
            return {}
        cand: Counter = Counter()
        for t in sorted(tokens):
            for i in self.postings.get(t, ()):  # type: ignore[arg-type]
                cand[i] += 1
        if not cand:
            return {}
        scored = []
        for i, _ in sorted(cand.items(), key=lambda kv: (-kv[1], kv[0]))[:120]:
            etoks, label = self.examples[i]
            if label not in allowed:
                continue
            inter = len(tokens & etoks)
            if not inter:
                continue
            scored.append((inter / len(tokens | etoks), label))
        scored.sort(reverse=True)
        votes: dict[str, float] = {}
        tot = 0.0
        for j, label in sorted(scored[:k]):
            votes[label] = votes.get(label, 0.0) + j
            tot += j
        return {lab: v / tot for lab, v in votes.items()} if tot > 0 else {}


@dataclass
class RoutingModel:
    token_label: dict[str, Counter] = dc_field(default_factory=lambda: defaultdict(Counter))
    label_total: Counter = dc_field(default_factory=Counter)
    token_total: Counter = dc_field(default_factory=Counter)
    n_pairs: int = 0

    postings: dict[str, list[int]] = dc_field(default_factory=lambda: defaultdict(list))
    examples: list[tuple[frozenset, str]] = dc_field(default_factory=list)
    vocab: dict[str, int] = dc_field(default_factory=dict)
    ranker: object | None = None
    chooser: object | None = None
    regions: dict[str, RegionStats] = dc_field(default_factory=dict)
    use_bigrams: bool = False
    mine_threshold: float = MINE_THRESHOLD
    region_weight: float = 0.0
    field_edits: dict[tuple[str, str], tuple[int, int]] = dc_field(default_factory=dict)
    label_edits: dict[str, tuple[int, int]] = dc_field(default_factory=dict)
    global_edit_rate: float = 0.35

    def edit_prior(self, tkey: str, label: str, alpha: float = 2.0) -> float:
        """How often the reference edits this field of this template."""
        lab_e, lab_n = self.label_edits.get(label, (0, 0))
        backoff = (lab_e + alpha * self.global_edit_rate) / (lab_n + alpha)
        e, n = self.field_edits.get((tkey, label), (0, 0))
        return (e + alpha * backoff) / (n + alpha)
    style_examples: list[tuple[frozenset, str, str]] = dc_field(default_factory=list)
    style_postings: dict[str, list[int]] = dc_field(default_factory=lambda: defaultdict(list))

    def style_match(self, clause: str, threshold: float) -> str | None:
        """Closest training clause->reported-sentence rewrite, if it is safe.

        "Safe" means the reference sentence introduces no content word that the
        clause does not already have (apart from neutral reporting verbs), so
        this transfers phrasing only - never a finding.
        """
        toks = {stem(t) for t in content_tokens(clause)}
        if not toks or not self.style_examples:
            return None
        cand: Counter = Counter()
        for t in sorted(toks):
            for i in self.style_postings.get(t, ()):  # type: ignore[arg-type]
                cand[i] += 1
        best, best_s = None, 0.0
        for i, _ in sorted(cand.items(), key=lambda kv: (-kv[1], kv[0]))[:60]:
            etoks, src, tgt = self.style_examples[i]
            j = len(toks & etoks) / len(toks | etoks)
            if j < threshold:
                continue
            score = j + 0.001 * len(etoks)
            if score > best_s:
                best, best_s = (src, tgt), score
        if not best:
            return None
        _, target = best
        extra = {stem(t) for t in content_tokens(target)} - toks - NEUTRAL_STEMS
        if extra:
            return None
        return target

    def knn(self, tokens: set[str], allowed: set[str], k: int = 12) -> dict[str, float]:
        """Similarity-weighted vote of the closest mined training sentences."""
        if not tokens or not self.examples:
            return {}
        cand: Counter = Counter()
        for t in sorted(tokens):
            for i in self.postings.get(t, ()):  # type: ignore[arg-type]
                cand[i] += 1
        if not cand:
            return {}
        scored = []
        for i, _ in sorted(cand.items(), key=lambda kv: (-kv[1], kv[0]))[:120]:
            etoks, label = self.examples[i]
            if label not in allowed:
                continue
            inter = len(tokens & etoks)
            if not inter:
                continue
            j = inter / len(tokens | etoks)
            scored.append((j, label))
        scored.sort(reverse=True)
        votes: dict[str, float] = {}
        tot = 0.0
        for j, label in sorted(scored[:k]):
            votes[label] = votes.get(label, 0.0) + j
            tot += j
        if tot <= 0:
            return {}
        return {lab: v / tot for lab, v in votes.items()}

    def score(self, tokens: set[str], label: str) -> float:
        if label not in self.label_total or not tokens:
            return 0.0
        total = self.label_total[label]
        acc = 0.0
        for t in sorted(tokens):
            c = self.token_label.get(t)
            if not c:
                continue
            p_t_l = c.get(label, 0) / total
            p_t = self.token_total[t] / max(1, self.n_pairs)
            if p_t_l > 0:
                acc += math.log((p_t_l + 1e-4) / (p_t + 1e-4))
        return max(0.0, min(1.0, acc / (2.0 * max(1, len(tokens)))))


def mine_row(row, threshold: float = MINE_THRESHOLD) -> list[tuple[int, str, str, str]]:
    """(segment index, segment text, gold field label, reference sentence)."""
    from .dictation import segment_dictation

    tmpl = parse_template(row["template_content"])
    rep = parse_template(row["report"])
    doc = segment_dictation(row["dictation"])
    units = doc.findings or doc.impression
    if not units:
        return []
    tmpl_by_label = {f.label: f for f in tmpl.fields}
    out: list[tuple[int, str, str]] = []
    used: set[int] = set()
    for rf in rep.fields:
        if not rf.label:
            continue
        tf = tmpl_by_label.get(rf.label)
        tmpl_sents = tf.sentences if tf else []
        for rs in split_sentences(rf.text):
            if any(sim(rs, ts) >= 0.85 for ts in tmpl_sents):
                continue
            best, best_s = -1, 0.0
            for i, u in enumerate(units):
                s = sim(rs, u.text)
                if s > best_s:
                    best, best_s = i, s
            if best >= 0 and best_s >= threshold and best not in used:
                used.add(best)
                out.append((best, units[best].text, rf.label, rs))
    return out


def mine_pairs(rows) -> list[tuple[str, str]]:
    """(dictated sentence, report field label) supervision mined from train rows."""
    return [(text, label) for row in rows for _, text, label, _ in mine_row(row)]


def token_repr(text: str, bigrams: bool = False) -> set[str]:
    """Stemmed unigrams, optionally with adjacent-pair features.

    Bigrams disambiguate terms whose field depends on their neighbour
    ("joint effusion" vs "pleural effusion").
    """
    toks = [stem(t) for t in content_tokens(text)]
    out = set(toks)
    if bigrams:
        out |= {f"{a}_{b}" for a, b in zip(toks, toks[1:])}
    return out


def fit_router(rows, cfg=None) -> RoutingModel:
    from .lexicon import build_vocabulary

    model = RoutingModel()
    if cfg is not None:
        model.use_bigrams = getattr(cfg, "use_bigrams", False)
        model.mine_threshold = getattr(cfg, "mine_threshold", MINE_THRESHOLD)
    model.vocab = build_vocabulary(
        [r.get("report") or "" for r in rows] + [r.get("template_content") or "" for r in rows]
    )
    edited: dict[tuple[str, str], list[int]] = {}
    lab_edit: dict[str, list[int]] = {}
    tot_e = tot_n = 0
    for row in rows:
        tkey = template_key(row.get("template_content") or "")
        tmpl_fields = {f.label: squash(f.text) for f in parse_template(row["template_content"]).fields if f.label}
        rep_fields = {f.label: squash(f.text) for f in parse_template(row["report"]).fields if f.label}
        for lab, txt in tmpl_fields.items():
            changed = int(rep_fields.get(lab, "") != txt)
            edited.setdefault((tkey, lab), [0, 0])
            edited[(tkey, lab)][0] += changed
            edited[(tkey, lab)][1] += 1
            lab_edit.setdefault(lab, [0, 0])
            lab_edit[lab][0] += changed
            lab_edit[lab][1] += 1
            tot_e += changed
            tot_n += 1
    model.field_edits = {k: (v[0], v[1]) for k, v in edited.items()}
    model.label_edits = {k: (v[0], v[1]) for k, v in lab_edit.items()}
    model.global_edit_rate = tot_e / max(1, tot_n)

    pairs: list[tuple[str, str]] = []
    for row in rows:
        region = body_region(
            str(row.get("body_part") or ""), str(row.get("study_description") or "")
        )
        for _, text, label, ref_sentence in mine_row(row, model.mine_threshold):
            pairs.append((text, label))
            rtoks = token_repr(text, model.use_bigrams)
            if rtoks:
                model.regions.setdefault(region, RegionStats()).add(rtoks, label)
            toks = frozenset(token_repr(text, model.use_bigrams))
            if not toks:
                continue
            idx = len(model.style_examples)
            model.style_examples.append((toks, text, ref_sentence))
            for t in toks:
                model.style_postings[t].append(idx)
    for text, label in pairs:
        toks = token_repr(text, model.use_bigrams)
        if not toks:
            continue
        model.n_pairs += 1
        model.label_total[label] += 1
        idx = len(model.examples)
        model.examples.append((frozenset(toks), label))
        for t in toks:
            model.token_label[t][label] += 1
            model.token_total[t] += 1
            model.postings[t].append(idx)
    return model


WEIGHTS = {
    "cue": 3.0,
    "label": 2.2,
    "concept": 1.2,
    "template": 1.0,
    "mined": 1.2,
    "knn": 1.6,
    "continuity": 0.0,
    "backward": 0.0,
    "prior": 0.0,
}
MIN_SCORE = 0.30


def field_candidates(tmpl: Template):
    return [f for f in tmpl.fields if f.label and not f.is_free and f.label != "OTHER FINDINGS"]


def cue_supported(cue: str | None, tmpl: Template, ctx: "TemplateContext",
                  minimum: float = 0.34) -> bool:
    """Does any field of this template correspond to the dictation's cue?

    When the radiologist dictates "Brain shows ..." but the template has no
    brain field, the finding belongs to no field at all - the reference reports
    put it in a trailing paragraph rather than forcing it into a wrong field.
    """
    if not cue:
        return True
    hits = concept_hits(cue)
    for f in field_candidates(tmpl):
        if _label_match(cue, f.label, ctx.label_weights) >= minimum:
            return True
        concept = concept_for_label(f.label)
        if concept and concept in hits:
            return True
    return False


FEATURES = (
    "cue", "label", "concept", "template", "mined", "knn",
    "group", "same_prev", "backward", "forward", "prior",
)


def template_key(text: str) -> str:
    import hashlib

    return hashlib.sha256(key(text).encode()).hexdigest()[:16]


def field_features(seg_text: str, cue: str | None, tmpl: Template, model: RoutingModel,
                   ctx: "TemplateContext",
                   prev_order: int | None = None) -> list[tuple[str, dict[str, float]]]:
    """Per-candidate-field feature vector for one dictated clause.

    The same features drive the hand-weighted scorer and the learned ranker, so
    the two are directly comparable.
    """
    idf, lw = ctx.idf, ctx.label_weights
    toks = token_repr(seg_text, model.use_bigrams)
    hits = concept_hits(seg_text)
    tot_hits = sum(hits.values())
    cands = field_candidates(tmpl)
    allowed = {f.label for f in cands}
    knn = model.knn(toks, allowed)
    reg = model.regions.get(ctx.region) if model.region_weight else None
    if reg is not None and reg.n_pairs >= 50:
        lam = model.region_weight
        reg_knn = reg.knn(toks, allowed)
        knn = {
            lab: (1 - lam) * knn.get(lab, 0.0) + lam * reg_knn.get(lab, 0.0)
            for lab in allowed
        }
    else:
        reg = None
    span = max(1, len(tmpl.fields) - 1)
    out: list[tuple[str, dict[str, float]]] = []
    for f in cands:
        feat = {k: 0.0 for k in FEATURES}
        if cue:
            feat["cue"] = _label_match(cue, f.label, lw)
        feat["label"] = _label_match(seg_text, f.label, lw)
        concept = concept_for_label(f.label)
        if concept and tot_hits:
            feat["concept"] = hits.get(concept, 0) / tot_hits
        if f.text:
            ft = {stem(t) for t in content_tokens(f.text)}
            if ft and toks:
                num = sum(idf.get(t, 1.0) for t in sorted(ft & toks))
                den = sum(idf.get(t, 1.0) for t in sorted(ft)) or 1.0
                feat["template"] = min(1.0, num / den)
        feat["mined"] = model.score(toks, f.label)
        if reg is not None:
            lam = model.region_weight
            feat["mined"] = (1 - lam) * feat["mined"] + lam * reg.score(toks, f.label)
        feat["knn"] = knn.get(f.label, 0.0)
        feat["group"] = 1.0 if f.is_group else 0.0
        feat["prior"] = model.edit_prior(ctx.template_key, f.label)
        if prev_order is not None:
            if f.order == prev_order:
                feat["same_prev"] = 1.0
            elif f.order < prev_order:
                feat["backward"] = min(1.0, (prev_order - f.order) / span)
            else:
                feat["forward"] = min(1.0, (f.order - prev_order) / span)
        out.append((f.label, feat))
    return out


def score_segment(seg_text: str, cue: str | None, tmpl: Template, model: RoutingModel,
                  ctx: "TemplateContext",
                  weights: dict[str, float] | None = None,
                  prev_order: int | None = None) -> list[tuple[float, str]]:
    """Score every candidate field for one dictated clause.

    `prev_order` is the template position of the field the previous clause went
    to.  Radiologists dictate in template order - 52% of consecutive findings
    stay in the same field and 85% never move backwards - so continuity is a
    real signal, not a heuristic.
    """
    W = weights or WEIGHTS
    scored: list[tuple[float, str]] = []
    for label, feat in field_features(seg_text, cue, tmpl, model, ctx, prev_order):
        if model.ranker is not None and W.get("use_ranker"):
            s = model.ranker.score(feat)
        else:
            s = (
                W["cue"] * feat["cue"]
                + W["label"] * feat["label"]
                + W["concept"] * feat["concept"]
                + W["template"] * feat["template"]
                + W["mined"] * feat["mined"]
                + W["knn"] * feat["knn"]
                + W.get("prior", 0.0) * feat["prior"]
                + W.get("continuity", 0.0) * feat["same_prev"]
                - W.get("backward", 0.0) * feat["backward"]
            )
        scored.append((s, label))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored


@dataclass
class TemplateContext:
    idf: dict[str, float]
    label_weights: dict[str, float]
    template_key: str = ""
    region: str = "other"


def build_context(tmpl: Template, region: str = "other") -> TemplateContext:
    """Rarity weights computed over the template's own fields and labels:
    a word that occurs in only one field/label is decisive for that field."""
    fields = field_candidates(tmpl)
    n = max(1, len(fields))
    df: Counter = Counter()
    for f in fields:
        for t in {stem(x) for x in content_tokens(f.text)}:
            df[t] += 1
    idf = {t: math.log((n + 1) / (c + 0.5)) for t, c in df.items()}

    ldf: Counter = Counter()
    for f in fields:
        for t in label_tokens(f.label):
            ldf[t] += 1
    lw = {t: math.log((n + 1) / (c + 0.5)) for t, c in ldf.items()}
    # generic label words carry little routing information
    for generic in ("structure", "space", "tissu", "other", "finding", "region", "gener"):
        for t in list(lw):
            if t.startswith(generic):
                lw[t] = min(lw[t], 0.3)
    return TemplateContext(
        idf=idf, label_weights=lw, template_key=template_key(tmpl.raw), region=region
    )


# backwards-compatible helper
def build_idf(tmpl: Template) -> TemplateContext:
    return build_context(tmpl)


def fit_ranked_router(rows, cfg) -> RoutingModel:
    """Fit the mined statistics, then fit the learned router on top of them."""
    from .ranker import build_examples, fit_ranker

    model = fit_router(rows, cfg)
    model.region_weight = getattr(cfg, "region_weight", 0.0)
    if getattr(cfg, "use_impression_chooser", False):
        from .chooser import build_training_rows, fit_chooser

        model.chooser = fit_chooser(
            build_training_rows(rows, model, cfg), depth=cfg.chooser_depth
        )
    if getattr(cfg, "use_ranker", False):
        model.ranker = fit_ranker(
            build_examples(rows, model, cfg),
            epochs=cfg.ranker_epochs,
            lr=cfg.ranker_lr,
            l2=cfg.ranker_l2,
        )
    return model
