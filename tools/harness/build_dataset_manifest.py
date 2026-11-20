"""Dataset manifest builder — constructs datasets/<version>/manifest.json from a texts dir.

ID scheme (origin: D1 decision, frozen for v1): <H|A>-<topic>-<band>-<n>.txt
maps to sample_id <H|A>-<topic>-<band>-<n>, ground_truth_label human|ai,
provenance authored-human-style-for-evaluation | generated-ai-for-evaluation.
The manifest is the source of truth from here on; later versions are new files.
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as cfg

# origin: D1 decision — ID scheme frozen for v1 (see module docstring).
ID_PREFIX_LABEL = {"H": ("human", "authored-human-style-for-evaluation"),
                   "A": ("ai", "generated-ai-for-evaluation")}


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--texts-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--languages", default="en")
    args = parser.parse_args(argv)
    names = sorted(f for f in os.listdir(args.texts_dir) if f.endswith(".txt"))
    samples = []
    for name in names:
        stem = name[:-4]
        parts = stem.split("-")
        arm, band, num = parts[0], parts[-2], parts[-1]
        topic = "-".join(parts[1:-2])
        label, provenance = ID_PREFIX_LABEL[arm]
        text = open(os.path.join(args.texts_dir, name)).read()
        samples.append({
            "sample_id": stem,
            "text_file": "texts/" + name,
            "text_sha256": sha256_file(os.path.join(args.texts_dir, name)),
            "word_count": len(text.split()),
            "ground_truth_label": label,
            "topic": topic,
            "length_band": band,
            "provenance": provenance,
        })
    ds = cfg.load("datasets.yaml")
    manifest = {
        "dataset_version": args.version,
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config_hashes": {"datasets.yaml": sha256_file(
            os.path.join(cfg.CONFIG_DIR, "datasets.yaml"))},
        "languages": args.languages.split(","),
        "id_scheme": "<H|A>-<topic>-<band>-<n>",
        "briefs": "build/evidence/D1/generation-briefs.md",
        "samples": samples,
        "variant_slots": [],
        "variant_slot_schema": "D3 fills: {slot_id, source_sample_id, condition_id, pipeline_id, config_hash}; v1 ships empty per D1 scope",
    }
    if os.path.exists(args.out):
        print("refusing to overwrite " + args.out, file=sys.stderr)
        return 1
    with open(args.out, "w") as fh:
        json.dump(manifest, fh, indent=2)
    print("wrote %s with %d samples" % (args.out, len(samples)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
