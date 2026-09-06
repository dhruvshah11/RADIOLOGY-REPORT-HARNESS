"""Low-level text utilities shared by the whole pipeline.

Everything here is deterministic and dependency-free (stdlib only) so the
pipeline reproduces byte-identically on Kaggle, offline.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache

# ---------------------------------------------------------------- whitespace


def clean_ws(text: str) -> str:
    """Normalise unicode + collapse horizontal whitespace, keep newlines."""
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace(" ", " ").replace("–", "-").replace("—", "-")
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def squash(text: str) -> str:
    """Single-line, single-spaced version of a chunk of text."""
    return re.sub(r"\s+", " ", text or "").strip()


# ---------------------------------------------------------------- key forms

_NONWORD = re.compile(r"[^a-z0-9]+")


def key(text: str) -> str:
    """Aggressive normalisation used for equality / similarity comparisons."""
    return _NONWORD.sub(" ", (text or "").lower()).strip()


STOPWORDS = frozenset(
    """a an and are as at be been but by for from had has have in into is it its
    of on or that the there these this to was were with without which who whom
    within are demonstrates demonstrate shows show reveals reveal seen noted note
    identified appears appear present evident visualized visualised""".split()
)


def content_tokens(text: str) -> list[str]:
    return [t for t in key(text).split() if t not in STOPWORDS and len(t) > 2]


def token_set(text: str) -> frozenset[str]:
    return frozenset(content_tokens(text))


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def coverage(sub: frozenset, sup: frozenset) -> float:
    """Fraction of `sub` present in `sup`."""
    if not sub:
        return 0.0
    return len(sub & sup) / len(sub)


@lru_cache(maxsize=200_000)
def ratio(a: str, b: str) -> float:
    """Character-level similarity of two normalised strings."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def sim(a: str, b: str) -> float:
    return ratio(key(a), key(b))


# ---------------------------------------------------------------- sentences

_SENT_END = re.compile(r"(?<=[.;!?])\s+")
_DECIMAL = re.compile(r"(?<=\d)\.(?=\d)")
_ABBREVS = (
    "dr", "vs", "approx", "e.g", "i.e", "no", "cf", "etc", "mr", "ms", "st",
    "fig", "ca", "wk", "yr", "mo",
)
# telegraphic dictations frequently drop the full stop between sentences
_SENT_FINAL = (
    "seen|noted|identified|present|intact|maintained|preserved|unremarkable|"
    "normal|negative|patent|visualized|visualised|appreciated|demonstrated|observed"
)
_SENT_START = (
    "The|There|No|Mild|Moderate|Severe|Minimal|Small|Large|Normal|Multiple|"
    "Otherwise|Marked|Trace|Focal|Diffuse|Both|Overall|Findings|Impression|An?|"
    "At|Few|Multilevel|Visualized|Rest|Status|Post|Mildly|Grade"
)
# the space is optional: dictations contain run-ons such as "maintainedMinimal"
_MISSING_STOP = re.compile(rf"\b({_SENT_FINAL}) ?(?=(?:{_SENT_START})\b)")


def split_sentences(text: str) -> list[str]:
    """Split prose into sentences without breaking decimals or level labels."""
    if not text:
        return []
    guarded = _DECIMAL.sub("\x00", text)
    guarded = re.sub(r"\b([A-Z])\.(?=\s*[A-Z]\.)", lambda m: m.group(1) + "\x00", guarded)
    for ab in _ABBREVS:
        guarded = re.sub(
            rf"\b({re.escape(ab)})\.", lambda m: m.group(1) + "\x00", guarded, flags=re.I
        )
    out: list[str] = []
    for line in guarded.split("\n"):
        line = line.strip()
        if not line:
            continue
        for piece in _SENT_END.split(line):
            piece = piece.strip()
            if not piece:
                continue
            piece = _MISSING_STOP.sub(lambda m: m.group(1) + ".\x01", piece)
            for sub in piece.split("\x01"):
                sub = sub.strip()
                if sub:
                    out.append(sub.replace("\x00", "."))
    return out


def cap_first(text: str) -> str:
    """Upper-case the first alphabetic character, leave the rest untouched."""
    for i, ch in enumerate(text):
        if ch.isalpha():
            # do not lower-case ALLCAPS acronyms that already start the string
            return text[:i] + ch.upper() + text[i + 1 :]
        if ch not in "([\"' ":
            break
    return text


def end_period(text: str) -> str:
    text = text.rstrip()
    if not text:
        return text
    if text[-1] in ".;:!?":
        return text[:-1] + "." if text[-1] == ";" else text
    return text + "."


def tidy_sentence(text: str) -> str:
    """Canonical sentence rendering: trimmed, capitalised, single final period."""
    text = squash(text)
    text = re.sub(r"^[\-•*\d]+[\.\)]\s*", "", text)  # strip list bullets
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"\.{2,}", ".", text)
    if not text:
        return ""
    return end_period(cap_first(text))


# ---------------------------------------------------------------- distances


try:  # optional accelerator; the pure-python fallback gives identical results
    from rapidfuzz.distance import Levenshtein as _RF

    def levenshtein(a, b) -> int:
        return _RF.distance(a, b)

except Exception:  # pragma: no cover - Kaggle images ship rapidfuzz, but be safe
    def levenshtein(a, b) -> int:
        return _levenshtein_py(a, b)


def _levenshtein_py(a, b) -> int:
    """Edit distance over any two sequences (str or list of tokens)."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        ai = a[i - 1]
        for j in range(1, lb + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ai != b[j - 1]))
        prev = cur
    return prev[lb]
