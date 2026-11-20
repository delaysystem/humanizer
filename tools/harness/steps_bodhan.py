"""Step: bodhan legs — one translation leg via the frozen chat transport.

Contract: run(text, metadata, params, ctx) -> (text, metadata). Params from
config/steps/bodhan-*.yaml only. Never changes ground_truth_label; appends to
the provenance chain. Transport errors retry with identical params (bounded,
config backoff); HTTP 4xx raises BodhanError without retry (fault path).
Budget is enforced before every attempt: exceeding it raises BudgetExceeded.
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as cfg

# origin: D3 decision — generous ceiling; observed Bodhan legs take ~2 s.
BODHAN_TIMEOUT_S = 60


class BodhanError(Exception):
    pass


class BudgetExceeded(Exception):
    pass


def run(text, metadata, params, ctx):
    target = params["target_language_code"]
    script = params.get("target_script", "native")
    max_attempts = ctx["max_attempts"]
    backoff = ctx["backoff"]
    last_error = None
    for attempt in range(1, max_attempts + 1):
        if ctx["calls"] >= ctx["max_calls"]:
            raise BudgetExceeded("bodhan budget %d exhausted" % ctx["max_calls"])
        if attempt == 1 and ctx.get("call_delay"):
            ctx["audit"]({"sample_id": metadata["original_id"], "step": metadata["current_step"],
                          "event": "sleep", "seconds": ctx["call_delay"], "reason": "pacing"})
            time.sleep(ctx["call_delay"])
        payload = {"model": ctx["model"],
                   "messages": [{"role": "user", "content": text}],
                   "target_language_code": target, "target_script": script}
        body = json.dumps(payload).encode()
        req = urllib.request.Request(ctx["base_url"] + ctx["chat_path"], data=body,
                                     headers={"Content-Type": "application/json",
                                              "Authorization": "Bearer " + ctx["key"]},
                                     method="POST")
        ctx["calls"] += 1
        try:
            resp = urllib.request.urlopen(req, timeout=BODHAN_TIMEOUT_S)
            data = json.loads(resp.read())
            content = data["choices"][0]["message"]["content"]
            ctx["audit"]({"sample_id": metadata["original_id"], "step": metadata["current_step"],
                          "attempt": attempt, "http": resp.status, "outcome": "scored",
                          "params_echo": {"target_language_code": target, "target_script": script},
                          "usage": data.get("usage")})
            metadata = dict(metadata)
            metadata["provenance"] = metadata["provenance"] + [
                {"step": metadata["current_step"], "version": metadata["current_version"],
                 "params": {"target_language_code": target, "target_script": script}}]
            return content, metadata
        except urllib.error.HTTPError as exc:
            last_error = "HTTP %s: %s" % (exc.code, exc.read()[:200])
            ctx["audit"]({"sample_id": metadata["original_id"], "step": metadata["current_step"],
                          "attempt": attempt, "http": exc.code, "outcome": last_error,
                          "params_echo": {"target_language_code": target, "target_script": script}})
            wait = backoff
            if exc.code == 429:
                wait = ctx.get("backoff_429") or backoff
                try:
                    retry_after = float(exc.headers.get("Retry-After"))
                    wait = max(wait, retry_after)
                except (TypeError, ValueError, AttributeError):
                    pass
                last_error = "HTTP 429 (backoff %ss): %s" % (wait, last_error)
            elif exc.code not in (500, 502, 503, 504):
                raise BodhanError(last_error)
            if attempt < max_attempts:
                ctx["audit"]({"sample_id": metadata["original_id"], "step": metadata["current_step"],
                              "event": "sleep", "seconds": wait,
                              "reason": "retry-429" if exc.code == 429 else "retry"})
                time.sleep(wait)
            continue
        except Exception as exc:
            last_error = "%s: %s" % (type(exc).__name__, exc)
            ctx["audit"]({"sample_id": metadata["original_id"], "step": metadata["current_step"],
                          "attempt": attempt, "http": None, "outcome": last_error,
                          "params_echo": {"target_language_code": target, "target_script": script}})
            if attempt < max_attempts:
                ctx["audit"]({"sample_id": metadata["original_id"], "step": metadata["current_step"],
                              "event": "sleep", "seconds": backoff, "reason": "retry"})
                time.sleep(backoff)
    raise BodhanError("transport exhausted: %s" % last_error)
