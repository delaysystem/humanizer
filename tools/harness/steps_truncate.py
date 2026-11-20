"""Step: truncate@v1 — hard word cut to target_words (config/steps/truncate-v1.yaml).

Same contract as truncate@v2 (see steps_truncate_v2.py); the two exist to prove
§3B replaceability (same contract, different implementation).
"""
import copy


def run(text, metadata, params, ctx):
    target = int(params["target_words"])
    words = text.split()
    cut = " ".join(words[:target])
    metadata = copy.deepcopy(metadata)
    metadata["provenance"] = metadata["provenance"] + [
        {"step": metadata["current_step"], "version": metadata["current_version"],
         "params": {"target_words": target, "in_words": len(words),
                    "out_words": len(cut.split())}}]
    return cut, metadata
