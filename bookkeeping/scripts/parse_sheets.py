#!/usr/bin/env python3
"""Parse raw Sheets rows into typed bookkeeping payloads.

Supports three kinds: Chart of Accounts, flat ledger, manual journals.
The kind is selected via the `kind` field in the input.

Input:
    {
      "kind": "coa" | "flat_ledger" | "manual_journals",
      "rows": [["header1", "header2", ...], ["row1col1", ...], ...]
    }

Output (varies by kind):
    {"coa": {"entries": [...]}}
    {"flat_ledger": [...]}
    {"manual_journals": [...]}

Malformed rows in `flat_ledger` / `manual_journals` are skipped (matches
the original `SheetsParser` behaviour: partial data shouldn't block a
period close). `coa` raises `SheetsParseError` on any malformed row.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

_p = Path(__file__).resolve()
while _p.parent != _p and not (_p / "_common").is_dir():
    _p = _p.parent
if str(_p) not in sys.path:
    sys.path.insert(0, str(_p))

from _common._cli import run  # noqa: E402
from _common.domain_errors import SheetsParseError  # noqa: E402
from _common.models import (  # noqa: E402
    ChartOfAccounts,
    ChartOfAccountsEntry,
    Classification,
    Direction,
    DocumentType,
    FlatLedgerRow,
    JournalSource,
    ManualJournalRow,
    SubClassification,
)


def _normalize_rows(raw: object) -> list[list[str]]:
    if not isinstance(raw, list):
        raise SheetsParseError(f"rows must be a list of lists; got {type(raw).__name__}")
    out: list[list[str]] = []
    for r in raw:
        if not isinstance(r, list):
            raise SheetsParseError(f"each row must be a list; got {type(r).__name__}")
        out.append([str(c) if c is not None else "" for c in r])
    return out


def _get_cell(row: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return row[idx]


def _parse_iso_date(raw: str) -> date:
    s = raw.strip()
    if not s:
        msg = "empty date string"
        raise ValueError(msg)
    if "T" in s:
        s = s.split("T", 1)[0]
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass
    try:
        serial = int(float(s))
    except ValueError as exc:
        msg = f"unrecognized date format: {raw!r}"
        raise ValueError(msg) from exc
    epoch = date(1899, 12, 30)
    return epoch + timedelta(days=serial)


def parse_coa(rows: list[list[str]]) -> ChartOfAccounts:
    if not rows:
        raise SheetsParseError("COA SHEETS_READ returned no rows")
    header = [c.strip().lower() for c in rows[0]]
    required = ("account_code", "account_name", "classification", "sub_classification")
    indices: dict[str, int] = {}
    for col in required:
        if col not in header:
            raise SheetsParseError(
                f"COA SHEETS_READ missing required column {col!r}; got {rows[0]}",
            )
        indices[col] = header.index(col)
    sort_index = header.index("sort_order") if "sort_order" in header else None

    entries: list[ChartOfAccountsEntry] = []
    for row in rows[1:]:
        if not row or len(row) <= indices["account_code"]:
            continue
        try:
            account_code = row[indices["account_code"]].strip()
            account_name = row[indices["account_name"]].strip()
            classification_str = row[indices["classification"]].strip()
            sub_classification_str = row[indices["sub_classification"]].strip()
        except IndexError:
            continue
        if not account_code or not account_name:
            continue
        try:
            classification = Classification(classification_str)
            sub_classification = SubClassification(sub_classification_str)
        except ValueError as exc:
            raise SheetsParseError(
                f"COA row {account_code!r} has invalid "
                f"classification or sub_classification ({exc})",
            ) from exc
        sort_order = 0
        if sort_index is not None and len(row) > sort_index:
            raw_sort = row[sort_index].strip()
            if raw_sort:
                try:
                    sort_order = int(raw_sort)
                except ValueError:
                    sort_order = 0
        entries.append(
            ChartOfAccountsEntry(
                account_code=account_code,
                account_name=account_name,
                classification=classification,
                sub_classification=sub_classification,
                sort_order=sort_order,
            ),
        )
    if not entries:
        raise SheetsParseError("COA SHEETS_READ produced no valid entries")
    return ChartOfAccounts(entries=tuple(entries))


def parse_flat_ledger(rows: list[list[str]]) -> tuple[FlatLedgerRow, ...]:
    if not rows:
        return ()
    header = [c.strip().lower() for c in rows[0]]
    expected = (
        "posting date", "transaction date", "description", "vendor", "amount",
        "currency", "direction", "category", "reference", "source file",
        "source file id", "account code", "counter account code", "document type",
    )
    indices: dict[str, int] = {}
    for col in expected:
        if col in header:
            indices[col] = header.index(col)

    out: list[FlatLedgerRow] = []
    for row in rows[1:]:
        if not any(c.strip() for c in row):
            continue
        try:
            posting_str = _get_cell(row, indices.get("posting date"))
            posting = _parse_iso_date(posting_str)
            txn_str = (
                _get_cell(row, indices.get("transaction date")) or posting_str
            )
            txn = _parse_iso_date(txn_str)
            amount_str = _get_cell(row, indices.get("amount")).strip()
            if not amount_str:
                continue
            amount_str = amount_str.replace(",", "").replace("RM", "").strip()
            amount = Decimal(amount_str)
            if amount <= 0:
                continue
            direction = Direction(_get_cell(row, indices.get("direction")).strip().lower())
            account_code = _get_cell(row, indices.get("account code")).strip()
            counter_account_code = _get_cell(
                row, indices.get("counter account code"),
            ).strip()
            doc_type_raw = _get_cell(row, indices.get("document type")).strip().upper()
            if not account_code or not counter_account_code or not doc_type_raw:
                continue
            doc_type = DocumentType(doc_type_raw)
        except (ValueError, KeyError, ArithmeticError, InvalidOperation):
            continue

        out.append(
            FlatLedgerRow(
                posting_date=posting,
                transaction_date=txn,
                description=_get_cell(row, indices.get("description")),
                vendor=_get_cell(row, indices.get("vendor")),
                amount=amount,
                currency=_get_cell(row, indices.get("currency")).strip().upper() or "USD",
                direction=direction,
                category=_get_cell(row, indices.get("category")),
                reference=_get_cell(row, indices.get("reference")),
                source_file=_get_cell(row, indices.get("source file")),
                source_file_id=_get_cell(row, indices.get("source file id")),
                account_code=account_code,
                counter_account_code=counter_account_code,
                document_type=doc_type,
            ),
        )
    return tuple(out)


def parse_manual_journals(rows: list[list[str]]) -> tuple[ManualJournalRow, ...]:
    if not rows:
        return ()
    header = [c.strip().lower() for c in rows[0]]
    required = (
        "journal_ref", "journal_date", "account_code",
        "description", "debit", "credit", "source",
    )
    indices: dict[str, int] = {}
    for col in required:
        if col not in header:
            raise SheetsParseError(
                f"Manual Journals SHEETS_READ missing column {col!r}",
            )
        indices[col] = header.index(col)

    out: list[ManualJournalRow] = []
    for row in rows[1:]:
        if not any(c.strip() for c in row):
            continue
        try:
            journal_ref = row[indices["journal_ref"]].strip()
            journal_date = _parse_iso_date(row[indices["journal_date"]])
            account_code = row[indices["account_code"]].strip()
            desc_idx = indices["description"]
            description = row[desc_idx] if len(row) > desc_idx else ""
            debit_idx = indices["debit"]
            debit_raw = (row[debit_idx] if len(row) > debit_idx else "0").strip() or "0"
            credit_idx = indices["credit"]
            credit_raw = (row[credit_idx] if len(row) > credit_idx else "0").strip() or "0"
            source_idx = indices["source"]
            source_raw = row[source_idx].strip() if len(row) > source_idx else "MANUAL"
        except (IndexError, ValueError):
            continue
        if not journal_ref or not account_code:
            continue
        try:
            source = JournalSource(source_raw)
        except ValueError:
            source = JournalSource.MANUAL
        try:
            debit = Decimal(debit_raw)
            credit = Decimal(credit_raw)
        except (ValueError, ArithmeticError, InvalidOperation):
            continue
        out.append(
            ManualJournalRow(
                journal_ref=journal_ref,
                journal_date=journal_date,
                account_code=account_code,
                description=description,
                debit=debit,
                credit=credit,
                source=source,
            ),
        )
    return tuple(out)


def main(payload: dict[str, Any]) -> dict[str, Any]:
    kind = payload.get("kind")
    if not isinstance(kind, str):
        raise ValueError("kind is required (coa | flat_ledger | manual_journals)")
    rows = _normalize_rows(payload.get("rows", []))
    if kind == "coa":
        return {"coa": parse_coa(rows).to_json()}
    if kind == "flat_ledger":
        return {"flat_ledger": [r.to_json() for r in parse_flat_ledger(rows)]}
    if kind == "manual_journals":
        return {"manual_journals": [r.to_json() for r in parse_manual_journals(rows)]}
    raise ValueError(f"unknown kind {kind!r} (expected coa | flat_ledger | manual_journals)")


if __name__ == "__main__":
    run(main)
