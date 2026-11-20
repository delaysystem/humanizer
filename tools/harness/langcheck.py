"""Final-language rule, §2.3 (D3A build) — script-fraction proxy for language ID.

A variant whose Kannada-script character fraction exceeds the config limit is
not in the intended final language (English) and must be marked degraded
regardless of Layer 1. Used by the D3A pipeline at generation time; D4 applies
the same function at analysis time for D3 variants (no D3 evidence rewritten).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as cfg

# origin: D3A decision — Unicode Kannada block; script fraction is a crude but
# deterministic language-leak signal (a correct en output has ~zero Kannada).
KANNADA_START, KANNADA_END = 0x0C80, 0x0CFF


def kannada_fraction(text):
    if not text:
        return 0.0
    hits = sum(1 for ch in text if KANNADA_START <= ord(ch) <= KANNADA_END)
    return round(hits / len(text), 4)


def check(text):
    fid = cfg.load("fidelity.yaml")
    intended = cfg.require_resolved(fid, "lang_intended_final", "config/fidelity.yaml")
    limit = cfg.require_resolved(fid, "lang_kannada_fraction_limit", "config/fidelity.yaml")
    frac = kannada_fraction(text)
    return {"intended_final": intended, "kannada_fraction": frac,
            "limit": limit, "mismatch": frac > limit}
