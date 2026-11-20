"""Results store writer — per-sample records per config/results-schema.json.

Layout under a store root: records/<sample_id>.json, raw/<sample_id>.json
(Sloptotal report verbatim), blocked.json (EXTERNAL-BLOCKED samples, never
scored), attempts-<run_id>.log (JSONL request log, unique per run).
"""
import json
import os

REQUIRED = ["sample_id", "original_id", "ground_truth_label", "condition_id",
            "transform_params", "provenance", "variant_text_ref",
            "per_detector_scores", "fidelity", "store_record_id"]


def write_record(store_root, record):
    missing = [f for f in REQUIRED if f not in record]
    if missing:
        raise ValueError("record missing fields: %s" % missing)
    path = os.path.join(store_root, "records", record["sample_id"] + ".json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(record, fh, indent=2)
    return path


def write_raw(store_root, sample_id, report):
    path = os.path.join(store_root, "raw", sample_id + ".json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(report, fh, indent=2)
    return path


def append_blocked(store_root, entry):
    path = os.path.join(store_root, "blocked.json")
    blocked = []
    if os.path.exists(path):
        blocked = json.load(open(path))
    blocked.append(entry)
    with open(path, "w") as fh:
        json.dump(blocked, fh, indent=2)
    return path


class AttemptLog:
    def __init__(self, store_root, run_id):
        self.path = os.path.join(store_root, "attempts-%s.log" % run_id)
        os.makedirs(store_root, exist_ok=True)
        self.fh = open(self.path, "w")

    def event(self, obj):
        self.fh.write(json.dumps(obj) + "\n")
        self.fh.flush()

    def close(self):
        self.fh.close()
