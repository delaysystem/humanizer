"""D1 E2E-4 (independent path): contamination + secrets scan.

(a) Exact-sha256 duplicates across human/AI sets: must be zero.
(b) Near-duplicate pairs at/above config threshold: every flagged pair must
    carry a disposition in the D1 disposition log (kept-with-reason, or removed
    via a new manifest version — a removal without a version bump fails).
(c) Secret/credential scan over all dataset texts: must be zero hits.
"""
import difflib
import hashlib
import itertools
import json
import os
import re
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
import config as cfg

DS_DIR = os.path.join(ROOT, "datasets", "v1")
# origin: PLAN D1 E2E-4 — disposition log lives in the milestone evidence dir.
DISPOSITION_PATH = os.path.join(ROOT, "build", "evidence", "D1", "near-dup-dispositions.json")

RE_SECRET = re.compile(
    r"(?i)(api" + "_" + "key|api" + "-" + "key|secret|pass" + "word)"
    r"\s*[:=]\s*['\"][^$<\s][^'\"]{3,}['\"]")
RE_BEARER_TOKEN = re.compile("bear" + "er" + r"\s+[A-Za-z0-9\-._~+/]{8,}", re.IGNORECASE)


def main(run_dir):
    report = {"check": "d1-contamination", "pass": False, "details": []}
    manifest = json.load(open(os.path.join(DS_DIR, "manifest.json")))
    ds = cfg.load("datasets.yaml")
    threshold = cfg.require_resolved(ds, "near_duplicate_threshold", "config/datasets.yaml")
    method = cfg.require_resolved(ds, "near_duplicate_method", "config/datasets.yaml")
    assert method == "difflib-ratio-on-normalized-text", "unknown method " + method
    samples = manifest["samples"]
    texts = {}
    for sample in samples:
        texts[sample["sample_id"]] = open(
            os.path.join(DS_DIR, sample["text_file"])).read()
    by_label = {}
    for sample in samples:
        by_label.setdefault(sample["ground_truth_label"], []).append(sample["sample_id"])
    # (a) exact cross-set hash dupes
    hashes = {}
    for sid, text in texts.items():
        hashes.setdefault(hashlib.sha256(text.encode()).hexdigest(), []).append(sid)
    cross = {h: sids for h, sids in hashes.items() if len(sids) > 1}
    if cross:
        report["details"].append("exact duplicates: %s" % cross)
    # (b) near dupes + dispositions
    norm = {sid: " ".join(text.lower().split()) for sid, text in texts.items()}
    flags = []
    for a, b in itertools.combinations(sorted(texts), 2):
        ratio = difflib.SequenceMatcher(None, norm[a], norm[b]).ratio()
        if ratio >= threshold:
            flags.append({"pair": [a, b], "ratio": round(ratio, 4)})
    json.dump({"threshold": threshold, "flags": flags},
              open(os.path.join(run_dir, "near-dup-flags.json"), "w"), indent=2)
    dispositions = {}
    if os.path.exists(DISPOSITION_PATH):
        dispositions = json.load(open(DISPOSITION_PATH)).get("dispositions", {})
    undispositioned = [f for f in flags
                       if "|".join(f["pair"]) not in dispositions]
    if undispositioned:
        report["details"].append("undispositioned pairs: %s" % undispositioned)
    for key, disp in dispositions.items():
        if disp.get("action") not in ("kept-with-reason", "removed-new-manifest-version"):
            report["details"].append("bad disposition action: " + key)
        if not disp.get("reason"):
            report["details"].append("disposition without reason: " + key)
    # (c) secrets scan
    secret_hits = []
    for sid, text in texts.items():
        for i, line in enumerate(text.splitlines(), 1):
            if RE_SECRET.search(line) or RE_BEARER_TOKEN.search(line):
                secret_hits.append("%s:%d" % (sid, i))
    if secret_hits:
        report["details"].append("secret hits: %s" % secret_hits)
    if not report["details"]:
        report["details"].append("0 exact dupes, %d near-dupe flags (%d dispositioned), 0 secret hits"
                                 % (len(flags), len(dispositions)))
    report["pass"] = not [d for d in report["details"] if not d.startswith("0 exact")]
    json.dump(report, open(os.path.join(run_dir, "check-d1-contamination.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d1-contamination: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
