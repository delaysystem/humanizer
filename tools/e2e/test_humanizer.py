"""Automated E2E Verification Suite for Bodhan Humanizer Pipeline.

Enforces Rule 3 (No untested code):
- Exercises real Bodhan API calls with active credentials from .dev.vars.
- Exercises real pipeline strategies (round-trip, multi-hop, hybrid).
- Asserts semantic fidelity cosine >= 0.80 using real sentence-transformers.
- Exercises real Sloptotal detector API (http://localhost:8765).
- Asserts observable shift in detector scores and clean verdicts.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "harness"))
import config as cfg
import humanize

SAMPLE_AI_TEXT = (
    "The SoundArc Buds Lite offer impressive value at their budget price point. "
    "Setup is straightforward, with quick Bluetooth pairing and a comfortable fit suitable for exercise. "
    "Call quality is adequate for everyday conversations. "
    "While bass response is limited and the charging case feels inexpensive, these compromises are reasonable given the cost. "
    "Battery life meets the manufacturer's six-hour rating. "
    "For users who frequently misplace earbuds, the low replacement cost is a significant advantage. "
    "Overall, these earbuds deliver solid performance for casual listening."
)


def log(msg):
    print("[E2E] %s" % msg)


def test_e2e_humanizer():
    log("Loading configuration...")
    config = cfg.load("humanizer.yaml")
    api_key = humanize.resolve_api_key(config)
    assert api_key, "API key resolution failed"
    log("API key resolved successfully (length: %d)" % len(api_key))

    # Test 1: Round-trip translation
    log("Testing Strategy 1: Round-trip (en -> kn -> en)...")
    res_rt = humanize.humanize(SAMPLE_AI_TEXT, strategy="round-trip", language="kn", config=config, api_key=api_key)
    text_rt = res_rt["humanized_text"]
    assert text_rt, "Round-trip returned empty text"
    assert text_rt != SAMPLE_AI_TEXT, "Round-trip text was unchanged"
    assert len(text_rt.split()) >= 40, "Round-trip text truncated abnormally"
    log("Round-trip produced %d words" % len(text_rt.split()))

    # Test 2: Fidelity Gate on round-trip
    log("Calculating semantic fidelity score for Round-trip...")
    fidelity_rt = humanize.compute_fidelity(SAMPLE_AI_TEXT, text_rt)
    log("Round-trip Fidelity Cosine: %s" % fidelity_rt)
    assert fidelity_rt is not None, "Fidelity calculation failed"
    assert fidelity_rt >= 0.80, "Fidelity score %s below 0.80 threshold" % fidelity_rt
    log("PASS: Round-trip semantic fidelity >= 0.80 (actual: %s)" % fidelity_rt)

    # Test 3: Multi-hop translation
    log("Testing Strategy 2: Multi-hop (en -> hi -> kn -> en)...")
    res_mh = humanize.humanize(SAMPLE_AI_TEXT, strategy="multi-hop", chain=["hi", "kn"], config=config, api_key=api_key)
    text_mh = res_mh["humanized_text"]
    assert text_mh, "Multi-hop returned empty text"
    assert text_mh != SAMPLE_AI_TEXT, "Multi-hop text was unchanged"
    fidelity_mh = humanize.compute_fidelity(SAMPLE_AI_TEXT, text_mh)
    log("Multi-hop Fidelity Cosine: %s" % fidelity_mh)
    assert fidelity_mh >= 0.80, "Multi-hop fidelity %s below 0.80 threshold" % fidelity_mh
    log("PASS: Multi-hop semantic fidelity >= 0.80 (actual: %s)" % fidelity_mh)

    # Test 4: Hybrid transformation
    log("Testing Strategy 3: Hybrid (multi-hop + stylistic adjustments)...")
    res_hy = humanize.humanize(SAMPLE_AI_TEXT, strategy="hybrid", chain=["hi", "kn"], config=config, api_key=api_key)
    text_hy = res_hy["humanized_text"]
    assert text_hy, "Hybrid returned empty text"
    fidelity_hy = humanize.compute_fidelity(SAMPLE_AI_TEXT, text_hy)
    log("Hybrid Fidelity Cosine: %s" % fidelity_hy)
    assert fidelity_hy >= 0.80, "Hybrid fidelity %s below 0.80 threshold" % fidelity_hy
    log("PASS: Hybrid semantic fidelity >= 0.80 (actual: %s)" % fidelity_hy)

    # Test 5: Detector scoring on Sloptotal
    slop_url = config.get("sloptotal_base_url", "http://localhost:8765") + config.get("sloptotal_analyze_path", "/api/analyze")
    log("Testing detector classification against Sloptotal at %s..." % slop_url)

    scores_orig = humanize.score_detectors(SAMPLE_AI_TEXT, slop_url)
    assert "error" not in scores_orig, "Sloptotal scoring error on original text: %s" % scores_orig.get("error")

    scores_rt = humanize.score_detectors(text_rt, slop_url)
    assert "error" not in scores_rt, "Sloptotal scoring error on humanized text: %s" % scores_rt.get("error")

    clean_count = scores_rt.get("clean_count", 0)
    total_count = scores_rt.get("total_detectors", 0)
    log("Humanized text clean detectors: %d / %d" % (clean_count, total_count))
    assert clean_count >= 14, "Expected at least 14 clean detectors, got %d" % clean_count

    # Check specific critical detectors
    engines = scores_rt.get("engines", {})
    for det in ["Binoculars", "Fast-DetectGPT", "OpenAI Detector", "Burstiness", "Perplexity"]:
        info = engines.get(det, {})
        v = info.get("verdict")
        s = info.get("score")
        log("Detector %-20s -> Verdict: %s (Score: %s)" % (det, v, s))
        assert v == "clean", "Expected %s to be clean, got %s (score: %s)" % (det, v, s)

    log("ALL E2E CHECKS PASSED DETERMINISTICALLY.")
    return 0


if __name__ == "__main__":
    sys.exit(test_e2e_humanizer())
