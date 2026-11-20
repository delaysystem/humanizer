"""Apply-phase deploy helper: up/down/status for one entry's isolated deployment.

Reads config/apply.yaml (image, container name, ports, volume, network).
Up creates the container on the apply network with the apply models
volume, waits for /health, and records the deployment facts JSON. Down
removes the container. Only one deployment runs at a time (host RAM).
Usage: deploy.py up|down|status --entry FIX-D3A-001
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "..", "harness"))
import config as cfg  # noqa: E402

ROOT = os.path.abspath(__file__)
for _ in range(3):
    ROOT = os.path.dirname(ROOT)

# Origin: apply decision — uvicorn is up within seconds; model checks may
# retry briefly; past this the container is broken and must be diagnosed.
HEALTH_WAIT_S = 180
HEALTH_POLL_S = 5


def entry_cfg(entry):
    apply_cfg = cfg.load("apply.yaml")
    if entry not in apply_cfg["apply_entries"]:
        raise ValueError("unknown entry " + entry)
    get = lambda key: cfg.require_resolved(apply_cfg, key, "config/apply.yaml")
    return {
        "condition": get("apply_%s_condition" % entry),
        "image": get("apply_%s_image" % entry),
        "container": get("apply_%s_container" % entry),
        "port": get("apply_%s_port" % entry),
        "cport": get("apply_container_port"),
        "volume": get("apply_volume"),
        "network": get("apply_network"),
    }


def running(name):
    done = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                          capture_output=True, text=True, check=True)
    return name in done.stdout.split()


def health(base):
    try:
        with urllib.request.urlopen(base + "/health", timeout=10) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001 — health is boolean
        return False


def endpoint_url(port):
    scheme = cfg.require_resolved(cfg.load("apply.yaml"), "apply_url_scheme",
                                  "config/apply.yaml")
    return "%s://localhost:%s" % (scheme, port)


def cmd_up(entry):
    cfg_e = entry_cfg(entry)
    if running(cfg_e["container"]):
        raise ValueError(cfg_e["container"] + " already running")
    subprocess.run(["docker", "rm", "-f", cfg_e["container"]],
                   capture_output=True)
    create = subprocess.run(
        ["docker", "run", "-d", "--name", cfg_e["container"],
         "--network", cfg_e["network"],
         "-v", "%s:/app/models" % cfg_e["volume"],
         "-p", "%s:%s" % (cfg_e["port"], cfg_e["cport"]),
         "--health-cmd", "python -c \"import urllib.request; "
         "urllib.request.urlopen('%s/health')\" || exit 1"
         % endpoint_url(cfg_e["cport"]),
         cfg_e["image"], "python", "-m", "uvicorn", "app.main:app",
         "--host", "0.0.0.0", "--port", str(cfg_e["cport"])],
        capture_output=True, text=True)
    if create.returncode != 0:
        raise ValueError("create failed: %s" % create.stderr.strip()[:300])
    base = endpoint_url(cfg_e["port"])
    deadline = time.time() + HEALTH_WAIT_S
    while time.time() < deadline:
        if health(base):
            break
        time.sleep(HEALTH_POLL_S)
    else:
        logs = subprocess.run(["docker", "logs", cfg_e["container"]],
                              capture_output=True, text=True)
        raise ValueError("unhealthy after %ds: %s"
                         % (HEALTH_WAIT_S, logs.stdout[-800:] + logs.stderr[-800:]))
    cid = subprocess.run(["docker", "inspect", "--format", "{{.Id}}",
                          cfg_e["container"]], capture_output=True, text=True,
                         check=True).stdout.strip()
    facts = {"entry": entry, "condition": cfg_e["condition"],
             "container": cfg_e["container"], "container_id": cid,
             "image": cfg_e["image"], "endpoint": base,
             "volume": cfg_e["volume"], "network": cfg_e["network"]}
    with open(os.path.join(ROOT, "build/evidence/APPLY/deploy-%s.json" % entry),
              "w") as fh:
        json.dump(facts, fh, indent=2, sort_keys=True)
    print("up: %s at %s" % (cfg_e["container"], base))
    return 0


def cmd_down(entry):
    cfg_e = entry_cfg(entry)
    subprocess.run(["docker", "rm", "-f", cfg_e["container"]], capture_output=True)
    print("down: %s removed" % cfg_e["container"])
    return 0


def cmd_status(entry):
    cfg_e = entry_cfg(entry)
    base = endpoint_url(cfg_e["port"])
    print("%s running=%s healthy=%s" % (
        cfg_e["container"], running(cfg_e["container"]), health(base)))
    return 0


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("up", "down", "status"))
    ap.add_argument("--entry", required=True)
    args = ap.parse_args(argv)
    return {"up": cmd_up, "down": cmd_down, "status": cmd_status}[args.action](args.entry)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
