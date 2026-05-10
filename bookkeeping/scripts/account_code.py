#!/usr/bin/env python3
"""Generate the next available account code for a (classification, sub) bucket.

Numbering convention follows Malaysian SME packages (UBS / SQL Account /
AutoCount). See SKILL.md for the full range table.

Input:
    {
      "existing_codes": ["100-0000", "200-0001", ...],
      "classification": "ASSET" | "LIABILITY" | "EQUITY" | "INCOME" | "EXPENSE" | "COGS",
      "sub_classification": "FIXED_ASSET" | "CURRENT_ASSET" | ...
    }

Output:
    {"account_code": "200-0001"}
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_p = Path(__file__).resolve()
while _p.parent != _p and not (_p / "_common").is_dir():
    _p = _p.parent
if str(_p) not in sys.path:
    sys.path.insert(0, str(_p))

from _common._cli import run  # noqa: E402
from _common.domain_errors import AccountCodeGenerationError  # noqa: E402
from _common.models import Classification, SubClassification  # noqa: E402

# Prefix range per (classification, sub_classification). End is inclusive.
_RANGES: dict[tuple[Classification, SubClassification], tuple[int, int]] = {
    (Classification.EQUITY, SubClassification.CAPITAL): (100, 149),
    (Classification.EQUITY, SubClassification.RETAINED_EARNING): (150, 199),
    (Classification.ASSET, SubClassification.FIXED_ASSET): (200, 299),
    (Classification.ASSET, SubClassification.CURRENT_ASSET): (300, 399),
    (Classification.LIABILITY, SubClassification.CURRENT_LIABILITY): (400, 499),
    (Classification.INCOME, SubClassification.SALES): (500, 599),
    (Classification.INCOME, SubClassification.OTHER_INCOMES): (540, 599),
    (Classification.COGS, SubClassification.COGS): (600, 699),
    (Classification.EXPENSE, SubClassification.EXPENSES): (700, 989),
    (Classification.EXPENSE, SubClassification.TAXATION): (990, 998),
}

_CODE_LENGTH = 8  # NNN-NNNN
_DASH_INDEX = 3


def next_code(
    existing_codes: tuple[str, ...],
    classification: Classification,
    sub_classification: SubClassification,
) -> str:
    bounds = _RANGES.get((classification, sub_classification))
    if bounds is None:
        raise AccountCodeGenerationError(
            f"No auto-numbering range for "
            f"({classification.value}, {sub_classification.value}). "
            f"Edit _RANGES in scripts/account_code.py to add one.",
        )

    start_prefix, end_prefix = bounds
    used_serials_per_prefix: dict[int, set[int]] = {
        prefix: set() for prefix in range(start_prefix, end_prefix + 1)
    }
    for code in existing_codes:
        parsed = _parse(code)
        if parsed is None:
            continue
        prefix, serial = parsed
        if start_prefix <= prefix <= end_prefix:
            used_serials_per_prefix[prefix].add(serial)

    for prefix in range(start_prefix, end_prefix + 1):
        taken = used_serials_per_prefix[prefix]
        for serial in range(0, 10_000):
            if serial not in taken:
                return f"{prefix:03d}-{serial:04d}"

    raise AccountCodeGenerationError(
        f"No free code remains in range "
        f"{start_prefix:03d}-0000..{end_prefix:03d}-9999. "
        f"Bucket exhausted (~{(end_prefix - start_prefix + 1) * 10_000} accounts).",
    )


def _parse(code: str) -> tuple[int, int] | None:
    if len(code) != _CODE_LENGTH or code[_DASH_INDEX] != "-":
        return None
    prefix_str = code[:_DASH_INDEX]
    serial_str = code[_DASH_INDEX + 1 :]
    if not prefix_str.isdigit() or not serial_str.isdigit():
        return None
    return int(prefix_str), int(serial_str)


def main(payload: dict[str, Any]) -> dict[str, Any]:
    codes_raw = payload.get("existing_codes", [])
    if not isinstance(codes_raw, list):
        raise ValueError("existing_codes must be a list of strings")
    classification_raw = payload.get("classification")
    sub_raw = payload.get("sub_classification")
    if not isinstance(classification_raw, str) or not classification_raw:
        raise ValueError("classification is required")
    if not isinstance(sub_raw, str) or not sub_raw:
        raise ValueError("sub_classification is required")
    return {
        "account_code": next_code(
            existing_codes=tuple(str(c) for c in codes_raw),
            classification=Classification(classification_raw),
            sub_classification=SubClassification(sub_raw),
        ),
    }


if __name__ == "__main__":
    run(main)
