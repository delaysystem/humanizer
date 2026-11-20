"""D5 E2E-3: rescore every frozen D3/D3A variant text through the configured
endpoint and store raw reports run-scoped. Asserts the configured container
exists, is healthy, and runs the D0-pinned image digest (mechanical proof
the rescoring endpoint is what the config claims); records both container
IDs so fresh-vs-reuse is factual, never assumed.

Usage: d5_rescore.py --run-dir <dir> --d3-store results/d3 --d3a-store results/d3a
"""
import glob
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "harness"))
import config as cfg
import run as runner
import store


def main(args):
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    d5 = cfg.load("d5.yaml")
    base = cfg.require_resolved(d5, "d5_rescoring_base_url", "config/d5.yaml")
    container = cfg.require_resolved(d5, "d5_rescoring_container", "config/d5.yaml")
    live = json.loads(subprocess.run(["docker", "inspect", container], capture_output=True,
                                     text=True, check=True).stdout)[0]
    if live["State"].get("Health", {}).get("Status") != "healthy":
        raise ValueError("rescoring container not healthy: " + container)
    frozen = json.load(open(os.path.join(
        root, "build/evidence/D0/frozen/docker-baseline.json")))["payload"]
    if live["Image"] != frozen["image_digest"]:
        raise ValueError("rescoring image is not the D0 pin: " + live["Image"])
    fresh = live["Id"] != frozen["container_id"]
    print("rescoring endpoint: %s (%s, image==D0 pin, fresh=%s)"
          % (base, live["Id"][:12], fresh))
    api = cfg.load("api.yaml")
    analyze = cfg.require_resolved(api, "sloptotal_analyze_path", "config/api.yaml")
    ticket = cfg.require_resolved(api, "sloptotal_ticket_path_prefix", "config/api.yaml")
    attempts = cfg.require_resolved(api, "runner_retry_max_attempts", "config/api.yaml")
    backoff = cfg.require_resolved(api, "runner_retry_backoff_s", "config/api.yaml")
    out = os.path.join(args.run_dir, "rescores")
    os.makedirs(out, exist_ok=True)
    log = store.AttemptLog(args.run_dir, "rescore")
    texts = []
    for store_dir in (args.d3_store, args.d3a_store):
        for path in sorted(glob.glob(os.path.join(store_dir, "variants", "V-*.txt"))):
            texts.append((os.path.basename(path)[:-4], open(path).read()))
    if len(texts) != 207:
        raise ValueError("expected 207 frozen variants, found %d" % len(texts))
    blocked, scored = [], 0
    for vid, text in texts:
        report, fatal = runner.score_with_retry(
            base, analyze, ticket, text, attempts, backoff, runner.SCORE_TIMEOUT_S,
            lambda e: log.event(dict(e, sample_id=vid)))
        if report is None:
            blocked.append({"variant_id": vid, "status": "EXTERNAL-BLOCKED",
                            "reason": str(fatal)[:300]})
            continue
        with open(os.path.join(out, vid + ".json"), "w") as fh:
            json.dump(report, fh, indent=2)
        scored += 1
    with open(os.path.join(args.run_dir, "rescore-blocked.json"), "w") as fh:
        json.dump(blocked, fh, indent=2)
    print("rescoring done: scored=%d blocked=%d endpoint_fresh=%s" % (scored, len(blocked), fresh))
    return 0 if not blocked else 3


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(prog="d5_rescore")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--d3-store", required=True)
    parser.add_argument("--d3a-store", required=True)
    sys.exit(main(parser.parse_args()))
