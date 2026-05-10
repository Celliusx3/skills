#!/usr/bin/env python3
"""Convert flat ledger rows + manual journals into double-entry Journal rows.

The flat ledger records each transaction as ONE row from the bank's POV;
JOURNALIZE expands each into TWO `JournalRow`s.
Manual journals are already double-entry; they pass through unchanged.

Input:
    {
      "flat_ledger": [{...FlatLedgerRow...}, ...],
      "manual_journals": [{...ManualJournalRow...}, ...],
      "period_start": "YYYY-MM-DD",
      "period_end": "YYYY-MM-DD"
    }

Output:
    {"journal": {"rows": [{...JournalRow...}, ...]}}
"""

from __future__ import annotations

import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

_p = Path(__file__).resolve()
while _p.parent != _p and not (_p / "_common").is_dir():
    _p = _p.parent
if str(_p) not in sys.path:
    sys.path.insert(0, str(_p))

from _common._cli import run  # noqa: E402
from _common.domain_errors import (  # noqa: E402
    JournalizeError,
    VoucherNumberGenerationError,
)
from _common.models import (  # noqa: E402
    Direction,
    FlatLedgerRow,
    Journal,
    JournalRow,
    JournalSource,
    ManualJournalRow,
    VoucherType,
    _date,
)

_ZERO = Decimal("0")
_REF_PATTERN = re.compile(r"^([A-Z]{2})(\d{2})(\d{2})-(\d{4})$")


def _next_voucher_number(
    existing_journal_refs: tuple[str, ...],
    voucher_type: VoucherType,
    posting_date: date,
) -> str:
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


def journalize(
    flat_ledger: tuple[FlatLedgerRow, ...],
    manual_journals: tuple[ManualJournalRow, ...],
    period_start: date,
    period_end: date,
) -> Journal:
    if period_end < period_start:
        raise JournalizeError(
            f"period_end ({period_end}) precedes period_start ({period_start}).",
        )
    rows: list[JournalRow] = []
    allocated_refs: list[str] = [m.journal_ref for m in manual_journals]

    for manual in manual_journals:
        if manual.journal_date < period_start or manual.journal_date > period_end:
            continue
        rows.append(_manual_to_journal_row(manual))

    for flat in flat_ledger:
        if flat.posting_date < period_start or flat.posting_date > period_end:
            continue
        voucher_type = _voucher_type_for(flat)
        ref = _next_voucher_number(
            existing_journal_refs=tuple(allocated_refs),
            voucher_type=voucher_type,
            posting_date=flat.posting_date,
        )
        allocated_refs.append(ref)
        rows.extend(_flat_to_journal_rows(flat, ref, voucher_type))

    return Journal(rows=tuple(rows))


def _manual_to_journal_row(manual: ManualJournalRow) -> JournalRow:
    return JournalRow(
        journal_ref=manual.journal_ref,
        journal_date=manual.journal_date,
        voucher_type=VoucherType.JV,
        account_code=manual.account_code,
        description=manual.description,
        debit=manual.debit,
        credit=manual.credit,
        source=manual.source,
        source_file_id="",
    )


def _voucher_type_for(flat: FlatLedgerRow) -> VoucherType:
    if flat.direction == Direction.DEBIT:
        return VoucherType.PV
    return VoucherType.OR


def _flat_to_journal_rows(
    flat: FlatLedgerRow,
    journal_ref: str,
    voucher_type: VoucherType,
) -> list[JournalRow]:
    if flat.direction == Direction.DEBIT:
        # Payment: DR categorized, CR counter.
        return [
            JournalRow(
                journal_ref=journal_ref,
                journal_date=flat.posting_date,
                voucher_type=voucher_type,
                account_code=flat.account_code,
                description=flat.description,
                debit=flat.amount,
                credit=_ZERO,
                source=JournalSource.BANK_VOUCHER,
                source_file_id=flat.source_file_id,
            ),
            JournalRow(
                journal_ref=journal_ref,
                journal_date=flat.posting_date,
                voucher_type=voucher_type,
                account_code=flat.counter_account_code,
                description=flat.description,
                debit=_ZERO,
                credit=flat.amount,
                source=JournalSource.BANK_VOUCHER,
                source_file_id=flat.source_file_id,
            ),
        ]
    # Receipt: DR counter, CR categorized.
    return [
        JournalRow(
            journal_ref=journal_ref,
            journal_date=flat.posting_date,
            voucher_type=voucher_type,
            account_code=flat.counter_account_code,
            description=flat.description,
            debit=flat.amount,
            credit=_ZERO,
            source=JournalSource.BANK_VOUCHER,
            source_file_id=flat.source_file_id,
        ),
        JournalRow(
            journal_ref=journal_ref,
            journal_date=flat.posting_date,
            voucher_type=voucher_type,
            account_code=flat.account_code,
            description=flat.description,
            debit=_ZERO,
            credit=flat.amount,
            source=JournalSource.BANK_VOUCHER,
            source_file_id=flat.source_file_id,
        ),
    ]


def main(payload: dict[str, Any]) -> dict[str, Any]:
    flat_raw = payload.get("flat_ledger", [])
    manual_raw = payload.get("manual_journals", [])
    if not isinstance(flat_raw, list):
        raise ValueError("flat_ledger must be a list")
    if not isinstance(manual_raw, list):
        raise ValueError("manual_journals must be a list")
    period_start_raw = payload.get("period_start")
    period_end_raw = payload.get("period_end")
    if not isinstance(period_start_raw, str) or not isinstance(period_end_raw, str):
        raise ValueError("period_start and period_end are required ISO dates")

    journal = journalize(
        flat_ledger=tuple(FlatLedgerRow.from_json(r) for r in flat_raw),
        manual_journals=tuple(ManualJournalRow.from_json(r) for r in manual_raw),
        period_start=_date(period_start_raw),
        period_end=_date(period_end_raw),
    )
    return {"journal": journal.to_json()}


if __name__ == "__main__":
    run(main)
