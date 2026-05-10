"""Shared CLI envelope for skill scripts.

Each script:

    from skills.bookkeeping.scripts._cli import run

    def main(payload: dict) -> dict:
        ...

    if __name__ == "__main__":
        run(main)

`run` parses `argv[1]` (or stdin if argv is empty) as JSON, hands the
dict to `main`, prints the returned dict on stdout, and converts any
domain exception into a JSON error envelope on stdout (still single
line) with exit code 1.

The skill ships its scripts inside a directory tree that gets cloned
into the sandbox; sys.path manipulation here makes `from _common
import ...` work whether the script is run as a module or directly
(`python scripts/journalize.py`).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Ensure the skill root is on sys.path so `_common` resolves whether
# the script is run from the skill root, the scripts dir, or as a
# module path. The skill is designed to be self-contained.
_SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))


def _read_input() -> dict[str, Any]:
    """Read JSON input from argv[1], or stdin when argv is empty."""
    raw = ""
    if len(sys.argv) > 1:
        raw = sys.argv[1]
    else:
        raw = sys.stdin.read()
    if not raw.strip():
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(
            f"skill input must be a JSON object; got {type(parsed).__name__}",
        )
    return parsed


def run(main: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    """Wrap `main(payload)` with input parsing + error envelope."""
    try:
        payload = _read_input()
        result = main(payload)
        sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        sys.stdout.write("\n")
    except Exception as exc:
        envelope = {
            "error": type(exc).__name__,
            "message": str(exc),
        }
        sys.stdout.write(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))
        sys.stdout.write("\n")
        sys.exit(1)
