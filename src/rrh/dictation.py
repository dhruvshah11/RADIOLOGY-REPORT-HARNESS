"""Dictation segmentation.

Turns a telegraphic dictation into structured `Segment`s, separating
   * technique / history / recommendation boilerplate (never reported),
   * the body of observations, and
   * a trailing radiologist summary (the dictated impression), which the
     reference reports reuse almost verbatim in IMPRESSION.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field

from .lexicon import correct_spelling, normalize_shorthand
from .textutil import clean_ws, content_tokens, jaccard, split_sentences, squash, token_set

CUE_VERB = re.compile(
    r"^(?P<cue>[A-Za-z][A-Za-z0-9 ,/&'\-\.]{1,45}?)\s+(?:shows?|demonstrates?|reveals?|"
    r"demonstrate|reveal)\s+(?P<rest>.+)$",
    re.I,
)
CUE_COLON = re.compile(r"^(?P<cue>[A-Za-z][A-Za-z0-9 ,/&'\-\.]{1,45}?)\s*:\s*(?P<rest>.+)$")
BARE_HEADER = re.compile(r"^(?P<cue>[A-Za-z][A-Za-z0-9 ,/&'\-\.]{1,45}?)\s*:\s*$")
LEVEL_RE = re.compile(r"\b([CTLS])\s*(\d{1,2})\s*[-–/]\s*(?:[CTLS])?\s*(\d{1,2}|S1)\b", re.I)

TECHNIQUE_PAT = re.compile(
    r"(was|were)\s+(performed|obtained|acquired)|"
    r"^(multiplanar|multisequence|multi-planar|axial|sagittal|coronal|sequences?|"
    r"technique|protocol|images?\s+were|imaging\s+was|scout|localizer|"
    r"post-?processed|reformat\w*|reconstruct\w*|magnetic\s+resonance|"
    r"computed\s+tomograph\w*|hrct\b|thin[- ]section)\b|"
    r"\b(radiograph|view|projection)s?\s+(of|were|was|obtained|acquired)\b|"
    r"^\s*(\d+|two|three|four|five|six|single|frontal|lateral|ap and lateral)[\w\- ]{0,25}"
    r"(views?|radiographs?|projections?)\b|"
    r"\b(without|with)\s+(intravenous|iv)\s+contrast\s*$|"
    r"^(contrast|comparison|indication|history|clinical\s+history|technique|exam(ination)?)\s*[:\-]",
    re.I,
)
HISTORY_PAT = re.compile(
    r"\b(pain|swelling|trauma|injury|fall|weakness|numbness|tingling|discomfort|"
    r"complaint|symptoms?)\s+(for|since|x)\s+\d|"
    r"^(clinical\s+)?(history|indication|hx)\b|"
    r"\b(rule\s+out|r/o)\b\s*$|"
    # "15-19-year-old with back pain (M54.9)." - age band, referral, ICD code
    r"\b\d{1,3}\s*(?:-\s*\d{1,3}\s*)?[- ]year[- ]old\b|"
    r"\(\s*[A-TV-Z]\d{2}(?:\.\d+)?\s*\)|"
    r"^(shortness of breath|sob|chest pain|back pain|abdominal pain|headache|fever)\b",
    re.I,
)
RECOMMEND_PAT = re.compile(
    r"^(recommendation|recommend(ed|s)?\b|correlate\s+clinic|"
    r"suggest\s+clinical|further\s+evaluation\s+with|"
    r"clinical\s+correlation\s+(is\s+)?(recommended|suggested|advised))",
    re.I,
)
ADVISED_PAT = re.compile(
    r"\b(is|are)\s+(advised|recommended|suggested|indicated)\b|"
    r"\bfor\s+further\s+(characteri[sz]ation|evaluation|assessment|workup)\b|"
    r"\bcorrelation\s+is\s+(advised|recommended|suggested)\b",
    re.I,
)
NONE_PAT = re.compile(
    r"^(none|n/?a|nil|not applicable)(\s+(available|provided|performed|obtained))?\s*\.?$|"
    r"^("
    r"(no\s+)?(prior|previous|comparison)s?(\s+(study|studies|exam\w*|imaging))?"
    r"(\s+(are|is|were|was))?(\s+(available|provided|performed))?)\s*\.?$",
    re.I,
)
MODALITY_HEADER = re.compile(
    r"^(mri|mr|ct|cta|mra|mrcp|us|usg|ultrasound|sonograph\w*|x-?ray|xr|radiograph\w*|"
    r"pet|dexa|fluoroscop\w*)\b",
    re.I,
)
CONTRAST_PAT = re.compile(
    r"\b(gadavist|gadolinium|gadobutrol|omnipaque|iohexol|ioversol|isovue|optiray|"
    r"ultravist|visipaque|contrast\s+material|contrast\s+agent)\b|"
    r"^\s*\w+\s+\d+(?:\.\d+)?\s*(?:ml|cc|mg)\s+(?:iv|i\.v\.)\b|"
    r"\b\d+(?:\.\d+)?\s*(?:ml|cc)\b[^.]{0,40}\b(administered|injected|intravenous(?:ly)?|"
    r"orally|per\s+oral)\b",
    re.I,
)
SYMPTOM_PAT = re.compile(
    r"\b(nausea|vomiting|headaches?|dizziness|vertigo|fever|chills|cough|dyspn(?:o?ea)|"
    r"seizures?|syncope|palpitations?|fatigue|malaise|tingling|paresthesias?|"
    r"restricted movement|difficulty|inability)\b",
    re.I,
)
ALLCAPS_HEADER = re.compile(r"^[A-Z0-9][A-Z0-9 /\-\(\)\.,&]{6,}$")
NORMAL_PAT = re.compile(
    r"^(normal|norml|nomal|normal study|unremarkable|nad|wnl|within normal limits?|"
    r"no abnormality|no acute abnormality|essentially normal|grossly normal)\s*\.?$",
    re.I,
)

GLOBAL_CONCL = re.compile(
    r"^(no acute|no significant|otherwise\s+(unremarkable|normal)|overall|"
    r"essentially\s+normal|unremarkable\s+(study|examination))\b.*"
    r"(abnormality|abnormalities|finding|study|examination|"
    r"\b(shoulder|knee|hip|wrist|ankle|elbow|hand|foot|spine|chest|abdomen|pelvis|"
    r"brain|head|neck|femur|humerus|skull|thorax)\b)",
    re.I,
)

NEG_LEAD = re.compile(
    r"^(no\b|not\b|without\b|absence of\b|negative for\b|there is no\b|there are no\b|"
    r"free of\b|unremarkable\b|normal\b|intact\b|preserved\b|maintained\b)",
    re.I,
)
NEG_ANY = re.compile(r"\b(no|not|without|negative for|absence of|free of)\b", re.I)
POS_HINT = re.compile(
    r"\b(mild|moderate|severe|small|large|minimal|marked|mild-to-moderate|"
    r"moderate-to-severe|trace|prominent|focal|diffuse|multiple|few|grade\s*[iv1-4]|"
    r"partial|complete|acute|chronic|degenerative|tear|fracture|effusion|edema|oedema|"
    r"stenosis|narrowing|osteophyte|bulge|herniation|opacity|consolidation|nodule|mass|"
    r"lesion|cyst|swelling|hypertrophy|spondylosis|tendinosis|bursitis|arthrosis|"
    r"arthritis|atrophy|thickening|calcification|sclerosis|deformity|dislocation|"
    r"collection|abnormal)\b",
    re.I,
)
LATERAL_RE = re.compile(r"\b(right|left|bilateral|rt|lt|b/l|bilat)\b", re.I)
MEASURE_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:x\s*\d+(?:\.\d+)?\s*)*(?:mm|cm|ml|cc)\b", re.I)


@dataclass
class Segment:
    text: str
    cue: str | None = None
    own_cue: bool = False  # the cue was written in this sentence, not inherited
    kind: str = "finding"  # finding | preamble | impression | normal
    negative: bool = False
    tokens: frozenset = dc_field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.tokens:
            self.tokens = token_set(self.text)
        self.negative = bool(NEG_LEAD.match(self.text)) and not POS_HINT.search(self.text)

    @property
    def laterality(self) -> str | None:
        m = LATERAL_RE.search(self.text)
        if not m:
            return None
        v = m.group(1).lower()
        return {"rt": "right", "lt": "left", "b/l": "bilateral", "bilat": "bilateral"}.get(v, v)


@dataclass
class DictationDoc:
    raw: str
    preamble: list[Segment]
    findings: list[Segment]
    impression: list[Segment]
    is_normal: bool

    @property
    def all_reportable(self) -> list[Segment]:
        return self.findings + self.impression


# A dictation that carries its own section layout ("Findings", "Kidneys",
# "Peritoneum/Retroperitoneum") leaks those bare headers in as findings.  On the
# training set 74 such segments appear and the reference keeps 4 of them (5.4%).
_HEADER_VERB = re.compile(
    r"\b(is|are|was|were|shows?|demonstrat\w*|seen|noted|identified|present|"
    r"reveals?|appears?|measur\w*|no|without|there|with|within)\b", re.I)
_HEADER_QUAL = re.compile(
    r"^(mild|moderate|severe|small|large|minimal|trace|focal|diffuse|multiple|normal|"
    r"prominent|stable|chronic|acute|mildly|grossly|few|early|advanced)\b", re.I)


def is_layout_header(sent: str) -> bool:
    """A bare section label from the dictation's own layout, not a finding."""
    t = sent.strip().rstrip(".").strip()
    words = t.split()
    if not 1 <= len(words) <= 4:
        return False
    if _HEADER_VERB.search(t) or _HEADER_QUAL.match(t) or re.search(r"\d", t):
        return False
    return t.isupper() or t == t.title() or t.endswith(":")


def _classify_boilerplate(sent: str, drop_layout_headers: bool = True) -> str | None:
    s = sent.strip()
    if NONE_PAT.match(s):
        return "preamble"
    if RECOMMEND_PAT.match(s) or ADVISED_PAT.search(s):
        return "preamble"
    if HISTORY_PAT.search(s):
        return "preamble"
    if TECHNIQUE_PAT.search(s):
        return "preamble"
    if ALLCAPS_HEADER.match(s) and not LEVEL_RE.search(s):
        return "preamble"
    if drop_layout_headers and is_layout_header(s) and not LEVEL_RE.search(s):
        return "preamble"
    if MODALITY_HEADER.match(s) and not POS_HINT.search(s) and not NEG_ANY.search(s):
        return "preamble"
    if CONTRAST_PAT.search(s) and len(content_tokens(s)) <= 8:
        return "preamble"
    if SYMPTOM_PAT.search(s) and len(content_tokens(s)) <= 6:
        return "preamble"
    return None


ARTICLE_LEAD = re.compile(r"^(the|a|an|there|this|these|those|it|his|her|their)\b", re.I)


def _strip_cue(sent: str) -> tuple[str | None, str, bool]:
    """Return (routing cue, sentence body).

    A *header* cue ("Bones shows ...", "Labrum: ...") is removed from the text,
    exactly as the reference reports do.  A cue that is really the subject of a
    normal sentence ("The medial meniscus demonstrates ...") is kept verbatim
    and only used for routing.
    """
    m = CUE_VERB.match(sent)
    if m:
        cue, rest = m.group("cue").strip(), m.group("rest").strip()
        if len(content_tokens(cue)) <= 6 and rest:
            if ARTICLE_LEAD.match(cue) or rest[:1].isupper():
                return cue, sent, False
            return cue, rest, True
    m = CUE_COLON.match(sent)
    if m:
        cue, rest = m.group("cue").strip(), m.group("rest").strip()
        if len(cue.split()) <= 6 and not re.search(r"[.!?]", cue) and rest:
            return cue, rest, True
    return None, sent, False


def _match_score(a: Segment, prior: list[Segment]) -> float:
    best = 0.0
    for p in prior:
        best = max(best, jaccard(a.tokens, p.tokens))
        if best >= 0.9:
            break
    return best


def _detect_summary(segs: list[Segment], threshold: float = 0.34, max_misses: int = 3,
                    after_cues: bool = False) -> int:
    """Index where the dictated impression starts (len(segs) if there is none).

    Two independent signals: a global conclusion sentence in the back part of
    the dictation, and a trailing run of sentences that restate earlier ones.
    """
    n = len(segs)
    if n < 4:
        return n
    body_limit = max(2, n // 3)
    # Section cues ("C5-6 shows ...", "Bones show ...") mark the body of the
    # dictation: a summary can only start after the last one.  Without this,
    # level-by-level spine dictations look like a repeated-sentence summary.
    last_cue = max((i for i, s in enumerate(segs) if s.own_cue), default=-1)
    body_limit = max(body_limit, last_cue + 1)
    if body_limit >= n - 1:
        return n
    if after_cues and last_cue >= 0 and n - (last_cue + 1) >= 2:
        # a structured dictation ends its cued sections and then summarises
        return last_cue + 1

    marker = n
    for i in range(body_limit, n - 1):
        if GLOBAL_CONCL.match(segs[i].text):
            marker = i
            break

    dup = n
    misses = 0
    for i in range(n - 1, body_limit - 1, -1):
        if _match_score(segs[i], segs[:i]) >= threshold:
            dup = i
            misses = 0
        else:
            misses += 1
            if misses > max_misses:
                break
    if dup >= n - 1:
        dup = n

    start = min(marker, dup)
    if start >= n - 1:
        return n
    while start > body_limit and GLOBAL_CONCL.match(segs[start - 1].text):
        start -= 1
    return start


def segment_dictation(
    raw: str,
    normalize: bool = True,
    vocab: dict[str, int] | None = None,
    summary_threshold: float = 0.34,
    summary_max_misses: int = 3,
    summary_after_cues: bool = False,
    drop_layout_headers: bool = True,
) -> DictationDoc:
    text = clean_ws(raw or "")
    if normalize:
        text = normalize_shorthand(text)
    if vocab:
        text = correct_spelling(text, vocab)
    if not text or NORMAL_PAT.match(squash(text)):
        return DictationDoc(raw=text, preamble=[], findings=[], impression=[], is_normal=True)

    sents = split_sentences(text)
    pre: list[Segment] = []
    body: list[Segment] = []
    carry_cue: str | None = None
    for s in sents:
        s = squash(s)
        if not s:
            continue
        kind = _classify_boilerplate(s, drop_layout_headers)
        if kind == "preamble":
            pre.append(Segment(text=s, kind="preamble"))
            continue
        if NORMAL_PAT.match(s):
            continue
        bare = BARE_HEADER.match(s)
        if bare:  # a section header on its own line: routing cue, not a finding
            carry_cue = bare.group("cue").strip()
            continue
        cue, rest, is_header = _strip_cue(s)
        _own = cue
        if is_header:
            carry_cue = cue
        elif carry_cue and not cue:
            cue = carry_cue
        body.append(Segment(text=squash(rest), cue=cue, own_cue=bool(cue) and cue == _own))
    # a cue must not leak into the dictated summary


    body = [b for b in body if content_tokens(b.text)]
    cut = _detect_summary(body, summary_threshold, summary_max_misses, summary_after_cues)
    findings, impression = body[:cut], body[cut:]
    for seg in impression:
        seg.kind = "impression"
    is_normal = not body
    return DictationDoc(
        raw=text, preamble=pre, findings=findings, impression=impression, is_normal=is_normal
    )
