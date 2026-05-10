#!/usr/bin/env python3
"""Compute a Profit and Loss Statement from a Journal + COA.

Input:
    {
      "journal": {"rows": [...]},
      "coa": {"entries": [...]},
      "company_name": "...",
      "period_end": "YYYY-MM-DD",
      "prior_period_end": "YYYY-MM-DD",
      "currency": "MYR"
    }

Output:
    {"profit_and_loss": {...}}
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
    Classification,
    Journal,
    ProfitAndLoss,
    ProfitAndLossLine,
    ProfitAndLossSection,
    SubClassification,
    _date,
)

_ZERO = Decimal("0")

_PL_SECTIONS: tuple[tuple[SubClassification, str], ...] = (
    (SubClassification.SALES, "SALES"),
    (SubClassification.COGS, "COST OF GOODS SOLD"),
    (SubClassification.OTHER_INCOMES, "OTHER INCOMES"),
    (SubClassification.EXPENSES, "EXPENSES"),
    (SubClassification.TAXATION, "TAXATION"),
)

_INCOME_CLASSIFICATIONS = {Classification.INCOME}
_EXPENSE_CLASSIFICATIONS = {Classification.EXPENSE, Classification.COGS}


def compute(
    journal: Journal,
    coa: ChartOfAccounts,
    company_name: str,
    period_end: date,
    prior_period_end: date,
    currency: str,
) -> ProfitAndLoss:
    prior_year_start = date(
        prior_period_end.year - 1,
        prior_period_end.month,
        prior_period_end.day,
    )
    this_year_net = _net_per_account(journal, prior_period_end, period_end, coa)
    last_year_net = _net_per_account(journal, prior_year_start, prior_period_end, coa)

    sections: list[ProfitAndLossSection] = []
    for sub, title in _PL_SECTIONS:
        lines = _build_section_lines(sub, coa, this_year_net, last_year_net)
        if not lines:
            continue
        sections.append(
            ProfitAndLossSection(
                section=sub,
                title=title,
                lines=tuple(lines),
                subtotal_this_year=sum((line.this_year for line in lines), _ZERO),
                subtotal_last_year=sum((line.last_year for line in lines), _ZERO),
            ),
        )

    sub_to_section = {s.section: s for s in sections}

    def _sub(s: SubClassification, year: str) -> Decimal:
        section = sub_to_section.get(s)
        return getattr(section, f"subtotal_{year}") if section is not None else _ZERO

    gp_ty = _sub(SubClassification.SALES, "this_year") - _sub(SubClassification.COGS, "this_year")
    gp_ly = _sub(SubClassification.SALES, "last_year") - _sub(SubClassification.COGS, "last_year")

    npbt_ty = (
        gp_ty
        + _sub(SubClassification.OTHER_INCOMES, "this_year")
        - _sub(SubClassification.EXPENSES, "this_year")
    )
    npbt_ly = (
        gp_ly
        + _sub(SubClassification.OTHER_INCOMES, "last_year")
        - _sub(SubClassification.EXPENSES, "last_year")
    )

    npat_ty = npbt_ty - _sub(SubClassification.TAXATION, "this_year")
    npat_ly = npbt_ly - _sub(SubClassification.TAXATION, "last_year")

    return ProfitAndLoss(
        company_name=company_name,
        period_end=period_end,
        prior_period_end=prior_period_end,
        currency=currency,
        sections=tuple(sections),
        gross_profit_this_year=gp_ty,
        gross_profit_last_year=gp_ly,
        net_profit_before_tax_this_year=npbt_ty,
        net_profit_before_tax_last_year=npbt_ly,
        net_profit_after_tax_this_year=npat_ty,
        net_profit_after_tax_last_year=npat_ly,
    )


def _net_per_account(
    journal: Journal,
    period_start_exclusive: date,
    period_end_inclusive: date,
    coa: ChartOfAccounts,
) -> dict[str, Decimal]:
    coa_by_code = {entry.account_code: entry for entry in coa.entries}
    net: dict[str, Decimal] = {}
    for row in journal.rows:
        if row.journal_date <= period_start_exclusive or row.journal_date > period_end_inclusive:
            continue
        entry = coa_by_code.get(row.account_code)
        if entry is None:
            continue
        if entry.classification in _INCOME_CLASSIFICATIONS:
            delta = row.credit - row.debit
        elif entry.classification in _EXPENSE_CLASSIFICATIONS:
            delta = row.debit - row.credit
        else:
            continue
        net[row.account_code] = net.get(row.account_code, _ZERO) + delta
    return net


def _build_section_lines(
    sub: SubClassification,
    coa: ChartOfAccounts,
    this_year_net: dict[str, Decimal],
    last_year_net: dict[str, Decimal],
) -> list[ProfitAndLossLine]:
    section_entries = [e for e in coa.entries if e.sub_classification == sub]
    section_entries.sort(key=lambda e: (e.sort_order, e.account_code))
    lines: list[ProfitAndLossLine] = []
    for entry in section_entries:
        ty = this_year_net.get(entry.account_code, _ZERO)
        ly = last_year_net.get(entry.account_code, _ZERO)
        if ty == _ZERO and ly == _ZERO:
            continue
        lines.append(
            ProfitAndLossLine(
                section=sub,
                account_code=entry.account_code,
                account_name=entry.account_name,
                this_year=ty,
                last_year=ly,
            ),
        )
    return lines


def main(payload: dict[str, Any]) -> dict[str, Any]:
    journal_raw = payload.get("journal")
    coa_raw = payload.get("coa")
    if not isinstance(journal_raw, dict):
        raise ValueError("journal must be an object with 'rows'")
    if not isinstance(coa_raw, dict):
        raise ValueError("coa must be an object with 'entries'")
    company = payload.get("company_name")
    period_end = payload.get("period_end")
    prior = payload.get("prior_period_end")
    currency = payload.get("currency")
    if not isinstance(company, str) or not company:
        raise ValueError("company_name is required")
    if not isinstance(period_end, str) or not period_end:
        raise ValueError("period_end is required")
    if not isinstance(prior, str) or not prior:
        raise ValueError("prior_period_end is required")
    if not isinstance(currency, str) or len(currency) != 3:
        raise ValueError("currency must be a 3-letter code")

    pl = compute(
        journal=Journal.from_json(journal_raw),
        coa=ChartOfAccounts.from_json(coa_raw),
        company_name=company,
        period_end=_date(period_end),
        prior_period_end=_date(prior),
        currency=currency,
    )
    return {"profit_and_loss": pl.to_json()}


if __name__ == "__main__":
    run(main)
