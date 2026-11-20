"""Bodhan Humanizer Pipeline — transforms AI-generated text into human-like text.

Adheres to AGENTS.md §1 & PLAN.md §7:
1. Translates English text to Indic language(s) using Bodhan indic-translate.
2. Back-translates to English to disrupt AI statistical/linguistic signatures.
3. Evaluates semantic fidelity (cosine similarity >= 0.80).
4. Optionally verifies against Sloptotal detectors to measure human detection.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as cfg

# Cliché phrase normalizations for hybrid strategy
HYBRID_REPLACEMENTS = [
    (r"\bIn conclusion,\s*", "Overall, "),
    (r"\bFurthermore,\s*", "Also, "),
    (r"\bMoreover,\s*", "In addition, "),
    (r"\bIt is important to note that\s*", "Note that "),
    (r"\bIt is worth noting that\s*", "Noticeably, "),
    (r"\bdelve into\b", "explore"),
    (r"\ba testament to\b", "proof of"),
]


def resolve_api_key(config):
    env_var = config.get("bodhan_key_env_var", "INDIC_TRANSLATE_API_KEY")
    key = os.environ.get(env_var) or os.environ.get("BODHAN_API_KEY")
    if key:
        return key.strip()

    key_file = os.path.join(cfg.PROJECT_ROOT, config.get("bodhan_key_file_local", ".dev.vars"))
    if os.path.exists(key_file):
        with open(key_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(env_var + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
                if line.startswith("BODHAN_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")

    raise RuntimeError("Missing Bodhan API key. Set %s in environment or %s." % (env_var, key_file))


def translate_leg(text, target_lang, script="native", config=None, api_key=None):
    if not config:
        config = cfg.load("humanizer.yaml")
    if not api_key:
        api_key = resolve_api_key(config)

    base_url = cfg.require_resolved(config, "bodhan_base_url", "config/humanizer.yaml")
    chat_path = cfg.require_resolved(config, "bodhan_chat_path", "config/humanizer.yaml")
    model = cfg.require_resolved(config, "bodhan_model", "config/humanizer.yaml")
    timeout = int(config.get("timeout_s", 45))
    max_retries = int(config.get("max_retries", 3))
    backoff_429 = int(config.get("backoff_429_s", 60))

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": text}],
        "target_language_code": target_lang,
        "target_script": script
    }
    body = json.dumps(payload).encode("utf-8")
    url = base_url + chat_path

    last_error = None
    for attempt in range(1, max_retries + 1):
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json"
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                return content
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            last_error = "HTTP %s: %s" % (exc.code, err_body)
            if exc.code == 429:
                wait = backoff_429
                try:
                    retry_header = exc.headers.get("Retry-After")
                    if retry_header:
                        wait = max(wait, float(retry_header))
                except (TypeError, ValueError):
                    pass
                if attempt < max_retries:
                    time.sleep(wait)
                    continue
            elif exc.code in (500, 502, 503, 504):
                if attempt < max_retries:
                    time.sleep(2 * attempt)
                    continue
            raise RuntimeError("Bodhan API error: %s" % last_error) from exc
        except Exception as exc:
            last_error = "%s: %s" % (type(exc).__name__, exc)
            if attempt < max_retries:
                time.sleep(2 * attempt)
                continue
            raise RuntimeError("Bodhan transport error: %s" % last_error) from exc

    raise RuntimeError("Bodhan retries exhausted: %s" % last_error)


def apply_hybrid_adjustments(text):
    result = text
    for pattern, replacement in HYBRID_REPLACEMENTS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def humanize(text, strategy="round-trip", language="kn", chain=None, config=None, api_key=None):
    if not config:
        config = cfg.load("humanizer.yaml")
    if not api_key:
        api_key = resolve_api_key(config)

    inter_delay = float(config.get("inter_call_delay_s", 2))
    stages = []

    if strategy == "round-trip":
        target = language or config.get("default_language", "kn")
        # Step 1: en -> target
        intermediate = translate_leg(text, target, script="native", config=config, api_key=api_key)
        stages.append({"from": "en", "to": target, "text": intermediate})
        if inter_delay > 0:
            time.sleep(inter_delay)
        # Step 2: target -> en
        humanized = translate_leg(intermediate, "en", script="native", config=config, api_key=api_key)
        stages.append({"from": target, "to": "en", "text": humanized})

    elif strategy == "multi-hop":
        hop_languages = chain or config.get("multihop_chain", ["hi", "kn"])
        curr_text = text
        prev_lang = "en"
        for hop in hop_languages:
            curr_text = translate_leg(curr_text, hop, script="native", config=config, api_key=api_key)
            stages.append({"from": prev_lang, "to": hop, "text": curr_text})
            prev_lang = hop
            if inter_delay > 0:
                time.sleep(inter_delay)
        # Final leg back to English
        humanized = translate_leg(curr_text, "en", script="native", config=config, api_key=api_key)
        stages.append({"from": prev_lang, "to": "en", "text": humanized})

    elif strategy == "hybrid":
        # Multi-hop followed by stylistic de-clichéing
        hop_languages = chain or config.get("multihop_chain", ["hi", "kn"])
        curr_text = text
        prev_lang = "en"
        for hop in hop_languages:
            curr_text = translate_leg(curr_text, hop, script="native", config=config, api_key=api_key)
            stages.append({"from": prev_lang, "to": hop, "text": curr_text})
            prev_lang = hop
            if inter_delay > 0:
                time.sleep(inter_delay)
        translated_en = translate_leg(curr_text, "en", script="native", config=config, api_key=api_key)
        stages.append({"from": prev_lang, "to": "en", "text": translated_en})
        humanized = apply_hybrid_adjustments(translated_en)
        stages.append({"from": "en", "to": "en_hybrid", "text": humanized})

    else:
        raise ValueError("Unknown strategy: %s (supported: round-trip, multi-hop, hybrid)" % strategy)

    return {
        "original_text": text,
        "humanized_text": humanized,
        "strategy": strategy,
        "stages": stages
    }


def compute_fidelity(original, variant):
    try:
        import fidelity
        model = fidelity.load_model()
        return round(float(fidelity.cosine(model, original, variant)), 4)
    except Exception as exc:
        print("[WARN] Could not calculate embedding fidelity: %s" % exc, file=sys.stderr)
        return None


def score_detectors(text, sloptotal_url="http://localhost:8765/api/analyze"):
    req = urllib.request.Request(
        sloptotal_url,
        data=json.dumps({"text": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("engine_results", [])
            clean_count = sum(1 for e in results if e.get("verdict") == "clean")
            slop_count = sum(1 for e in results if e.get("verdict") == "slop")
            total = len(results)
            engines = {
                e.get("engine_name"): {
                    "verdict": e.get("verdict"),
                    "score": e.get("score")
                }
                for e in results
            }
            return {
                "overall_verdict": data.get("overall_verdict"),
                "clean_count": clean_count,
                "slop_count": slop_count,
                "total_detectors": total,
                "engines": engines
            }
    except Exception as exc:
        return {"error": str(exc)}


def main():
    parser = argparse.ArgumentParser(description="Bodhan Humanizer CLI Pipeline")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--text", type=str, help="Raw AI text to humanize")
    group.add_argument("--file", type=str, help="Path to text file to humanize")

    parser.add_argument("--strategy", type=str, default="round-trip",
                        choices=["round-trip", "multi-hop", "hybrid"],
                        help="Transformation strategy (default: round-trip)")
    parser.add_argument("--lang", type=str, default="kn",
                        help="Indic language code for round-trip (default: kn)")
    parser.add_argument("--chain", type=str, nargs="+", default=None,
                        help="Custom language chain for multi-hop (e.g. hi kn)")
    parser.add_argument("--evaluate", action="store_true",
                        help="Evaluate detector scores before and after on Sloptotal")
    parser.add_argument("--out", type=str, help="Path to save humanized text")
    parser.add_argument("--json", action="store_true", help="Output result as JSON")

    args = parser.parse_args()

    input_text = args.text
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            input_text = f.read().strip()

    if not input_text:
        print("Error: Input text is empty.", file=sys.stderr)
        return 1

    config = cfg.load("humanizer.yaml")
    api_key = resolve_api_key(config)

    print("=" * 60)
    print("BODHAN HUMANIZER PIPELINE")
    print("Strategy: %s | Primary Lang: %s" % (args.strategy, args.lang))
    print("=" * 60)

    # 1. Humanize
    t0 = time.time()
    result = humanize(
        input_text,
        strategy=args.strategy,
        language=args.lang,
        chain=args.chain,
        config=config,
        api_key=api_key
    )
    duration = round(time.time() - t0, 2)
    humanized_text = result["humanized_text"]

    # 2. Fidelity Gate
    fidelity_score = compute_fidelity(input_text, humanized_text)
    min_thresh = float(config.get("fidelity_min_threshold", 0.80))
    fidelity_passed = (fidelity_score is not None and fidelity_score >= min_thresh)

    output_payload = {
        "status": "success",
        "strategy": args.strategy,
        "duration_seconds": duration,
        "fidelity_score": fidelity_score,
        "fidelity_passed": fidelity_passed,
        "original_text": input_text,
        "humanized_text": humanized_text,
        "stages": result["stages"]
    }

    # 3. Optional Detector Evaluation
    if args.evaluate:
        slop_url = config.get("sloptotal_base_url", "http://localhost:8765") + config.get("sloptotal_analyze_path", "/api/analyze")
        print("\nEvaluating against detectors at %s..." % slop_url)
        scores_orig = score_detectors(input_text, slop_url)
        scores_humanized = score_detectors(humanized_text, slop_url)
        output_payload["evaluation"] = {
            "original": scores_orig,
            "humanized": scores_humanized
        }

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(humanized_text)
        print("Humanized text written to: %s" % args.out)

    if args.json:
        print(json.dumps(output_payload, indent=2))
        return 0

    print("\n--- ORIGINAL TEXT (%d words) ---" % len(input_text.split()))
    print(input_text)
    print("\n--- HUMANIZED TEXT (%d words) ---" % len(humanized_text.split()))
    print(humanized_text)
    print("\n--- METRICS ---")
    print("Fidelity Score: %s (Threshold: >= %s -> %s)" % (
        fidelity_score, min_thresh, "PASS" if fidelity_passed else "FAIL"))
    print("Transformation Time: %ss" % duration)

    if args.evaluate and "evaluation" in output_payload:
        ev = output_payload["evaluation"]
        orig_ev = ev.get("original", {})
        hum_ev = ev.get("humanized", {})
        if "error" in orig_ev or "error" in hum_ev:
            print("[WARN] Detector evaluation error: %s" % (orig_ev.get("error") or hum_ev.get("error")))
        else:
            print("\n--- DETECTOR CLASSIFICATION COMPARISON ---")
            print("Detectors classifying as HUMAN (Clean):")
            print("  Before: %s / %s" % (orig_ev.get("clean_count"), orig_ev.get("total_detectors")))
            print("  After:  %s / %s" % (hum_ev.get("clean_count"), hum_ev.get("total_detectors")))
            print("Overall Verdict:")
            print("  Before: %s" % orig_ev.get("overall_verdict"))
            print("  After:  %s" % hum_ev.get("overall_verdict"))

            print("\nKey Detector Scores (0.0 = Human / Clean, 1.0 = AI / Slop):")
            for det_name in [
                "Binoculars", "Fast-DetectGPT", "OpenAI Detector", "GLTR",
                "Log-Rank", "Burstiness", "Readability Uniformity", "Perplexity"
            ]:
                s1 = orig_ev.get("engines", {}).get(det_name, {}).get("score", "N/A")
                s2 = hum_ev.get("engines", {}).get(det_name, {}).get("score", "N/A")
                v1 = orig_ev.get("engines", {}).get(det_name, {}).get("verdict", "N/A")
                v2 = hum_ev.get("engines", {}).get(det_name, {}).get("verdict", "N/A")
                print("  %-25s Before: %s (%s)  -->  After: %s (%s)" % (det_name, s1, v1, s2, v2))

    return 0 if (fidelity_passed or fidelity_score is None) else 2


if __name__ == "__main__":
    sys.exit(main())
