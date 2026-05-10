#!/usr/bin/env python3
"""Compute monthly / period depreciation per asset.

Pure function. Stateless. Straight-line only (Phase C parity with the
former `DepreciationService`).

Input:
    {
      "register": {"assets": [{...FixedAsset...}, ...]},
      "period_start": "YYYY-MM-DD",
      "period_end": "YYYY-MM-DD"
    }

Output:
    {
      "run": {
        "period_start": "...", "period_end": "...",
        "months_in_period": int,
        "lines": [{...AssetDepreciation...}, ...],
        "total_expense": "..."
      }
    }
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
from _common.domain_errors import DepreciationServiceError  # noqa: E402
from _common.models import (  # noqa: E402
    AssetDepreciation,
    DepreciationMethod,
    DepreciationRun,
    FixedAsset,
    FixedAssetRegister,
    _date,
)

_ZERO = Decimal("0")
_TWO_PLACES = Decimal("0.01")


def compute(
    register: FixedAssetRegister,
    period_start: date,
    period_end: date,
) -> DepreciationRun:
    if period_end < period_start:
        raise DepreciationServiceError(
            f"period_end ({period_end}) precedes period_start ({period_start}).",
        )
    months_in_period = _months_between(period_start, period_end)
    lines: list[AssetDepreciation] = []
    for asset in register.assets:
        line = _depreciate_one(asset, period_start, period_end)
        if line is None:
            continue
        lines.append(line)
    total_expense = sum((line.period_depreciation for line in lines), _ZERO)
    return DepreciationRun(
        period_start=period_start,
        period_end=period_end,
        months_in_period=months_in_period,
        lines=tuple(lines),
        total_expense=total_expense,
    )


def _depreciate_one(
    asset: FixedAsset, period_start: date, period_end: date,
) -> AssetDepreciation | None:
    if asset.acquisition_date > period_end:
        return None
    months_active = _active_months(asset, period_start, period_end)
    if months_active <= 0:
        return None
    monthly = _monthly_depreciation(asset)
    period_amount = (monthly * Decimal(months_active)).quantize(_TWO_PLACES)
    return AssetDepreciation(
        asset_id=asset.asset_id,
        asset_name=asset.asset_name,
        cost=asset.cost,
        residual_value=asset.residual_value,
        useful_life_months=asset.useful_life_months,
        method=asset.method,
        months_in_period=months_active,
        monthly_depreciation=monthly,
        period_depreciation=period_amount,
        asset_account_code=asset.asset_account_code,
        accumulated_depreciation_account_code=asset.accumulated_depreciation_account_code,
        depreciation_expense_account_code=asset.depreciation_expense_account_code,
    )


def _monthly_depreciation(asset: FixedAsset) -> Decimal:
    if asset.method != DepreciationMethod.STRAIGHT_LINE:
        raise DepreciationServiceError(
            f"Unsupported depreciation method: {asset.method}",
        )
    depreciable_base = asset.cost - asset.residual_value
    if depreciable_base <= _ZERO:
        return _ZERO
    monthly = depreciable_base / Decimal(asset.useful_life_months)
    return monthly.quantize(_TWO_PLACES)


def _active_months(
    asset: FixedAsset, period_start: date, period_end: date,
) -> int:
    end_of_life = _add_months(asset.acquisition_date, asset.useful_life_months)
    effective_start = max(period_start, asset.acquisition_date)
    effective_end = min(period_end, _last_day_before(end_of_life))
    if effective_end < effective_start:
        return 0
    return _months_between(effective_start, effective_end)


def _months_between(start: date, end: date) -> int:
    if end < start:
        return 0
    months = (end.year - start.year) * 12 + (end.month - start.month) + 1
    return max(months, 0)


def _add_months(d: date, months: int) -> date:
    total_month_index = d.month - 1 + months
    new_year = d.year + total_month_index // 12
    new_month = total_month_index % 12 + 1
    new_day = min(d.day, _days_in_month(new_year, new_month))
    return date(new_year, new_month, new_day)


def _last_day_before(d: date) -> date:
    if d.day > 1:
        return date(d.year, d.month, d.day - 1)
    if d.month > 1:
        return date(d.year, d.month - 1, _days_in_month(d.year, d.month - 1))
    return date(d.year - 1, 12, 31)


def _days_in_month(year: int, month: int) -> int:
    if month == 2:
        leap = (year % 4 == 0 and year % 100 != 0) or year % 400 == 0
        return 29 if leap else 28
    return 30 if month in (4, 6, 9, 11) else 31


def main(payload: dict[str, Any]) -> dict[str, Any]:
    register_raw = payload.get("register")
    if not isinstance(register_raw, dict):
        raise ValueError("register must be an object with 'assets' list")
    period_start_raw = payload.get("period_start")
    period_end_raw = payload.get("period_end")
    if not isinstance(period_start_raw, str) or not isinstance(period_end_raw, str):
        raise ValueError("period_start and period_end are required ISO dates")

    result = compute(
        register=FixedAssetRegister.from_json(register_raw),
        period_start=_date(period_start_raw),
        period_end=_date(period_end_raw),
    )
    return {"run": result.to_json()}


if __name__ == "__main__":
    run(main)
