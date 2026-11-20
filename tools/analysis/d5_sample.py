"""D5 E2E-1b: deterministic stratified drift sample — N samples per pipeline,
seeded shuffle preferring distinct length bands. Same inputs always yield
the same sample (implementer and verifier regenerate the same SET with
independent fresh calls).

Usage: d5_sample.py --dataset-manifest datasets/v1/manifest.json
  --pipelines cond-rt-kn,cond-truncate-S,d3a-i1,... --seed 42 --per-n 2
  --out build/evidence/D5/runs/<run>/drift-sample.json
"""
import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "harness"))
import config as cfg
import pipeline as pipe


def band_of(manifest, sample_id):
    try:
        band = next(s["length_band"] for s in manifest["samples"]
                    if s["sample_id"] == sample_id)
    except StopIteration:
        raise ValueError("sample not in manifest: " + sample_id)
    if band not in ("S", "M", "L"):
        raise ValueError("bad band for " + sample_id)
    return band


def main(args):
    manifest = json.load(open(args.dataset_manifest))
    pipes = cfg.load("pipelines.yaml")
    rng = random.Random(args.seed)
    sample = {}
    for pipe_id in sorted(args.pipelines.split(",")):
        sel = cfg.require_resolved(pipes, "pipeline_%s_samples" % pipe_id,
                                   "config/pipelines.yaml")
        candidates = sorted(pipe._select(manifest, sel))
        rng.shuffle(candidates)
        picked, bands = [], set()
        for sid in candidates:
            if len(picked) >= args.per_n:
                break
            band = band_of(manifest, sid)
            if band not in bands:
                picked.append(sid)
                bands.add(band)
        for sid in candidates:
            if len(picked) >= args.per_n:
                break
            if sid not in picked:
                picked.append(sid)
        if len(picked) != args.per_n:
            raise ValueError("too few samples for %s" % pipe_id)
        sample[pipe_id] = sorted(picked)
    with open(args.out, "w") as fh:
        json.dump({"seed": args.seed, "per_n": args.per_n, "sample": sample},
                  fh, indent=2, sort_keys=True)
    print("drift sample: %s" % {p: len(s) for p, s in sorted(sample.items())})
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="d5_sample")
    parser.add_argument("--dataset-manifest", required=True)
    parser.add_argument("--pipelines", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--per-n", type=int, required=True)
    parser.add_argument("--out", required=True)
    sys.exit(main(parser.parse_args()))
