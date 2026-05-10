#!/usr/bin/env python3
"""Compute a Balance Sheet from a Journal + Chart of Accounts.

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
    {"balance_sheet": {...}}
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
    BalanceSheet,
    BalanceSheetLine,
    BalanceSheetSection,
    ChartOfAccounts,
    Classification,
    Journal,
    SubClassification,
    _date,
)

_ZERO = Decimal("0")

_BS_SECTIONS: tuple[tuple[SubClassification, str], ...] = (
    (SubClassification.FIXED_ASSET, "FIXED ASSETS"),
    (SubClassification.CURRENT_ASSET, "CURRENT ASSETS"),
    (SubClassification.CURRENT_LIABILITY, "CURRENT LIABILITIES"),
    (SubClassification.CAPITAL, "CAPITAL"),
    (SubClassification.RETAINED_EARNING, "RETAINED EARNING"),
)


def compute(
    journal: Journal,
    coa: ChartOfAccounts,
    company_name: str,
    period_end: date,
    prior_period_end: date,
    currency: str,
) -> BalanceSheet:
    this_year_net = _net_balances(journal, period_end)
    last_year_net = _net_balances(journal, prior_period_end)

    this_year_pnl = _period_net_pnl(journal, prior_period_end, period_end, coa)
    last_year_pnl = _period_net_pnl_full(journal, prior_period_end, coa)

    sections: list[BalanceSheetSection] = []
    for sub, title in _BS_SECTIONS:
        lines = _build_section_lines(
            sub=sub,
            coa=coa,
            this_year_net=this_year_net,
            last_year_net=last_year_net,
            this_year_pnl=this_year_pnl,
            last_year_pnl=last_year_pnl,
        )
        if not lines and sub != SubClassification.RETAINED_EARNING:
            continue
        sections.append(
            BalanceSheetSection(
                section=sub,
                title=title,
                lines=tuple(lines),
                subtotal_this_year=sum((line.this_year for line in lines), _ZERO),
                subtotal_last_year=sum((line.last_year for line in lines), _ZERO),
            ),
        )

    sub_to_section = {section.section: section for section in sections}

    def _subtotal(sub: SubClassification, year: str) -> Decimal:
        section = sub_to_section.get(sub)
        if section is None:
            return _ZERO
        value: Decimal = getattr(section, f"subtotal_{year}")
        return value

    net_ca_this = _subtotal(SubClassification.CURRENT_ASSET, "this_year") - _subtotal(
        SubClassification.CURRENT_LIABILITY, "this_year",
    )
    net_ca_last = _subtotal(SubClassification.CURRENT_ASSET, "last_year") - _subtotal(
        SubClassification.CURRENT_LIABILITY, "last_year",
    )

    total_al_this = _subtotal(SubClassification.FIXED_ASSET, "this_year") + net_ca_this
    total_al_last = _subtotal(SubClassification.FIXED_ASSET, "last_year") + net_ca_last

    financed_this = _subtotal(SubClassification.CAPITAL, "this_year") + _subtotal(
        SubClassification.RETAINED_EARNING, "this_year",
    )
    financed_last = _subtotal(SubClassification.CAPITAL, "last_year") + _subtotal(
        SubClassification.RETAINED_EARNING, "last_year",
    )

    return BalanceSheet(
        company_name=company_name,
        period_end=period_end,
        prior_period_end=prior_period_end,
        currency=currency,
        sections=tuple(sections),
        net_current_assets_this_year=net_ca_this,
        net_current_assets_last_year=net_ca_last,
        total_assets_less_liab_this_year=total_al_this,
        total_assets_less_liab_last_year=total_al_last,
        financed_by_this_year=financed_this,
        financed_by_last_year=financed_last,
    )


def _net_balances(journal: Journal, cutoff: date) -> dict[str, Decimal]:
    net: dict[str, Decimal] = {}
    for row in journal.rows:
        if row.journal_date > cutoff:
            continue
        net[row.account_code] = net.get(row.account_code, _ZERO) + row.debit - row.credit
    return net


def _period_net_pnl(
    journal: Journal,
    period_start_exclusive: date,
    period_end: date,
    coa: ChartOfAccounts,
) -> Decimal:
    pl_classifications = {Classification.INCOME, Classification.EXPENSE, Classification.COGS}
    pl_codes_to_class = {
        entry.account_code: entry.classification
        for entry in coa.entries
        if entry.classification in pl_classifications
    }
    income_net = _ZERO
    expense_net = _ZERO
    for row in journal.rows:
        if row.journal_date <= period_start_exclusive or row.journal_date > period_end:
            continue
        cls = pl_codes_to_class.get(row.account_code)
        if cls is None:
            continue
        if cls == Classification.INCOME:
            income_net += row.credit - row.debit
        else:
            expense_net += row.debit - row.credit
    return income_net - expense_net


def _period_net_pnl_full(
    journal: Journal,
    cutoff: date,
    coa: ChartOfAccounts,
) -> Decimal:
    pl_classifications = {Classification.INCOME, Classification.EXPENSE, Classification.COGS}
    pl_codes_to_class = {
        entry.account_code: entry.classification
        for entry in coa.entries
        if entry.classification in pl_classifications
    }
    income_net = _ZERO
    expense_net = _ZERO
    for row in journal.rows:
        if row.journal_date > cutoff:
            continue
        cls = pl_codes_to_class.get(row.account_code)
        if cls is None:
            continue
        if cls == Classification.INCOME:
            income_net += row.credit - row.debit
        else:
            expense_net += row.debit - row.credit
    return income_net - expense_net


def _build_section_lines(
    *,
    sub: SubClassification,
    coa: ChartOfAccounts,
    this_year_net: dict[str, Decimal],
    last_year_net: dict[str, Decimal],
    this_year_pnl: Decimal,
    last_year_pnl: Decimal,
) -> list[BalanceSheetLine]:
    lines: list[BalanceSheetLine] = []
    section_entries = [e for e in coa.entries if e.sub_classification == sub]
    section_entries.sort(key=lambda e: (e.sort_order, e.account_code))

    for entry in section_entries:
        ty_net = this_year_net.get(entry.account_code, _ZERO)
        ly_net = last_year_net.get(entry.account_code, _ZERO)
        ty_display, ly_display = _display_amounts(entry.classification, ty_net, ly_net)
        if ty_display == _ZERO and ly_display == _ZERO:
            continue
        lines.append(
            BalanceSheetLine(
                section=sub,
                account_code=entry.account_code,
                account_name=entry.account_name,
                this_year=ty_display,
                last_year=ly_display,
            ),
        )

    if sub == SubClassification.RETAINED_EARNING and (
        this_year_pnl != _ZERO or last_year_pnl != _ZERO
    ):
        lines.append(
            BalanceSheetLine(
                section=sub,
                account_code="",
                account_name="PROFIT/(LOSS)",
                this_year=this_year_pnl,
                last_year=last_year_pnl,
            ),
        )

    return lines


def _display_amounts(
    classification: Classification,
    this_year_net: Decimal,
    last_year_net: Decimal,
) -> tuple[Decimal, Decimal]:
    if classification == Classification.ASSET:
        return this_year_net, last_year_net
    return -this_year_net, -last_year_net


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

    bs = compute(
        journal=Journal.from_json(journal_raw),
        coa=ChartOfAccounts.from_json(coa_raw),
        company_name=company,
        period_end=_date(period_end),
        prior_period_end=_date(prior),
        currency=currency,
    )
    return {"balance_sheet": bs.to_json()}


if __name__ == "__main__":
    run(main)
