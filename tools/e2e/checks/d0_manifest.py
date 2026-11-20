"""D0 E2E-1 (independent path): manifest parses, lists every schema field, run ID matches transcript."""
import json
import os
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)


def main(run_dir):
    report = {"check": "d0-manifest", "pass": False, "details": []}
    manifest = json.load(open(os.path.join(run_dir, "manifest.json")))
    schema = json.load(open(os.path.join(ROOT, "config", "manifest-schema.json")))
    payload = manifest["payload"]
    missing = [f for f in schema["required_fields"] if f not in payload]
    if missing:
        report["details"].append("missing fields: %s" % missing)
    mistyped = [f for f, t in schema["field_types"].items()
                if f in payload and type(payload[f]).__name__ !=
                {"string": "str", "object": "dict", "array": "list"}[t]]
    if mistyped:
        report["details"].append("mistyped fields: %s" % mistyped)
    transcript = open(os.path.join(run_dir, "transcript.log")).read()
    first = transcript.splitlines()[0] if transcript else ""
    want = "# run_id: %s" % payload.get("run_id")
    if first != want:
        report["details"].append("transcript run_id mismatch: %r != %r" % (first, want))
    report["pass"] = not report["details"]
    if report["pass"]:
        report["details"].append("manifest valid; run_id %s matches transcript"
                                 % payload.get("run_id"))
    json.dump(report, open(os.path.join(run_dir, "check-d0-manifest.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d0-manifest: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
