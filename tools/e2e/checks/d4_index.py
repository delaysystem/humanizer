"""D4 E2E-2b (independent path): INDEX.md and INDEX.yaml agree field-for-field;
every entry has meta.yaml status PROPOSED_NOT_APPLIED; every retraining-type
fix has data-spec.md with a quarantine rule; every threshold-simulation.md
has a 'cannot prove' section; verification + evidence links resolve.
"""
import glob
import json
import os
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)

MD_COLUMNS = ["fix_id", "target_detector_ids[]", "failure_ids[]", "condition_ids[]",
              "status", "fix_type", "simulation", "evidence_artifact_ids[]",
              "verification_spec_id"]
LIST_COLUMNS = {"target_detector_ids[]", "failure_ids[]", "condition_ids[]",
                "evidence_artifact_ids[]"}
YAML_KEYS = {"target_detector_ids", "failure_ids", "condition_ids", "status",
             "fix_type", "simulation", "evidence_artifact_ids", "verification_spec_id"}
FIX_TYPES = {"threshold", "augmentation"}
SIMULATIONS = {"spec_only", "computed_estimates"}


def read_index_md(path):
    rows = {}
    header_seen = False
    for line in open(path):
        if line.startswith("| fix_id |"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cells != MD_COLUMNS:
                raise ValueError("INDEX.md columns drifted: %r" % cells)
            header_seen = True
            continue
        if line.startswith("| FIX-"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            row = dict(zip(MD_COLUMNS, cells))
            for col in LIST_COLUMNS:
                row[col] = {v.strip() for v in row[col].split(",") if v.strip()}
            rows[row["fix_id"]] = row
    if not header_seen:
        raise ValueError("INDEX.md header missing")
    return rows


def read_index_yaml(path):
    fixes = {}
    current = None
    for line in open(path):
        if line.startswith("  - fix_id: "):
            current = {"fix_id": line.split(": ", 1)[1].strip()}
            fixes[current["fix_id"]] = current
        elif line.startswith("    ") and current is not None and ": " in line:
            key, val = line.strip().split(": ", 1)
            if val.startswith("[") and val.endswith("]"):
                val = {v.strip() for v in val[1:-1].split(",") if v.strip()}
            current[key] = val
    return fixes


def main(run_dir, fixes_dir):
    report = {"check": "d4-index", "pass": False, "details": []}
    try:
        md_rows = read_index_md(os.path.join(fixes_dir, "INDEX.md"))
        yaml_rows = read_index_yaml(os.path.join(fixes_dir, "INDEX.yaml"))
    except ValueError as exc:
        report["details"].append("index parse: %s" % exc)
        md_rows, yaml_rows = {}, {}
    if set(md_rows) != set(yaml_rows):
        report["details"].append("fix-id sets differ: %s" %
                                 (set(md_rows) ^ set(yaml_rows)))
    for fix_id in sorted(set(md_rows) & set(yaml_rows)):
        md_row, yaml_row = md_rows[fix_id], yaml_rows[fix_id]
        for md_col in MD_COLUMNS[1:]:
            yaml_key = md_col[:-2] if md_col in LIST_COLUMNS else md_col
            if yaml_row.get(yaml_key) != md_row[md_col]:
                report["details"].append("%s: field %s differs" % (fix_id, yaml_key))
                break
        if yaml_row.get("fix_type") not in FIX_TYPES:
            report["details"].append("%s: unknown fix_type" % fix_id)
        if yaml_row.get("simulation") not in SIMULATIONS:
            report["details"].append("%s: unknown simulation" % fix_id)
        fix_dir = os.path.join(fixes_dir, fix_id)
        meta_path = os.path.join(fix_dir, "meta.yaml")
        try:
            status = [ln.split("status:", 1)[1].strip() for ln in open(meta_path)
                      if ln.startswith("status:")][0]
        except (OSError, IndexError):
            status = None
        if status != "PROPOSED_NOT_APPLIED":
            report["details"].append("%s: meta status %r" % (fix_id, status))
        if yaml_row.get("fix_type") == "augmentation":
            try:
                spec = open(os.path.join(fix_dir, "data-spec.md")).read()
            except OSError:
                spec = ""
            if "quarantine" not in spec.lower():
                report["details"].append("%s: data-spec lacks quarantine" % fix_id)
        try:
            sim = open(os.path.join(fix_dir, "threshold-simulation.md")).read()
        except OSError:
            sim = ""
        if "cannot prove" not in sim.lower():
            report["details"].append("%s: simulation lacks cannot-prove" % fix_id)
        verif = os.path.join(ROOT, yaml_row.get("verification_spec_id", ""))
        if not os.path.isfile(verif):
            report["details"].append("%s: verification spec missing" % fix_id)
        for path in yaml_row.get("evidence_artifact_ids", set()):
            full = os.path.join(ROOT, path)
            found = glob.glob(full) if "*" in path else ([full] if os.path.isfile(full) else [])
            if not found:
                report["details"].append("%s: evidence missing %s" % (fix_id, path))
    if not report["details"]:
        report["details"].append("%d entries: MD=YAML field-for-field, statuses honest, links resolve"
                                 % len(md_rows))
    report["pass"] = not [d for d in report["details"] if "field-for-field" not in d]
    json.dump(report, open(os.path.join(run_dir, "check-d4-index.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d4-index: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
