"""D1 E2E-1 (independent path): manifest integrity.

Asserts: top/sample fields match config/dataset-manifest-schema.json; sample
IDs unique; every ID resolves to exactly one text file whose sha256 and word
count match the manifest; labels/provenance in the allowed sets; each text's
word count falls inside its declared band range from config/datasets.yaml
(band truth is part of integrity: a mis-banded sample is a corrupt manifest).
"""
import hashlib
import json
import os
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
import config as cfg

DS_DIR = os.path.join(ROOT, "datasets", "v1")


def main(run_dir):
    report = {"check": "d1-manifest", "pass": False, "details": []}
    schema = json.load(open(os.path.join(ROOT, "config", "dataset-manifest-schema.json")))
    manifest = json.load(open(os.path.join(DS_DIR, "manifest.json")))
    ds = cfg.load("datasets.yaml")
    for field in schema["required_top_fields"]:
        if field not in manifest:
            report["details"].append("missing top field: " + field)
    seen, files = set(), set()
    for sample in manifest.get("samples", []):
        for field in schema["required_sample_fields"]:
            if field not in sample:
                report["details"].append("sample missing %s: %s"
                                         % (field, sample.get("sample_id")))
        sid = sample.get("sample_id")
        if sid in seen:
            report["details"].append("duplicate ID: " + str(sid))
        seen.add(sid)
        rel = sample.get("text_file", "")
        if rel in files:
            report["details"].append("file claimed twice: " + rel)
        files.add(rel)
        path = os.path.join(DS_DIR, rel)
        if not os.path.isfile(path):
            report["details"].append("unresolved file: " + rel)
            continue
        raw = open(path, "rb").read()
        if hashlib.sha256(raw).hexdigest() != sample.get("text_sha256"):
            report["details"].append("sha mismatch: " + str(sid))
        words = len(raw.decode("utf-8").split())
        if words != sample.get("word_count"):
            report["details"].append("word_count mismatch: %s" % sid)
        band = sample.get("length_band")
        lo = ds.get("band_%s_min_words" % band)
        hi = ds.get("band_%s_max_words" % band)
        if lo is None or not (lo <= words <= hi):
            report["details"].append("out of band %s: %s has %s words"
                                     % (band, sid, words))
        if sample.get("ground_truth_label") not in schema["label_values"]:
            report["details"].append("bad label: " + str(sid))
        if sample.get("provenance") not in schema["provenance_values"]:
            report["details"].append("bad provenance: " + str(sid))
    orphans = set("texts/" + f for f in os.listdir(os.path.join(DS_DIR, "texts"))
                  if f.endswith(".txt")) - files
    if orphans:
        report["details"].append("orphan text files: %s" % sorted(orphans))
    if not report["details"]:
        report["details"].append("%d samples resolve 1:1, all in-band, labeled, unique"
                                 % len(seen))
    report["pass"] = not report["details"] or report["details"][0].endswith("unique")
    report["pass"] = len([d for d in report["details"]
                          if not d.endswith("unique")]) == 0
    json.dump(report, open(os.path.join(run_dir, "check-d1-manifest.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d1-manifest: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
