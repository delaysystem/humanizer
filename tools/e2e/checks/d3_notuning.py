"""D3 E2E-4 (independent path): no-tuning proof — recompute the recursive
config hashes from disk and require equality with the run manifest's
config_hashes (no mid-run parameter changes).
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


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(run_dir):
    report = {"check": "d3-notuning", "pass": False, "details": []}
    manifest = json.load(open(os.path.join(run_dir, "manifest.json")))["payload"]
    current = {}
    for base, _, files in os.walk(cfg.CONFIG_DIR):
        for name in sorted(files):
            if name.endswith((".yaml", ".json")):
                full = os.path.join(base, name)
                current[os.path.relpath(full, cfg.CONFIG_DIR)] = sha256_file(full)
    frozen = manifest.get("config_hashes", {})
    if current != frozen:
        changed = sorted(set(current) ^ set(frozen))
        changed += [k for k in current if k in frozen and current[k] != frozen[k]]
        report["details"].append("config changed mid-run: %s" % sorted(set(changed)))
    else:
        report["details"].append("%d config files unchanged since run start" % len(current))
    report["pass"] = not [d for d in report["details"] if "unchanged" not in d]
    json.dump(report, open(os.path.join(run_dir, "check-d3-notuning.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d3-notuning: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
