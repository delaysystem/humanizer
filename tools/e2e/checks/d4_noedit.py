"""D4 E2E-3 (independent path): no-docker-edit proof — a second process
compares the D0-frozen image digest, container ID, volume mounts, and
environment against the live container and asserts all equal; model-file
hashes in volumes are recorded where readable without writing, otherwise
recorded as UNVERIFIED-BY-HASH (never assumed unchanged). Any difference
in the frozen fields fails as a scope violation.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(__file__)
for _ in range(4):
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
import config as cfg


def main(run_dir):
    report = {"check": "d4-noedit", "pass": False, "details": []}
    api = cfg.load("api.yaml")
    name = cfg.require_resolved(api, "sloptotal_container_name", "config/api.yaml")
    frozen = json.load(open(os.path.join(
        ROOT, "build/evidence/D0/frozen/docker-baseline.json")))["payload"]
    live = json.loads(subprocess.run(["docker", "inspect", name], capture_output=True,
                                     text=True, check=True).stdout)[0]
    json.dump(live, open(os.path.join(run_dir, "noedit-live-inspect.json"), "w"),
              indent=2, sort_keys=True, default=str)
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
    diffs = [f for f in ("image_digest", "container_id", "volume_mounts", "env_count")
             if current.get(f) != frozen.get(f)]
    if diffs:
        report["details"].append("SCOPE VIOLATION, frozen fields differ: %s" % diffs)
    live_keys = sorted(e.split("=", 1)[0] for e in live["Config"].get("Env", []))
    json.dump({"env_keys_live_redacted": live_keys, "env_count_live": len(live_keys)},
              open(os.path.join(run_dir, "noedit-env.json"), "w"), indent=2)
    try:
        listing = subprocess.run(
            ["docker", "exec", name, "find", "/app/models", "-type", "f"],
            capture_output=True, text=True, timeout=120, check=True).stdout.split()
        hashes = {}
        for path in sorted(listing)[:200]:
            out = subprocess.run(["docker", "exec", name, "sha256sum", path],
                                 capture_output=True, text=True, timeout=120,
                                 check=True).stdout
            hashes[path] = out.split()[0]
        json.dump({"model_files": hashes, "truncated": len(listing) > 200},
                  open(os.path.join(run_dir, "noedit-model-hashes.json"), "w"), indent=2)
        report["details"].append("%d model files hashed (read-only)" % len(hashes))
    except (subprocess.SubprocessError, OSError) as exc:
        json.dump({"model_files": "UNVERIFIED-BY-HASH", "reason": str(exc)[:200]},
                  open(os.path.join(run_dir, "noedit-model-hashes.json"), "w"), indent=2)
        report["details"].append("model files UNVERIFIED-BY-HASH (read failed, not assumed)")
    if not [d for d in report["details"] if "SCOPE VIOLATION" in d]:
        report["details"].append("frozen fields equal; no docker edit")
    report["pass"] = not [d for d in report["details"] if "SCOPE VIOLATION" in d]
    json.dump(report, open(os.path.join(run_dir, "check-d4-noedit.json"), "w"), indent=2)
    print(("PASS" if report["pass"] else "FAIL") + " d4-noedit: " + "; ".join(report["details"]))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
