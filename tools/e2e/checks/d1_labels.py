"""D1 E2E-5 (independent path): label preservation — copy the dataset to a clean
dir inside the run dir, re-read the copied manifest, and assert per-label
counts plus the full (file, label) pairing set equal the original's."""
import json
import os
import shutil
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)

DS_DIR = os.path.join(ROOT, "datasets", "v1")


def pairing(manifest):
    return sorted((s["text_file"], s["ground_truth_label"]) for s in manifest["samples"])


def label_counts(manifest):
    counts = {}
    for sample in manifest["samples"]:
        counts[sample["ground_truth_label"]] = counts.get(sample["ground_truth_label"], 0) + 1
    return counts


def main(run_dir):
    report = {"check": "d1-labels", "pass": False, "details": []}
    original = json.load(open(os.path.join(DS_DIR, "manifest.json")))
    copy_dir = os.path.join(run_dir, "dataset-copy")
    shutil.copytree(DS_DIR, copy_dir)
    copied = json.load(open(os.path.join(copy_dir, "manifest.json")))
    if label_counts(copied) != label_counts(original):
        report["details"].append("per-label counts differ: %s vs %s"
                                 % (label_counts(copied), label_counts(original)))
    if pairing(copied) != pairing(original):
        report["details"].append("pairing set differs")
    for sample in copied["samples"]:
        if not os.path.isfile(os.path.join(copy_dir, sample["text_file"])):
            report["details"].append("copied file missing: " + sample["text_file"])
    if not report["details"]:
        report["details"].append("%d pairings + counts identical after clean-dir copy"
                                 % len(original["samples"]))
    report["pass"] = not [d for d in report["details"] if "identical" not in d]
    json.dump(report, open(os.path.join(run_dir, "check-d1-labels.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d1-labels: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
