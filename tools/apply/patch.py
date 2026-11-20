"""Apply-phase patcher: generate per-entry derived sources from sweep candidates.

Reads sweep-<condition>.json + the D0 inventory (name→file-stem map) +
extracted originals (build/evidence/APPLY/orig/). For each of the six
entry-conditions it emits patched schemas.py (ENGINE_SLOP_BOUNDARY dict
with that condition's candidates) and patched engine files (real-path
call site passes the engine stem; 0.0 error paths untouched) into
build/evidence/APPLY/patch-<condition>/ with unified diffs + manifest.
Candidates at or below the fixed 0.4 clean boundary are skipped with a
recorded reason (A3 realizability rule). Every replacement must hit
exactly once or the run aborts loudly. Deterministic.
"""
import glob
import json
import os
import sys

ROOT = os.path.abspath(__file__)
for _ in range(3):
    ROOT = os.path.dirname(ROOT)

ORIG = os.path.join(ROOT, "build", "evidence", "APPLY", "orig")
CLEAN_BOUNDARY = 0.4
DEPLOYED_SLOP = 0.65


def load_json(path):
    with open(path) as fh:
        return json.load(fh)


def replace_once(text, old, new, where):
    if text.count(old) != 1:
        raise ValueError("%s: pattern hits %d times, want 1" % (where, text.count(old)))
    return text.replace(old, new)


def main():
    inv = load_json(os.path.join(
        ROOT, "build/evidence/D0/frozen/inventory.json"))["payload"]["detectors"]
    stem_of = {d["name"]: d["key"] for d in inv}
    base = load_json(os.path.join(
        ROOT, "build/evidence/D0/frozen/docker-baseline.json"))["payload"]
    image = base["repo_digest_pinned"]
    orig_schemas = open(os.path.join(ORIG, "schemas.py")).read()
    anchor = ("def score_to_engine_verdict(score: float) -> Verdict:\n"
              "    if score < 0.4:\n"
              "        return Verdict.CLEAN\n"
              "    elif score < 0.65:\n"
              "        return Verdict.SUSPICIOUS\n"
              "    else:\n"
              "        return Verdict.SLOP\n")
    if anchor not in orig_schemas:
        raise ValueError("schemas.py anchor not found verbatim")
    total_applied, total_skipped = 0, 0
    for path in sorted(glob.glob(os.path.join(
            ROOT, "build", "evidence", "APPLY", "sweep-*.json"))):
        sweep = load_json(path)
        condition = sweep["condition"]
        applied, skipped = {}, []
        for name, cell in sorted(sweep["detectors"].items()):
            cand = cell["candidate_T"]
            if cand is None:
                continue
            if cand <= CLEAN_BOUNDARY:
                skipped.append({"detector": name, "T": cand,
                                "reason": "at/below fixed clean boundary; unrealizable"})
                total_skipped += 1
                continue
            applied[stem_of[name]] = cand
            total_applied += 1
        patch_dir = os.path.join(ROOT, "build", "evidence", "APPLY", "patch-" + condition)
        os.makedirs(patch_dir, exist_ok=True)
        entries = "\n".join('    "%s": %s,' % (stem, applied[stem])
                            for stem in sorted(applied))
        patched_fn = ("# Apply-phase A3 (%s): per-engine slop boundaries from the frozen sweep.\n"
                      "# Unlisted engines keep the deployed 0.65.\n"
                      "ENGINE_SLOP_BOUNDARY = {\n%s\n}\n\n\n"
                      "def score_to_engine_verdict(score: float, engine=None) -> Verdict:\n"
                      "    slop = ENGINE_SLOP_BOUNDARY.get(engine, 0.65)\n"
                      "    if score < 0.4:\n"
                      "        return Verdict.CLEAN\n"
                      "    elif score < slop:\n"
                      "        return Verdict.SUSPICIOUS\n"
                      "    else:\n"
                      "        return Verdict.SLOP\n" % (condition, entries))
        patched_schemas = replace_once(orig_schemas, anchor, patched_fn, "schemas.py")
        with open(os.path.join(patch_dir, "schemas.py"), "w") as fh:
            fh.write(patched_schemas)
        for stem in sorted(applied):
            orig_text = open(os.path.join(ORIG, stem + ".py")).read()
            edited, hits = orig_text, 0
            for var in ("score", "final_score"):
                old = "score_to_engine_verdict(%s)" % var
                if old in edited:
                    edited = replace_once(
                        edited, old,
                        "score_to_engine_verdict(%s, \"%s\")" % (var, stem),
                        "%s.py %s" % (stem, var))
                    hits += 1
            if hits != 1:
                raise ValueError("%s.py: %d real-path call sites, want 1" % (stem, hits))
            with open(os.path.join(patch_dir, "engines_" + stem + ".py"), "w") as fh:
                fh.write(edited)
        dockerfile = ["FROM %s" % image, "COPY schemas.py /app/app/schemas.py"]
        for stem in sorted(applied):
            dockerfile.append("COPY engines_%s.py /app/app/engines/%s.py" % (stem, stem))
        with open(os.path.join(patch_dir, "Dockerfile"), "w") as fh:
            fh.write("\n".join(dockerfile) + "\n")
        manifest = {"condition": condition, "base_image": image,
                    "applied": applied, "skipped": skipped,
                    "files": sorted(os.listdir(patch_dir))}
        with open(os.path.join(patch_dir, "manifest.json"), "w") as fh:
            json.dump(manifest, fh, indent=2, sort_keys=True)
        print("%s: applied %d, skipped %d" % (condition, len(applied), len(skipped)))
    print("total applied: %d, skipped: %d" % (total_applied, total_skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
