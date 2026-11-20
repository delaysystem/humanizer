"""Evidence writer — append-only artifact writes (Rule 3 / P4).

Every artifact is written once with a run envelope. Overwriting an existing
artifact file is refused: a corrected run writes to a NEW run directory.
"""
import json
import os
from datetime import datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(relpath, obj, run_id):
    """Write obj as JSON under the project root. Fails if the file exists."""
    path = os.path.join(PROJECT_ROOT, relpath)
    if os.path.exists(path):
        raise FileExistsError("refusing to overwrite evidence artifact: " + relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    envelope = {"run_id": run_id, "written_utc": utcnow(), "artifact": relpath,
                "payload": obj}
    with open(path, "w") as fh:
        json.dump(envelope, fh, indent=2)
        fh.write("\n")
    return path


def write_text(relpath, text, run_id):
    """Write raw text (transcripts, logs). Fails if the file exists."""
    path = os.path.join(PROJECT_ROOT, relpath)
    if os.path.exists(path):
        raise FileExistsError("refusing to overwrite evidence artifact: " + relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    header = "# run_id: %s\n# written_utc: %s\n# artifact: %s\n" % (run_id, utcnow(), relpath)
    with open(path, "w") as fh:
        fh.write(header + text)
    return path
