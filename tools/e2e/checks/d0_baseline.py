"""D0 E2E-4 (independent path): live docker inspect matches the frozen baseline field-for-field."""
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
import config as cfg

FIELDS = ["image_digest", "container_id", "container_name", "volume_mounts",
          "port_bindings", "env_count", "entrypoint", "cmd"]


def main(run_dir):
    report = {"check": "d0-baseline", "pass": False, "details": []}
    api = cfg.load("api.yaml")
    name = cfg.require_resolved(api, "sloptotal_container_name", "config/api.yaml")
    frozen = json.load(open(os.path.join(
        ROOT, "build/evidence/D0/frozen/docker-baseline.json")))["payload"]
    live_raw = subprocess.run(["docker", "inspect", name], capture_output=True,
                              text=True, check=True).stdout
    live = json.loads(live_raw)[0]
    current = {
        "image_digest": live["Image"],
        "container_id": live["Id"],
        "container_name": live["Name"],
        "volume_mounts": [{"source": m.get("Source"), "destination": m.get("Destination"),
                           "mode": m.get("Mode"), "rw": m.get("RW")}
                          for m in live.get("Mounts", [])],
        "port_bindings": live["HostConfig"].get("PortBindings"),
        "env_count": len(live["Config"].get("Env", [])),
        "entrypoint": live["Config"].get("Entrypoint"),
        "cmd": live["Config"].get("Cmd"),
    }
    diffs = [f for f in FIELDS if current.get(f) != frozen.get(f)]
    if diffs:
        report["details"].append("mismatched fields: %s" % diffs)
    else:
        report["details"].append("all %d baseline fields match frozen artifact" % len(FIELDS))
    report["pass"] = not diffs
    json.dump(current, open(os.path.join(run_dir, "baseline-live.json"), "w"), indent=2)
    json.dump(report, open(os.path.join(run_dir, "check-d0-baseline.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d0-baseline: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
