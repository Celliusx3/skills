#!/usr/bin/env python3
"""Compute a Trial Balance from a Journal + Chart of Accounts.

Input:
    {
      "journal": {"rows": [...]},
      "coa": {"entries": [...]},
      "company_name": "...",
      "period_end": "YYYY-MM-DD",
      "currency": "MYR"
    }

Output:
    {"trial_balance": {...}}

Errors:
    `TrialBalanceComputationError` when the journal references account_codes
    not in the COA. Surfaces with exit 1 + JSON envelope.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

_p = Path(__file__).resolve()
while _p.parent != _p and not (_p / "_common").is_dir():
    _p = _p.parent
if str(_p) not in sys.path:
    sys.path.insert(0, str(_p))

from _common._cli import run  # noqa: E402
from _common.domain_errors import TrialBalanceComputationError  # noqa: E402
from _common.models import (  # noqa: E402
    ChartOfAccounts,
    Journal,
    TrialBalance,
    TrialBalanceLine,
    _date,
)

_ZERO = Decimal("0")


def compute(
    journal: Journal,
    coa: ChartOfAccounts,
    company_name: str,
    period_end_str: str,
    currency: str,
) -> TrialBalance:
    period_end = _date(period_end_str)
    gross_debits: dict[str, Decimal] = {}
    gross_credits: dict[str, Decimal] = {}
    for row in journal.rows:
        gross_debits[row.account_code] = (
            gross_debits.get(row.account_code, _ZERO) + row.debit
        )
        gross_credits[row.account_code] = (
            gross_credits.get(row.account_code, _ZERO) + row.credit
        )

    coa_by_code = {entry.account_code: entry for entry in coa.entries}
    unknown_codes = sorted(
        set(gross_debits.keys() | gross_credits.keys()) - coa_by_code.keys(),
    )
    if unknown_codes:
        raise TrialBalanceComputationError(
            f"Journal references account_codes not in COA: "
            f"{', '.join(unknown_codes)}. "
            f"Add them to the Chart of Accounts Sheet "
            f"(or recategorize the offending journal rows).",
        )

    active_codes = sorted(
        gross_debits.keys() | gross_credits.keys(),
        key=lambda code: (coa_by_code[code].sort_order, code),
    )

    lines: list[TrialBalanceLine] = []
    total_debit = _ZERO
    total_credit = _ZERO
    for code in active_codes:
        entry = coa_by_code[code]
        d = gross_debits.get(code, _ZERO)
        c = gross_credits.get(code, _ZERO)
        net = d - c
        if net > 0:
            lines.append(TrialBalanceLine(
                account_code=code,
                account_name=entry.account_name,
                debit=net,
                credit=_ZERO,
            ))
            total_debit += net
        elif net < 0:
            lines.append(TrialBalanceLine(
                account_code=code,
                account_name=entry.account_name,
                debit=_ZERO,
                credit=-net,
            ))
            total_credit += -net
        # net == 0 → omit (matches Jurunding TB convention)

    return TrialBalance(
        company_name=company_name,
        period_end=period_end,
        currency=currency,
        lines=tuple(lines),
        total_debit=total_debit,
        total_credit=total_credit,
    )


def main(payload: dict[str, Any]) -> dict[str, Any]:
    journal_raw = payload.get("journal")
    coa_raw = payload.get("coa")
    if not isinstance(journal_raw, dict):
        raise ValueError("journal must be an object with 'rows'")
    if not isinstance(coa_raw, dict):
        raise ValueError("coa must be an object with 'entries'")
    company = payload.get("company_name")
    period_end = payload.get("period_end")
    currency = payload.get("currency")
    if not isinstance(company, str) or not company:
        raise ValueError("company_name is required")
    if not isinstance(period_end, str) or not period_end:
        raise ValueError("period_end is required (ISO YYYY-MM-DD)")
    if not isinstance(currency, str) or len(currency) != 3:
        raise ValueError("currency must be a 3-letter code")

    tb = compute(
        journal=Journal.from_json(journal_raw),
        coa=ChartOfAccounts.from_json(coa_raw),
        company_name=company,
        period_end_str=period_end,
        currency=currency,
    )
    return {"trial_balance": tb.to_json()}


if __name__ == "__main__":
    run(main)
