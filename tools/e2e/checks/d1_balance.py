"""D1 E2E-2 (independent path): balance check — counts per label/topic/band/cell
match config/datasets.yaml targets within dataset_count_tolerance."""
import json
import os
import sys
from collections import Counter

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
import config as cfg


def main(run_dir):
    report = {"check": "d1-balance", "pass": False, "details": []}
    manifest = json.load(open(os.path.join(ROOT, "datasets", "v1", "manifest.json")))
    ds = cfg.load("datasets.yaml")
    tol = cfg.require_resolved(ds, "dataset_count_tolerance", "config/datasets.yaml")
    cell = cfg.require_resolved(ds, "dataset_cell_count", "config/datasets.yaml")
    samples = manifest["samples"]
    labels = Counter(s["ground_truth_label"] for s in samples)
    topics = Counter(s["topic"] for s in samples)
    bands = Counter(s["length_band"] for s in samples)
    cells = Counter((s["ground_truth_label"], s["topic"], s["length_band"]) for s in samples)
    n_labels = len(ds["dataset_labels"])
    n_topics = len(ds["dataset_topics"])
    n_bands = len(ds["dataset_bands"])
    exp_label = n_topics * n_bands * cell
    exp_topic = n_labels * n_bands * cell
    exp_band = n_labels * n_topics * cell
    for name, counter, expected in (("label", labels, exp_label),
                                    ("topic", topics, exp_topic),
                                    ("band", bands, exp_band)):
        for key, count in sorted(counter.items()):
            if abs(count - expected) > tol:
                report["details"].append("%s %s: %d != %d" % (name, key, count, expected))
    for key, count in sorted(cells.items()):
        if abs(count - cell) > tol:
            report["details"].append("cell %s: %d != %d" % (key, count, cell))
    if len(samples) != cfg.require_resolved(ds, "dataset_total_samples", "config/datasets.yaml"):
        report["details"].append("total %d != target" % len(samples))
    if not report["details"]:
        report["details"].append("%d samples balanced: labels %s topics %s bands %s cells=%d"
                                 % (len(samples), dict(labels), dict(topics),
                                    dict(bands), cell))
    report["pass"] = not [d for d in report["details"] if "balanced" not in d]
    json.dump(report, open(os.path.join(run_dir, "check-d1-balance.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d1-balance: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
