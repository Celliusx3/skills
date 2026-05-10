#!/usr/bin/env python3
"""Compute a General Ledger from a Journal + Chart of Accounts.

Input:
    {
      "journal": {"rows": [...]},
      "coa": {"entries": [...]},
      "company_name": "...",
      "company_registration": "..." (optional),
      "period_start": "YYYY-MM-DD",
      "period_end": "YYYY-MM-DD",
      "currency": "MYR"
    }

Output:
    {"general_ledger": {...}}

Per Jurunding's GL: every COA account appears, even if it had zero
period activity. Inactive accounts show only the BALANCE B/F line.
"""

from __future__ import annotations

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
from _common.models import (  # noqa: E402
    ChartOfAccounts,
    GeneralLedger,
    GeneralLedgerAccount,
    GeneralLedgerEntry,
    Journal,
    JournalRow,
    VoucherType,
    _date,
)

_ZERO = Decimal("0")


def compute(
    journal: Journal,
    coa: ChartOfAccounts,
    company_name: str,
    period_start: date,
    period_end: date,
    currency: str,
    company_registration: str = "",
) -> GeneralLedger:
    bf_balances = _cumulative_before(journal, period_start)

    period_rows_by_account: dict[str, list[JournalRow]] = {}
    for row in journal.rows:
        if row.journal_date < period_start or row.journal_date > period_end:
            continue
        period_rows_by_account.setdefault(row.account_code, []).append(row)

    for rows in period_rows_by_account.values():
        rows.sort(key=lambda r: (r.journal_date, r.journal_ref))

    coa_sorted = sorted(coa.entries, key=lambda e: (e.sort_order, e.account_code))

    accounts: list[GeneralLedgerAccount] = []
    for entry in coa_sorted:
        bf = bf_balances.get(entry.account_code, _ZERO)
        period_rows = period_rows_by_account.get(entry.account_code, [])
        entries: list[GeneralLedgerEntry] = [
            GeneralLedgerEntry(
                journal_date=None,
                journal_kind="",
                journal_ref="BALANCE B/F",
                description="",
                department="",
                debit=_ZERO,
                credit=_ZERO,
                running_balance=bf,
            ),
        ]
        running = bf
        period_total_debit = _ZERO
        period_total_credit = _ZERO
        for row in period_rows:
            running += row.debit - row.credit
            period_total_debit += row.debit
            period_total_credit += row.credit
            entries.append(
                GeneralLedgerEntry(
                    journal_date=row.journal_date,
                    journal_kind=_journal_kind(row.voucher_type),
                    journal_ref=row.journal_ref,
                    description=row.description,
                    department="",
                    debit=row.debit,
                    credit=row.credit,
                    running_balance=running,
                ),
            )
        accounts.append(
            GeneralLedgerAccount(
                account_code=entry.account_code,
                account_name=entry.account_name,
                entries=tuple(entries),
                period_total_debit=period_total_debit,
                period_total_credit=period_total_credit,
                closing_balance=running,
            ),
        )

    return GeneralLedger(
        company_name=company_name,
        company_registration=company_registration,
        period_start=period_start,
        period_end=period_end,
        currency=currency,
        accounts=tuple(accounts),
    )


def _cumulative_before(journal: Journal, cutoff: date) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for row in journal.rows:
        if row.journal_date >= cutoff:
            continue
        out[row.account_code] = out.get(row.account_code, _ZERO) + row.debit - row.credit
    return out


def _journal_kind(voucher_type: VoucherType) -> str:
    if voucher_type in {VoucherType.PV, VoucherType.OR}:
        return "BANK"
    return "GENERAL"


def main(payload: dict[str, Any]) -> dict[str, Any]:
    journal_raw = payload.get("journal")
    coa_raw = payload.get("coa")
    if not isinstance(journal_raw, dict):
        raise ValueError("journal must be an object with 'rows'")
    if not isinstance(coa_raw, dict):
        raise ValueError("coa must be an object with 'entries'")
    company = payload.get("company_name")
    period_start = payload.get("period_start")
    period_end = payload.get("period_end")
    currency = payload.get("currency")
    company_reg = payload.get("company_registration", "")
    if not isinstance(company, str) or not company:
        raise ValueError("company_name is required")
    if not isinstance(period_start, str) or not period_start:
        raise ValueError("period_start is required")
    if not isinstance(period_end, str) or not period_end:
        raise ValueError("period_end is required")
    if not isinstance(currency, str) or len(currency) != 3:
        raise ValueError("currency must be a 3-letter code")
    if not isinstance(company_reg, str):
        raise ValueError("company_registration must be a string when provided")

    gl = compute(
        journal=Journal.from_json(journal_raw),
        coa=ChartOfAccounts.from_json(coa_raw),
        company_name=company,
        period_start=_date(period_start),
        period_end=_date(period_end),
        currency=currency,
        company_registration=company_reg,
    )
    return {"general_ledger": gl.to_json()}


if __name__ == "__main__":
    run(main)
