#!/usr/bin/env python3
"""Generate the next voucher number for a (voucher_type, posting_date).

Format: `<TYPE><YYMM>-<4-digit serial>` (e.g. `PV2410-0001`).
Serial resets per `(voucher_type, year_month)`.

Input:
    {
      "existing_journal_refs": ["PV2410-0001", "OB-2024-11-01", ...],
      "voucher_type": "PV" | "OR" | "JV" | "CN" | "DN",
      "posting_date": "2024-10-15"
    }

Output:
    {"voucher_number": "PV2410-0002"}
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

# Walk up to the skill root (first parent that contains `_common/`).
_p = Path(__file__).resolve()
while _p.parent != _p and not (_p / "_common").is_dir():
    _p = _p.parent
if str(_p) not in sys.path:
    sys.path.insert(0, str(_p))

from _common._cli import run  # noqa: E402
from _common.domain_errors import VoucherNumberGenerationError  # noqa: E402
from _common.models import VoucherType, _date  # noqa: E402

_REF_PATTERN = re.compile(r"^([A-Z]{2})(\d{2})(\d{2})-(\d{4})$")


def next_voucher_number(
    existing_journal_refs: tuple[str, ...],
    voucher_type: VoucherType,
    posting_date_str: str,
) -> str:
    posting_date = _date(posting_date_str)
    type_str = voucher_type.value
    year_2digit = posting_date.year % 100
    month_2digit = posting_date.month
    used_serials: set[int] = set()
    for ref in existing_journal_refs:
        match = _REF_PATTERN.match(ref)
        if match is None:
            continue
        ref_type, ref_year, ref_month, ref_serial = match.groups()
        if (
            ref_type == type_str
            and int(ref_year) == year_2digit
            and int(ref_month) == month_2digit
        ):
            used_serials.add(int(ref_serial))

    for serial in range(1, 10_000):
        if serial not in used_serials:
            return f"{type_str}{year_2digit:02d}{month_2digit:02d}-{serial:04d}"

    raise VoucherNumberGenerationError(
        f"No free serial in {type_str}{year_2digit:02d}{month_2digit:02d} bucket "
        f"(9999 vouchers in one month).",
    )


def main(payload: dict[str, Any]) -> dict[str, Any]:
    refs_raw = payload.get("existing_journal_refs", [])
    if not isinstance(refs_raw, list):
        raise ValueError("existing_journal_refs must be a list of strings")
    voucher_type_raw = payload.get("voucher_type")
    if not isinstance(voucher_type_raw, str) or not voucher_type_raw:
        raise ValueError("voucher_type is required (PV/OR/JV/CN/DN)")
    posting_date_raw = payload.get("posting_date")
    if not isinstance(posting_date_raw, str) or not posting_date_raw:
        raise ValueError("posting_date is required (ISO YYYY-MM-DD)")

    voucher_number = next_voucher_number(
        existing_journal_refs=tuple(str(r) for r in refs_raw),
        voucher_type=VoucherType(voucher_type_raw),
        posting_date_str=posting_date_raw,
    )
    return {"voucher_number": voucher_number}


if __name__ == "__main__":
    run(main)
