#!/usr/bin/env python3
"""Claude Code status-line tap: save the plan usage limits for the dashboard, pass stdin through untouched.

Used as `python3 usage_tap.py | <real status line command>` in ~/.claude/settings.json.
Must never break the status line, so every failure is swallowed after the bytes are passed on.
"""
import json
import os
import sys
import time
from pathlib import Path

OUT = Path(__file__).parent / ".claude_usage.json"


def merge_window(old: dict | None, new: dict | None) -> dict | None:
    """Several sessions report the same window; idle ones repeat stale, lower numbers.
    Usage only rises within a window, so keep the max for the same reset time; a later reset is a new window."""
    if not isinstance(new, dict):
        return old
    if not isinstance(old, dict) or (new.get("resets_at") or 0) > (old.get("resets_at") or 0):
        return new
    if new.get("resets_at") == old.get("resets_at"):
        return max(old, new, key=lambda w: w.get("used_percentage") or 0)
    return old  # an older window than we already have


def extract(payload: dict, previous: dict | None = None) -> dict | None:
    limits = payload.get("rate_limits")
    if not isinstance(limits, dict) or not limits:
        return None
    old = (previous or {}).get("rate_limits") or {}
    merged = {k: merge_window(old.get(k), limits.get(k)) for k in set(old) | set(limits)}
    return {"rate_limits": {k: v for k, v in merged.items() if v}, "saved_at": time.time()}


def read_previous() -> dict | None:
    try:
        return json.loads(OUT.read_text())
    except Exception:  # noqa: BLE001 — missing or half-written file just means no history
        return None


def main() -> None:
    raw = sys.stdin.buffer.read()
    sys.stdout.buffer.write(raw)  # pass through first: the real status line must always get its input
    sys.stdout.flush()
    try:
        snapshot = extract(json.loads(raw or b"{}"), read_previous())
        if snapshot:
            tmp = OUT.with_suffix(f".{os.getpid()}.tmp")  # per-process: several sessions write at once
            tmp.write_text(json.dumps(snapshot))
            os.replace(tmp, OUT)  # atomic, so the dashboard never reads half a file
    except Exception:  # noqa: BLE001 — a broken tap must not break Claude Code's status line
        pass


if __name__ == "__main__":
    main()
