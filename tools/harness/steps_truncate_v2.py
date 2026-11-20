"""Step: truncate@v2 — sentence-boundary cut within target_words.

Same contract as truncate@v1, different implementation: keeps whole sentences
up to the word target (falls back to a hard cut only when no sentence boundary
fits). Exists for the §3B replaceability check.
"""
import copy
import re

SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def run(text, metadata, params, ctx):
    target = int(params["target_words"])
    sentences = [s for s in SENT_SPLIT.split(text.strip()) if s]
    kept, total = [], 0
    for sent in sentences:
        words = sent.split()
        if total + len(words) <= target:
            kept.append(sent)
            total += len(words)
        else:
            break
    cut = " ".join(kept) if kept else " ".join(text.split()[:target])
    metadata = copy.deepcopy(metadata)
    metadata["provenance"] = metadata["provenance"] + [
        {"step": metadata["current_step"], "version": metadata["current_version"],
         "params": {"target_words": target, "in_words": len(text.split()),
                    "out_words": len(cut.split()),
                    "mode": "sentence-boundary" if kept else "hard-cut-fallback"}}]
    return cut, metadata
