"""Fold-model cache keyed by a fingerprint of the pipeline source.

Tuning scripts refit the routing model for every fold, which dominates their
runtime.  Caching is safe only while the code that produced the model is
unchanged, so the cache file is named after a hash of the package source.
"""
from __future__ import annotations

import hashlib
import os
import pickle

PKG = os.path.dirname(os.path.abspath(__file__))


def source_fingerprint() -> str:
    h = hashlib.sha256()
    for name in sorted(os.listdir(PKG)):
        if name.endswith(".py"):
            with open(os.path.join(PKG, name), "rb") as fh:
                h.update(name.encode())
                h.update(fh.read())
    return h.hexdigest()[:12]


def cache_path(artifacts_dir: str, key: str = "") -> str:
    os.makedirs(artifacts_dir, exist_ok=True)
    suffix = "" if not key else "." + hashlib.sha256(key.encode()).hexdigest()[:8]
    return os.path.join(artifacts_dir, f"fold_models.{source_fingerprint()}{suffix}.pkl")


def load_or_build(artifacts_dir: str, build, key: str = ""):
    path = cache_path(artifacts_dir, key)
    if os.path.exists(path):
        with open(path, "rb") as fh:
            return pickle.load(fh)
    models = build()
    with open(path, "wb") as fh:
        pickle.dump(models, fh)
    return models
