"""Fidelity scorer — three-layer gate per PLAN §2.3 (D2 build).

Layer 1 (required): document-embedding cosine, variant-vs-original, from the
  model named in config/fidelity.yaml. Pass iff cosine >= threshold.
Layer 2 (supporting, never sole gate): number + capitalized-span overlap,
  reported with a review flag. Entity extraction is deliberately crude stdlib
  regex (proper NER is future work); noise here only flags, never fails.
Layer 3 (human): protocol frozen in build/evidence/D2/spotcheck-protocol.md;
  execution EXTERNAL-BLOCKED (no external raters in-session), so every variant
  is marked `spotcheck: unsampled` and passes on Layer 1 alone per §2.3.

Model loading honors fidelity_model_cache_dir (set as HF_HOME before importing
sentence_transformers). Import is lazy so this module imports under any
interpreter; gate() requires the D2 venv.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as cfg

# origin: D2 decision — crude stdlib entity/number signals; Layer 2 never gates
# alone, so recall noise is tolerable (reported + flagged, never failed).
RE_NUMBER = re.compile(r"\d[\d,./:-]*")
RE_ENTITY = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*")
# origin: D2 decision — flag threshold for entity-span recall.
ENTITY_FLAG_RECALL = 0.5

_MODEL = None


def load_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    fid = cfg.load("fidelity.yaml")
    cache = cfg.require_resolved(fid, "fidelity_model_cache_dir", "config/fidelity.yaml")
    os.environ.setdefault("HF_HOME", os.path.join(cfg.PROJECT_ROOT, cache))
    name = cfg.require_resolved(fid, "fidelity_scorer_model", "config/fidelity.yaml")
    short = name.split("/")[-1]
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError("fidelity scorer needs the D2 venv (sentence-transformers)") from exc
    _MODEL = SentenceTransformer(short)
    return _MODEL


def cosine(model, original, variant):
    import numpy as np
    emb = model.encode([original, variant], normalize_embeddings=True)
    return float(np.dot(emb[0], emb[1]))


def _syllables(word):
    # origin: D3A decision — standard vowel-group heuristic for Flesch; crude
    # but deterministic and dependency-free (Layer 2 never gates alone).
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return 0
    groups = re.findall(r"[aeiouy]+", word)
    count = len(groups)
    if word.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


def flesch_reading_ease(text):
    words = re.findall(r"[A-Za-z']+", text)
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    if not words or not sentences:
        return 0.0
    syllables = sum(_syllables(w) for w in words)
    score = 206.835 - 1.015 * (len(words) / len(sentences)) - 84.6 * (syllables / len(words))
    return round(score, 2)


def layer2(original, variant):
    nums_o = set(RE_NUMBER.findall(original))
    nums_v = set(RE_NUMBER.findall(variant))
    ent_o = set(RE_ENTITY.findall(original))
    ent_v = set(RE_ENTITY.findall(variant))
    num_recall = len(nums_o & nums_v) / len(nums_o) if nums_o else 1.0
    ent_recall = len(ent_o & ent_v) / len(ent_o) if ent_o else 1.0
    dropped_numbers = sorted(nums_o - nums_v)
    return {
        "numbers_original": len(nums_o),
        "numbers_recall": round(num_recall, 4),
        "dropped_numbers": dropped_numbers,
        "entities_original": len(ent_o),
        "entities_recall": round(ent_recall, 4),
        "readability": {"method": "flesch-reading-ease-stdlib",
                        "original": flesch_reading_ease(original),
                        "variant": flesch_reading_ease(variant)},
        "review_flag": bool(dropped_numbers) or ent_recall < ENTITY_FLAG_RECALL,
    }


def gate(original, variant, model=None):
    fid = cfg.load("fidelity.yaml")
    threshold = cfg.require_resolved(fid, "fidelity_threshold", "config/fidelity.yaml")
    model = model or load_model()
    score = cosine(model, original, variant)
    automated = score >= threshold
    return {
        "cosine": round(score, 4),
        "threshold": threshold,
        "metric": cfg.require_resolved(fid, "fidelity_threshold_metric", "config/fidelity.yaml"),
        "model": cfg.require_resolved(fid, "fidelity_scorer_model", "config/fidelity.yaml"),
        "automated_pass": automated,
        "layer2": layer2(original, variant),
        "spotcheck": "unsampled",
        "fidelity_passing": automated,  # §2.3 unsampled rule
    }
