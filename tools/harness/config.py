"""Config loader — the single named config source reader per component (P2).

Supported subset (deliberately small, stdlib-only):
  - flat `key: value` lines, `#` full-line and trailing comments
  - scalar values: strings, ints, floats (auto-coerced when unambiguous)
  - inline lists: `key: [a, b, c]` (string items; `[probe]` stays a string item)
  - `[probe]` and `[probe ...]` markers load as the literal string; callers use
    `require_resolved()` to refuse unfilled values instead of guessing.
"""
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")


def _strip_comment(line):
    # Cut at the first '#' that is not inside a [...] list.
    depth = 0
    for i, ch in enumerate(line):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth = max(0, depth - 1)
        elif ch == "#" and depth == 0:
            return line[:i]
    return line


def _coerce_scalar(raw):
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        return raw[1:-1]
    for conv in (int, float):
        try:
            if conv is float and "." not in raw and "e" not in raw.lower():
                continue
            return conv(raw)
        except ValueError:
            continue
    return raw


def _parse_list(raw):
    inner = raw.strip()[1:-1].strip()
    if not inner:
        return []
    return [item.strip() for item in inner.split(",")]


def _is_list(raw):
    # Bracketed values are inline lists — except [probe] markers, which stay
    # scalar so require_resolved() keeps refusing them. Single-element lists
    # ([truncate@v1], [en], [kn]) must parse as one-item lists, not strings.
    if "," in raw:
        return True
    inner = raw.strip()[1:-1].strip()
    return not (inner == "probe" or inner.startswith("probe ") or inner.startswith("probe-")
                or inner == "" or "[" in inner)


def load(name):
    """Load config/<name> into a dict. Raises FileNotFoundError / ValueError."""
    path = os.path.join(CONFIG_DIR, name)
    values = {}
    with open(path) as fh:
        for lineno, line in enumerate(fh, 1):
            line = _strip_comment(line).strip()
            if not line:
                continue
            if ":" not in line:
                raise ValueError("%s:%d: expected 'key: value'" % (name, lineno))
            key, raw = line.split(":", 1)
            key, raw = key.strip(), raw.strip()
            if raw.startswith("[") and raw.endswith("]") and _is_list(raw):
                values[key] = _parse_list(raw)
            else:
                values[key] = _coerce_scalar(raw)
    return values


def is_probe(value):
    return isinstance(value, str) and value.startswith("[probe")


def require_resolved(values, key, source_hint):
    """Return values[key] or raise if it is an unfilled [probe] marker."""
    if key not in values:
        raise KeyError("missing config key %r (%s)" % (key, source_hint))
    value = values[key]
    if is_probe(value):
        raise ValueError("config key %r is unfilled %s (%s); refusing to guess"
                         % (key, value, source_hint))
    return value
