"""Curated radiology knowledge used to route findings to template fields.

Kept small and explicit: it encodes *which anatomical field a term belongs to*,
never what a finding means clinically.  Nothing here invents content.
"""
from __future__ import annotations

import re

# canonical field concept -> terms that belong to that field
CONCEPT_TERMS: dict[str, tuple[str, ...]] = {
    "BONES": (
        "bone", "bones", "osseous", "fracture", "marrow", "cortex", "cortical",
        "lytic", "blastic", "sclerotic", "osteopenia", "osteoporosis", "mineralization",
        "vertebral body", "vertebral bodies", "endplate", "spondylosis", "spur",
        "osteophyte", "avulsion", "periosteal", "bone island", "enchondroma",
        "acromion", "tuberosity", "condyle", "malleolus", "calcaneus", "scaphoid",
        "clavicle", "rib", "sternum", "pedicle", "spinous process", "odontoid",
    ),
    "JOINTS": (
        "joint", "joints", "joint space", "articular", "dislocation", "subluxation",
        "arthrosis", "arthritis", "osteoarthrosis", "osteoarthritis", "degenerative change",
        "alignment", "effusion", "facet", "sacroiliac", "acromioclavicular",
        "glenohumeral", "carpometacarpal", "interphalangeal", "metacarpophalangeal",
    ),
    "SOFT TISSUES": (
        "soft tissue", "soft tissues", "swelling", "cellulitis", "edema", "oedema",
        "foreign body", "subcutaneous", "hematoma", "seroma", "abscess", "lipoma",
        "phlebolith", "calcified lymph node", "fat pad", "ganglion",
    ),
    "MUSCLES": (
        "muscle", "muscles", "musculature", "atrophy", "fatty infiltration",
        "myotendinous", "strain", "bulk",
    ),
    "TENDONS": (
        "tendon", "tendons", "tendinosis", "tendinopathy", "tendinitis", "tenosynovitis",
        "supraspinatus", "infraspinatus", "subscapularis", "teres minor", "biceps",
        "achilles", "peroneal", "quadriceps", "patellar tendon", "rotator cuff",
    ),
    "LIGAMENTS": (
        "ligament", "ligaments", "ligamentous", "cruciate", "collateral", "acl", "pcl",
        "mcl", "lcl", "lisfranc", "spring ligament", "deltoid ligament", "retinaculum",
        "syndesmosis", "talofibular",
    ),
    "MENISCI": ("meniscus", "menisci", "meniscal", "bucket-handle", "mucoid degeneration"),
    "CARTILAGE": ("cartilage", "chondral", "chondromalacia", "osteochondral"),
    "BURSAE": ("bursa", "bursae", "bursitis", "subacromial", "subdeltoid", "prepatellar"),
    "NERVES": ("nerve", "nerves", "neuroma", "median nerve", "ulnar nerve", "sciatic"),
    "LUNGS": (
        "lung", "lungs", "pulmonary", "airspace", "air-space", "consolidation",
        "opacity", "infiltrate", "atelectasis", "nodule", "emphysema", "bronchiectasis",
        "interstitial", "edema", "reticular", "ground-glass", "airway", "bronch",
    ),
    "PLEURA": ("pleura", "pleural", "effusion", "pneumothorax", "pleural thickening"),
    "HEART": ("heart", "cardiac", "cardiomegaly", "cardiac silhouette"),
    "MEDIASTINUM": (
        "mediastinum", "mediastinal", "hilum", "hila", "hilar", "aorta", "aortic",
        "great vessel", "trachea",
    ),
    "DIAPHRAGM": ("diaphragm", "diaphragmatic", "hemidiaphragm", "subdiaphragmatic", "free air"),
    "SUPPORT DEVICES": (
        "line", "tube", "catheter", "pacemaker", "device", "stent", "port",
        "endotracheal", "picc", "drain", "hardware", "screw", "plate", "prosthesis",
    ),
    "LIVER": ("liver", "hepatic", "hepatomegaly", "steatosis", "fatty liver"),
    "GALLBLADDER": ("gallbladder", "gallstone", "cholelithiasis", "biliary", "cbd"),
    "KIDNEYS": ("kidney", "kidneys", "renal", "hydronephrosis", "calculus", "nephrolithiasis"),
    "SPLEEN": ("spleen", "splenic", "splenomegaly"),
    "PANCREAS": ("pancreas", "pancreatic"),
    "BLADDER": ("bladder", "urinary bladder", "vesical"),
    "BOWEL": ("bowel", "colon", "small bowel", "ileus", "obstruction", "appendix"),
    "UTERUS": ("uterus", "uterine", "endometrium", "endometrial", "myometrium", "fibroid"),
    "OVARIES": ("ovary", "ovaries", "adnexa", "adnexal", "follicle"),
    "PROSTATE": ("prostate", "prostatic", "seminal vesicle"),
    "BRAIN": (
        "brain", "cerebral", "cerebellum", "parenchyma", "white matter", "gray matter",
        "infarct", "hemorrhage", "midline shift", "ventricle", "ventricular", "gliosis",
        "encephalomalacia", "mass effect",
    ),
    "SPINAL CORD": ("cord", "spinal cord", "myelomalacia", "syrinx", "cord signal"),
    "DISC": (
        "disc", "disk", "herniation", "protrusion", "extrusion", "bulge", "annular",
        "desiccation", "canal stenosis", "foraminal", "thecal sac", "osteophyte complex",
    ),
    "ALIGNMENT": (
        "alignment", "lordosis", "kyphosis", "scoliosis", "spondylolisthesis",
        "listhesis", "curvature", "straightening",
    ),
    "VESSELS": ("artery", "arterial", "vein", "venous", "stenosis", "aneurysm", "thrombus"),
    "SINUSES": ("sinus", "sinuses", "maxillary", "ethmoid", "sphenoid", "frontal sinus", "mucosal",
                "mastoid", "mastoiditis", "mastoid air cells"),
    "BILIARY": ("bile duct", "biliary", "cbd", "common bile duct", "common hepatic duct",
                "choledocholithiasis", "intrahepatic biliary", "biliary radicle",
                "biliary dilatation", "biliary stricture"),
    "PANCREATIC DUCT": ("pancreatic duct", "duct of wirsung", "main pancreatic duct"),
    "URETERS": ("ureter", "ureters", "ureteric", "ureteral", "hydroureter",
                "hydroureteronephrosis", "ureterovesical", "collecting system"),
    "SPINAL CANAL": ("spinal canal", "canal stenosis", "ap diameter", "central canal",
                     "canal diameter", "thecal"),
    "DISC SPACES": ("disc space", "disc height", "intervertebral", "disc space narrowing"),
    "NEURAL FORAMINA": ("neural foramen", "neural foramina", "foraminal", "foramina"),
    "FACET JOINTS": ("facet", "facets", "facet joint", "facet arthropathy", "zygapophyseal"),
    "ORBITS": ("orbit", "orbits", "globe", "optic nerve", "extraocular"),
}

# template label (upper-cased) -> canonical concept
LABEL_ALIASES: dict[str, str] = {
    "BONE": "BONES", "BONES": "BONES", "OSSEOUS STRUCTURES": "BONES",
    "OSSEOUS": "BONES", "BONES AND JOINTS": "BONES", "SKELETAL": "BONES",
    "VERTEBRAL BODIES": "BONES", "VERTEBRAL BODIES AND ALIGNMENT": "BONES",
    "OSSEOUS STRUCTURES AND ALIGNMENT": "BONES", "BONY STRUCTURES": "BONES",
    "JOINT": "JOINTS", "JOINTS": "JOINTS", "JOINT SPACES": "JOINTS",
    "JOINT SPACES AND ALIGNMENT": "JOINTS", "ARTICULATIONS": "JOINTS",
    "SOFT TISSUE": "SOFT TISSUES", "SOFT TISSUES": "SOFT TISSUES",
    "PARAVERTEBRAL SOFT TISSUES": "SOFT TISSUES", "PARASPINAL SOFT TISSUES": "SOFT TISSUES",
    "SURROUNDING SOFT TISSUES": "SOFT TISSUES",
    "MUSCLES": "MUSCLES", "MUSCULATURE": "MUSCLES", "MUSCLE": "MUSCLES",
    "TENDONS": "TENDONS", "TENDON": "TENDONS", "ROTATOR CUFF": "TENDONS",
    "LIGAMENTS": "LIGAMENTS", "LIGAMENT": "LIGAMENTS",
    "MENISCI": "MENISCI", "MENISCUS": "MENISCI",
    "ARTICULAR CARTILAGE": "CARTILAGE", "CARTILAGE": "CARTILAGE",
    "BURSAE": "BURSAE", "BURSA": "BURSAE",
    "NERVES": "NERVES", "NERVE": "NERVES",
    "LUNGS": "LUNGS", "LUNG": "LUNGS", "LUNGS/AIRWAYS": "LUNGS",
    "LUNGS AND AIRWAYS": "LUNGS", "LUNG PARENCHYMA": "LUNGS", "AIRWAYS": "LUNGS",
    "PLEURA": "PLEURA", "PLEURAL SPACES": "PLEURA", "PLEURAL SPACE": "PLEURA",
    "HEART": "HEART", "CARDIAC SILHOUETTE": "HEART", "CARDIOVASCULAR": "HEART",
    "CARDIOMEDIASTINAL SILHOUETTE": "HEART",
    "MEDIASTINUM": "MEDIASTINUM", "MEDIASTINUM/HILA": "MEDIASTINUM",
    "MEDIASTINUM AND HILA": "MEDIASTINUM", "HILA": "MEDIASTINUM",
    "DIAPHRAGM": "DIAPHRAGM", "DIAPHRAGMS": "DIAPHRAGM",
    "SUPPORT DEVICES": "SUPPORT DEVICES", "LINES/TUBES/SUPPORT DEVICES": "SUPPORT DEVICES",
    "LINES AND TUBES": "SUPPORT DEVICES", "DEVICES": "SUPPORT DEVICES",
    "LIVER": "LIVER", "GALLBLADDER": "GALLBLADDER", "GALLBLADDER AND BILIARY": "GALLBLADDER",
    "BILIARY SYSTEM": "GALLBLADDER", "KIDNEYS": "KIDNEYS", "KIDNEY": "KIDNEYS",
    "SPLEEN": "SPLEEN", "PANCREAS": "PANCREAS", "BLADDER": "BLADDER",
    "URINARY BLADDER": "BLADDER", "BOWEL": "BOWEL", "BOWEL GAS PATTERN": "BOWEL",
    "UTERUS": "UTERUS", "OVARIES": "OVARIES", "ADNEXA": "OVARIES", "PROSTATE": "PROSTATE",
    "BRAIN": "BRAIN", "BRAIN PARENCHYMA": "BRAIN", "PARENCHYMA": "BRAIN",
    "SPINAL CORD": "SPINAL CORD", "CORD": "SPINAL CORD",
    "ALIGNMENT": "ALIGNMENT", "SINUSES": "SINUSES", "PARANASAL SINUSES": "SINUSES",
    "ORBITS": "ORBITS", "VESSELS": "VESSELS", "VASCULAR": "VESSELS",
    "BILIARY TREE": "BILIARY", "BILE DUCTS": "BILIARY", "BILIARY": "BILIARY",
    "COMMON BILE DUCT": "BILIARY", "PANCREATIC DUCT": "PANCREATIC DUCT",
    "URETERS": "URETERS", "URETERS AND URINARY BLADDER": "URETERS",
    "SPINAL CANAL": "SPINAL CANAL", "CENTRAL CANAL": "SPINAL CANAL",
    "DISC SPACES": "DISC SPACES", "INTERVERTEBRAL DISCS": "DISC SPACES",
    "DISCS": "DISC SPACES", "NEURAL FORAMINA": "NEURAL FORAMINA",
    "FACET JOINTS": "FACET JOINTS", "SINUSES AND MASTOIDS": "SINUSES",
    "MASTOIDS": "SINUSES", "VERTEBRAE": "BONES", "VERTEBRAL BODIES/ALIGNMENT": "BONES",
}

_STEM_SUFFIXES = ("ies", "ives", "ing", "ous", "als", "ial", "ic", "es", "s", "al", "ar", "y")


def stem(word: str) -> str:
    w = word.lower()
    for suf in _STEM_SUFFIXES:
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def concept_for_label(label: str) -> str | None:
    lab = re.sub(r"\s+", " ", (label or "").upper()).strip()
    if lab in LABEL_ALIASES:
        return LABEL_ALIASES[lab]
    for alias, concept in LABEL_ALIASES.items():
        if alias in lab:
            return concept
    return None


_TERM_INDEX: dict[str, set[str]] = {}
for _concept, _terms in CONCEPT_TERMS.items():
    for _t in _terms:
        _TERM_INDEX.setdefault(_t.lower(), set()).add(_concept)


def concept_hits(text: str) -> dict[str, int]:
    """How many curated terms of each concept occur in `text`."""
    low = " " + re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()) + " "
    hits: dict[str, int] = {}
    for term, concepts in _TERM_INDEX.items():
        if f" {term} " in low or (" " in term and term in low):
            for c in concepts:
                hits[c] = hits.get(c, 0) + 1
    return hits


# ------------------------------------------------------------------ shorthand
# High-precision expansions of dictation shorthand and recurrent misspellings.
# Only unambiguous entries: nothing here changes clinical meaning.
SHORTHAND: dict[str, str] = {
    "degen": "degenerative",
    "degenrative": "degenerative",
    "degerative": "degenerative",
    "chnges": "changes",
    "chages": "changes",
    "norml": "normal",
    "nomal": "normal",
    "effusuon": "effusion",
    "effusiom": "effusion",
    "cacified": "calcified",
    "calcenal": "calcaneal",
    "lymphnodes": "lymph nodes",
    "lymphnode": "lymph node",
    "osteophyes": "osteophytes",
    "oosteophytes": "osteophytes",
    "trignonum": "trigonum",
    "rt": "right",
    "lt": "left",
    "bilat": "bilateral",
    "jt": "joint",
    "jts": "joints",
    "fx": "fracture",
    "wnl": "within normal limits",
    "w/o": "without",
    "w/": "with",
    "c/w": "consistent with",
    "s/p": "status post",
    "b/l": "bilateral",
    "h/o": "history of",
}

_SHORTHAND_RE = re.compile(
    r"(?<![A-Za-z0-9])(" + "|".join(sorted((re.escape(k) for k in SHORTHAND), key=len, reverse=True))
    + r")(?![A-Za-z0-9])",
    re.I,
)


def normalize_shorthand(text: str) -> str:
    """Expand dictation shorthand so the report reads as prose."""
    if not text:
        return text

    def repl(m: re.Match) -> str:
        src = m.group(1)
        out = SHORTHAND[src.lower()]
        return out.capitalize() if src[:1].isupper() else out

    return _SHORTHAND_RE.sub(repl, text)


# ------------------------------------------------------------- spell repair
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]{2,}")
_PROTECT = frozenset(
    """mm cm ml cc iv ap pa lat oblique t1 t2 stir flair dwi adc grade type
    lung rads birads""".split()
)


def build_vocabulary(texts) -> dict[str, int]:
    """Vocabulary of words that actually occur in reports/templates."""
    from collections import Counter

    vocab: Counter = Counter()
    for t in texts:
        for w in _WORD_RE.findall((t or "").lower()):
            vocab[w] += 1
    return dict(vocab)


def correct_spelling(text: str, vocab: dict[str, int], min_count: int = 3) -> str:
    """Repair dictation typos against the corpus vocabulary.

    Conservative by construction: only words absent from the vocabulary are
    touched, the replacement must be a frequent corpus word, and the edit
    distance budget scales with word length.
    """
    if not text or not vocab:
        return text
    from rapidfuzz import process, fuzz

    choices = [w for w, c in vocab.items() if c >= min_count]
    if not choices:
        return text
    cache: dict[str, str] = {}

    def repl(m: re.Match) -> str:
        w = m.group(0)
        low = w.lower()
        if low in vocab or low in _PROTECT or len(low) < 5:
            return w
        if low in cache:
            out = cache[low]
        else:
            budget = 1 if len(low) < 8 else 2
            hit = process.extractOne(
                low, choices, scorer=fuzz.ratio, score_cutoff=100 * (1 - budget / len(low))
            )
            out = low
            if hit:
                cand = hit[0]
                if abs(len(cand) - len(low)) <= budget and cand[0] == low[0]:
                    out = cand
            cache[low] = out
        if out == low:
            return w
        return out.capitalize() if w[:1].isupper() else out

    return _WORD_RE.sub(repl, text)


# ------------------------------------------------------------- body regions
# Coarse regions used to condition the mined routing statistics: the same word
# means different fields in different studies ("effusion" -> PLEURA in a chest
# radiograph, JOINT in a knee MRI).
REGION_GROUPS: dict[str, tuple[str, ...]] = {
    "chest": ("chest", "thorax", "lung", "rib", "ribs", "sternum", "clavicle", "breast",
              "mediastinum"),
    "abdomen": ("abdomen", "pelvis", "liver", "kidney", "bladder", "gallbladder", "spleen",
                "pancreas", "bowel", "uterus", "ovary", "prostate", "scrotum", "renal"),
    "spine": ("spine", "lsspine", "vertebra", "sacrum", "coccyx", "lumbar", "cervical",
              "thoracic", "sacral", "spinal"),
    "upper_limb": ("shoulder", "elbow", "wrist", "hand", "humerus", "forearm", "finger",
                   "thumb", "scapula", "arm", "clavicular"),
    "lower_limb": ("hip", "knee", "ankle", "foot", "femur", "leg", "heel", "toe", "tibia",
                   "fibula", "calcaneous", "calcaneus", "patella"),
    "head_neck": ("head", "brain", "skull", "orbit", "sinus", "neck", "face", "sella",
                  "pituitary", "temporal", "mastoid", "paranasal", "thyroid"),
}

_REGION_INDEX = {w: r for r, words in REGION_GROUPS.items() for w in words}


def body_region(body_part: str, study_description: str = "") -> str:
    """Coarse anatomical region for conditioning the routing statistics."""
    text = re.sub(r"[^a-z ]", " ", f"{body_part} {study_description}".lower())
    for w in text.split():
        r = _REGION_INDEX.get(w)
        if r:
            return r
        r = _REGION_INDEX.get(w.rstrip("s"))
        if r:
            return r
    return "other"
