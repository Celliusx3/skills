"""Domain shapes used by every bookkeeping skill script.

Stdlib-only (frozen dataclasses + StrEnum). Each class includes
`from_json` / `to_json` static helpers so scripts can deserialize argv
input and serialize stdout output without third-party dependencies.

`Decimal` and `date` are encoded as strings on the wire — stdlib `json`
can't natively encode either, and stringifying preserves precision and
calendar fidelity through round-trips.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

_ZERO = Decimal("0")


# ---------------------------------------------------------------------------
# Enums (verbatim values from the deleted quant.model.* enums so canvas
# wire-compat is preserved end-to-end).
# ---------------------------------------------------------------------------


class Direction(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class VoucherType(StrEnum):
    PV = "PV"
    OR = "OR"
    JV = "JV"
    CN = "CN"
    DN = "DN"


class DocumentType(StrEnum):
    RECEIPT = "RECEIPT"
    BILL = "BILL"
    EXPENSE_CLAIM = "EXPENSE_CLAIM"
    BANK_TXN = "BANK_TXN"


class JournalSource(StrEnum):
    OPENING_BALANCE = "OPENING_BALANCE"
    MANUAL = "MANUAL"
    RECURRING = "RECURRING"
    LLM_DRAFT_DEPRECIATION = "LLM_DRAFT_DEPRECIATION"
    LLM_DRAFT_ACCRUAL = "LLM_DRAFT_ACCRUAL"
    LLM_DRAFT_TAX = "LLM_DRAFT_TAX"
    BANK_VOUCHER = "BANK_VOUCHER"


class Classification(StrEnum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"
    COGS = "COGS"


class SubClassification(StrEnum):
    FIXED_ASSET = "FIXED_ASSET"
    CURRENT_ASSET = "CURRENT_ASSET"
    CURRENT_LIABILITY = "CURRENT_LIABILITY"
    CAPITAL = "CAPITAL"
    RETAINED_EARNING = "RETAINED_EARNING"
    SALES = "SALES"
    COGS = "COGS"
    OTHER_INCOMES = "OTHER_INCOMES"
    EXPENSES = "EXPENSES"
    TAXATION = "TAXATION"


class DepreciationMethod(StrEnum):
    STRAIGHT_LINE = "straight_line"


class DraftStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PROMOTED = "PROMOTED"


class DraftConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DepreciationKind(StrEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    CUSTOM = "custom"


# ---------------------------------------------------------------------------
# JSON codec helpers
# ---------------------------------------------------------------------------


def _decimal(raw: object, *, ge: Decimal | None = None, gt: Decimal | None = None) -> Decimal:
    """Decode a Decimal from JSON (string or numeric).

    Stringifying numeric inputs first preserves the literal digits the
    caller sent — `Decimal(0.1)` would otherwise produce a 51-digit
    binary-float artefact.
    """
    if isinstance(raw, Decimal):
        value = raw
    elif isinstance(raw, str):
        value = Decimal(raw.strip()) if raw.strip() else _ZERO
    elif isinstance(raw, (int, float)):
        value = Decimal(str(raw))
    elif raw is None:
        value = _ZERO
    else:
        msg = f"expected Decimal/str/int/float, got {type(raw).__name__}"
        raise ValueError(msg)
    if ge is not None and value < ge:
        msg = f"value {value} must be >= {ge}"
        raise ValueError(msg)
    if gt is not None and value <= gt:
        msg = f"value {value} must be > {gt}"
        raise ValueError(msg)
    return value


def _date(raw: object) -> date:
    if isinstance(raw, date):
        return raw
    if not isinstance(raw, str):
        msg = f"expected ISO date string, got {type(raw).__name__}"
        raise ValueError(msg)
    s = raw.strip()
    if "T" in s:
        s = s.split("T", 1)[0]
    return date.fromisoformat(s)


def _str(raw: object, *, min_length: int = 0, default: str = "") -> str:
    if raw is None:
        value = default
    elif isinstance(raw, str):
        value = raw
    else:
        value = str(raw)
    if len(value) < min_length:
        msg = f"string must be at least {min_length} chars; got {value!r}"
        raise ValueError(msg)
    return value


def _opt_date(raw: object) -> date | None:
    if raw is None or raw == "":
        return None
    return _date(raw)


def _enc_dec(value: Decimal) -> str:
    return str(value)


def _enc_date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


# ---------------------------------------------------------------------------
# Chart of accounts (skill-private — backend's quant.model.chart_of_accounts
# stays put, this is just a sandbox-side mirror).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChartOfAccountsEntry:
    account_code: str
    account_name: str
    classification: Classification
    sub_classification: SubClassification
    sort_order: int = 0

    def __post_init__(self) -> None:
        if not self.account_code:
            raise ValueError("account_code must be non-empty")
        if not self.account_name:
            raise ValueError("account_name must be non-empty")
        if self.sort_order < 0:
            raise ValueError(f"sort_order must be >= 0, got {self.sort_order}")

    @staticmethod
    def from_json(raw: Mapping[str, Any]) -> ChartOfAccountsEntry:
        return ChartOfAccountsEntry(
            account_code=_str(raw.get("account_code"), min_length=1),
            account_name=_str(raw.get("account_name"), min_length=1),
            classification=Classification(_str(raw.get("classification"), min_length=1)),
            sub_classification=SubClassification(_str(raw.get("sub_classification"), min_length=1)),
            sort_order=int(raw.get("sort_order") or 0),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "account_code": self.account_code,
            "account_name": self.account_name,
            "classification": self.classification.value,
            "sub_classification": self.sub_classification.value,
            "sort_order": self.sort_order,
        }


@dataclass(frozen=True, slots=True)
class ChartOfAccounts:
    entries: tuple[ChartOfAccountsEntry, ...]

    def lookup(self, account_code: str) -> ChartOfAccountsEntry | None:
        for entry in self.entries:
            if entry.account_code == account_code:
                return entry
        return None

    @staticmethod
    def from_json(raw: Mapping[str, Any]) -> ChartOfAccounts:
        items = raw.get("entries") if isinstance(raw, Mapping) else None
        if items is None:
            items = raw  # allow top-level list
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            raise ValueError("ChartOfAccounts payload must include 'entries' list")
        return ChartOfAccounts(
            entries=tuple(ChartOfAccountsEntry.from_json(e) for e in items),
        )

    def to_json(self) -> dict[str, Any]:
        return {"entries": [e.to_json() for e in self.entries]}


# ---------------------------------------------------------------------------
# Journal models (replaces quant.model.journal)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FlatLedgerRow:
    posting_date: date
    transaction_date: date
    description: str
    vendor: str
    amount: Decimal
    currency: str
    direction: Direction
    category: str
    reference: str
    source_file: str
    source_file_id: str
    account_code: str
    counter_account_code: str
    document_type: DocumentType

    def __post_init__(self) -> None:
        if self.amount <= _ZERO:
            raise ValueError(f"FlatLedgerRow.amount must be > 0; got {self.amount}")
        if len(self.currency) != 3:
            raise ValueError(f"currency must be 3 chars; got {self.currency!r}")

    @staticmethod
    def from_json(raw: Mapping[str, Any]) -> FlatLedgerRow:
        return FlatLedgerRow(
            posting_date=_date(raw.get("posting_date")),
            transaction_date=_date(raw.get("transaction_date")),
            description=_str(raw.get("description")),
            vendor=_str(raw.get("vendor")),
            amount=_decimal(raw.get("amount"), gt=_ZERO),
            currency=_str(raw.get("currency"), min_length=3),
            direction=Direction(_str(raw.get("direction"), min_length=1)),
            category=_str(raw.get("category")),
            reference=_str(raw.get("reference")),
            source_file=_str(raw.get("source_file")),
            source_file_id=_str(raw.get("source_file_id")),
            account_code=_str(raw.get("account_code"), min_length=1),
            counter_account_code=_str(raw.get("counter_account_code"), min_length=1),
            document_type=DocumentType(_str(raw.get("document_type"), min_length=1)),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "posting_date": _enc_date(self.posting_date),
            "transaction_date": _enc_date(self.transaction_date),
            "description": self.description,
            "vendor": self.vendor,
            "amount": _enc_dec(self.amount),
            "currency": self.currency,
            "direction": self.direction.value,
            "category": self.category,
            "reference": self.reference,
            "source_file": self.source_file,
            "source_file_id": self.source_file_id,
            "account_code": self.account_code,
            "counter_account_code": self.counter_account_code,
            "document_type": self.document_type.value,
        }


@dataclass(frozen=True, slots=True)
class ManualJournalRow:
    journal_ref: str
    journal_date: date
    account_code: str
    description: str
    debit: Decimal
    credit: Decimal
    source: JournalSource

    def __post_init__(self) -> None:
        if not self.journal_ref:
            raise ValueError("journal_ref must be non-empty")
        if not self.account_code:
            raise ValueError("account_code must be non-empty")
        if self.debit < _ZERO:
            raise ValueError(f"debit must be >= 0; got {self.debit}")
        if self.credit < _ZERO:
            raise ValueError(f"credit must be >= 0; got {self.credit}")

    @staticmethod
    def from_json(raw: Mapping[str, Any]) -> ManualJournalRow:
        return ManualJournalRow(
            journal_ref=_str(raw.get("journal_ref"), min_length=1),
            journal_date=_date(raw.get("journal_date")),
            account_code=_str(raw.get("account_code"), min_length=1),
            description=_str(raw.get("description")),
            debit=_decimal(raw.get("debit", "0"), ge=_ZERO),
            credit=_decimal(raw.get("credit", "0"), ge=_ZERO),
            source=JournalSource(_str(raw.get("source"), min_length=1)),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "journal_ref": self.journal_ref,
            "journal_date": _enc_date(self.journal_date),
            "account_code": self.account_code,
            "description": self.description,
            "debit": _enc_dec(self.debit),
            "credit": _enc_dec(self.credit),
            "source": self.source.value,
        }


@dataclass(frozen=True, slots=True)
class JournalRow:
    journal_ref: str
    journal_date: date
    voucher_type: VoucherType
    account_code: str
    description: str
    debit: Decimal
    credit: Decimal
    source: JournalSource
    source_file_id: str = ""

    def __post_init__(self) -> None:
        if not self.journal_ref:
            raise ValueError("journal_ref must be non-empty")
        if not self.account_code:
            raise ValueError("account_code must be non-empty")
        if self.debit < _ZERO:
            raise ValueError(f"debit must be >= 0; got {self.debit}")
        if self.credit < _ZERO:
            raise ValueError(f"credit must be >= 0; got {self.credit}")

    @staticmethod
    def from_json(raw: Mapping[str, Any]) -> JournalRow:
        return JournalRow(
            journal_ref=_str(raw.get("journal_ref"), min_length=1),
            journal_date=_date(raw.get("journal_date")),
            voucher_type=VoucherType(_str(raw.get("voucher_type"), min_length=1)),
            account_code=_str(raw.get("account_code"), min_length=1),
            description=_str(raw.get("description")),
            debit=_decimal(raw.get("debit", "0"), ge=_ZERO),
            credit=_decimal(raw.get("credit", "0"), ge=_ZERO),
            source=JournalSource(_str(raw.get("source"), min_length=1)),
            source_file_id=_str(raw.get("source_file_id")),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "journal_ref": self.journal_ref,
            "journal_date": _enc_date(self.journal_date),
            "voucher_type": self.voucher_type.value,
            "account_code": self.account_code,
            "description": self.description,
            "debit": _enc_dec(self.debit),
            "credit": _enc_dec(self.credit),
            "source": self.source.value,
            "source_file_id": self.source_file_id,
        }


@dataclass(frozen=True, slots=True)
class Journal:
    rows: tuple[JournalRow, ...]

    @staticmethod
    def from_json(raw: Mapping[str, Any]) -> Journal:
        items = raw.get("rows", []) if isinstance(raw, Mapping) else raw
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            raise ValueError("Journal payload must include 'rows' list")
        return Journal(rows=tuple(JournalRow.from_json(r) for r in items))

    def to_json(self) -> dict[str, Any]:
        return {"rows": [r.to_json() for r in self.rows]}


# ---------------------------------------------------------------------------
# Manual Journal Drafts (replaces quant.model.manual_journal_drafts)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ManualJournalDraftRow:
    journal_ref: str
    journal_date: date
    account_code: str
    description: str = ""
    debit: Decimal = _ZERO
    credit: Decimal = _ZERO
    source: str = "LLM_DRAFT"
    status: DraftStatus = DraftStatus.DRAFT
    confidence: DraftConfidence = DraftConfidence.MEDIUM
    rationale: str = ""
    source_doc_file_id: str = ""

    def __post_init__(self) -> None:
        if not self.journal_ref:
            raise ValueError("journal_ref must be non-empty")
        if not self.account_code:
            raise ValueError("account_code must be non-empty")
        if not self.source:
            raise ValueError("source must be non-empty")
        if self.debit < _ZERO:
            raise ValueError(f"debit must be >= 0; got {self.debit}")
        if self.credit < _ZERO:
            raise ValueError(f"credit must be >= 0; got {self.credit}")


# ---------------------------------------------------------------------------
# Fixed-asset register (skill-private mirror of quant.model.fixed_asset)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FixedAsset:
    asset_id: str
    asset_name: str
    cost: Decimal
    useful_life_months: int
    acquisition_date: date
    asset_account_code: str
    accumulated_depreciation_account_code: str
    depreciation_expense_account_code: str
    residual_value: Decimal = _ZERO
    method: DepreciationMethod = DepreciationMethod.STRAIGHT_LINE

    def __post_init__(self) -> None:
        if not self.asset_id:
            raise ValueError("asset_id must be non-empty")
        if not self.asset_name:
            raise ValueError("asset_name must be non-empty")
        if self.cost <= _ZERO:
            raise ValueError(f"cost must be > 0; got {self.cost}")
        if self.residual_value < _ZERO:
            raise ValueError(f"residual_value must be >= 0; got {self.residual_value}")
        if self.useful_life_months <= 0:
            raise ValueError(f"useful_life_months must be > 0; got {self.useful_life_months}")
        for label, code in (
            ("asset_account_code", self.asset_account_code),
            ("accumulated_depreciation_account_code", self.accumulated_depreciation_account_code),
            ("depreciation_expense_account_code", self.depreciation_expense_account_code),
        ):
            if not code:
                raise ValueError(f"{label} must be non-empty")

    @staticmethod
    def from_json(raw: Mapping[str, Any]) -> FixedAsset:
        return FixedAsset(
            asset_id=_str(raw.get("asset_id"), min_length=1),
            asset_name=_str(raw.get("asset_name"), min_length=1),
            cost=_decimal(raw.get("cost"), gt=_ZERO),
            residual_value=_decimal(raw.get("residual_value", "0"), ge=_ZERO),
            useful_life_months=int(raw.get("useful_life_months", 0)),
            method=DepreciationMethod(
                _str(raw.get("method", DepreciationMethod.STRAIGHT_LINE.value), min_length=1),
            ),
            acquisition_date=_date(raw.get("acquisition_date")),
            asset_account_code=_str(raw.get("asset_account_code"), min_length=1),
            accumulated_depreciation_account_code=_str(
                raw.get("accumulated_depreciation_account_code"), min_length=1,
            ),
            depreciation_expense_account_code=_str(
                raw.get("depreciation_expense_account_code"), min_length=1,
            ),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "asset_name": self.asset_name,
            "cost": _enc_dec(self.cost),
            "residual_value": _enc_dec(self.residual_value),
            "useful_life_months": self.useful_life_months,
            "method": self.method.value,
            "acquisition_date": _enc_date(self.acquisition_date),
            "asset_account_code": self.asset_account_code,
            "accumulated_depreciation_account_code": self.accumulated_depreciation_account_code,
            "depreciation_expense_account_code": self.depreciation_expense_account_code,
        }


@dataclass(frozen=True, slots=True)
class FixedAssetRegister:
    assets: tuple[FixedAsset, ...]

    @staticmethod
    def from_json(raw: Mapping[str, Any]) -> FixedAssetRegister:
        items = raw.get("assets", []) if isinstance(raw, Mapping) else raw
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            raise ValueError("FixedAssetRegister payload must include 'assets' list")
        return FixedAssetRegister(assets=tuple(FixedAsset.from_json(a) for a in items))

    def to_json(self) -> dict[str, Any]:
        return {"assets": [a.to_json() for a in self.assets]}


# ---------------------------------------------------------------------------
# Depreciation result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AssetDepreciation:
    asset_id: str
    asset_name: str
    cost: Decimal
    residual_value: Decimal
    useful_life_months: int
    method: DepreciationMethod
    months_in_period: int
    monthly_depreciation: Decimal
    period_depreciation: Decimal
    asset_account_code: str
    accumulated_depreciation_account_code: str
    depreciation_expense_account_code: str

    def to_json(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "asset_name": self.asset_name,
            "cost": _enc_dec(self.cost),
            "residual_value": _enc_dec(self.residual_value),
            "useful_life_months": self.useful_life_months,
            "method": self.method.value,
            "months_in_period": self.months_in_period,
            "monthly_depreciation": _enc_dec(self.monthly_depreciation),
            "period_depreciation": _enc_dec(self.period_depreciation),
            "asset_account_code": self.asset_account_code,
            "accumulated_depreciation_account_code": self.accumulated_depreciation_account_code,
            "depreciation_expense_account_code": self.depreciation_expense_account_code,
        }


@dataclass(frozen=True, slots=True)
class DepreciationRun:
    period_start: date
    period_end: date
    months_in_period: int
    lines: tuple[AssetDepreciation, ...]
    total_expense: Decimal

    def __post_init__(self) -> None:
        expected = sum((line.period_depreciation for line in self.lines), _ZERO)
        if expected != self.total_expense:
            raise ValueError(
                f"DepreciationRun.total_expense ({self.total_expense}) "
                f"!= sum of lines ({expected}). Indicates a bug in the compute path.",
            )

    def to_json(self) -> dict[str, Any]:
        return {
            "period_start": _enc_date(self.period_start),
            "period_end": _enc_date(self.period_end),
            "months_in_period": self.months_in_period,
            "lines": [line.to_json() for line in self.lines],
            "total_expense": _enc_dec(self.total_expense),
        }


# ---------------------------------------------------------------------------
# Trial Balance
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TrialBalanceLine:
    account_code: str
    account_name: str
    debit: Decimal = _ZERO
    credit: Decimal = _ZERO

    def __post_init__(self) -> None:
        if not self.account_code:
            raise ValueError("account_code must be non-empty")
        if not self.account_name:
            raise ValueError("account_name must be non-empty")

    def to_json(self) -> dict[str, Any]:
        return {
            "account_code": self.account_code,
            "account_name": self.account_name,
            "debit": _enc_dec(self.debit),
            "credit": _enc_dec(self.credit),
        }


@dataclass(frozen=True, slots=True)
class TrialBalance:
    company_name: str
    period_end: date
    currency: str
    lines: tuple[TrialBalanceLine, ...]
    total_debit: Decimal
    total_credit: Decimal

    def __post_init__(self) -> None:
        if not self.company_name:
            raise ValueError("company_name must be non-empty")
        if len(self.currency) != 3:
            raise ValueError(f"currency must be 3 chars; got {self.currency!r}")
        if self.total_debit != self.total_credit:
            raise ValueError(
                f"Trial Balance does not balance: total_debit={self.total_debit} "
                f"!= total_credit={self.total_credit}. Difference of "
                f"{self.total_debit - self.total_credit} indicates a bug "
                f"in journalize or unbalanced manual journals.",
            )

    def to_json(self) -> dict[str, Any]:
        return {
            "company_name": self.company_name,
            "period_end": _enc_date(self.period_end),
            "currency": self.currency,
            "lines": [line.to_json() for line in self.lines],
            "total_debit": _enc_dec(self.total_debit),
            "total_credit": _enc_dec(self.total_credit),
        }


# ---------------------------------------------------------------------------
# Balance Sheet
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BalanceSheetLine:
    section: SubClassification
    account_code: str  # may be empty for synthetic PROFIT/(LOSS) line
    account_name: str
    this_year: Decimal = _ZERO
    last_year: Decimal = _ZERO

    def __post_init__(self) -> None:
        if not self.account_name:
            raise ValueError("account_name must be non-empty")

    def to_json(self) -> dict[str, Any]:
        return {
            "section": self.section.value,
            "account_code": self.account_code,
            "account_name": self.account_name,
            "this_year": _enc_dec(self.this_year),
            "last_year": _enc_dec(self.last_year),
        }


@dataclass(frozen=True, slots=True)
class BalanceSheetSection:
    section: SubClassification
    title: str
    lines: tuple[BalanceSheetLine, ...]
    subtotal_this_year: Decimal
    subtotal_last_year: Decimal

    def __post_init__(self) -> None:
        if not self.title:
            raise ValueError("title must be non-empty")

    def to_json(self) -> dict[str, Any]:
        return {
            "section": self.section.value,
            "title": self.title,
            "lines": [line.to_json() for line in self.lines],
            "subtotal_this_year": _enc_dec(self.subtotal_this_year),
            "subtotal_last_year": _enc_dec(self.subtotal_last_year),
        }


@dataclass(frozen=True, slots=True)
class BalanceSheet:
    company_name: str
    period_end: date
    prior_period_end: date
    currency: str
    sections: tuple[BalanceSheetSection, ...]
    net_current_assets_this_year: Decimal
    net_current_assets_last_year: Decimal
    total_assets_less_liab_this_year: Decimal
    total_assets_less_liab_last_year: Decimal
    financed_by_this_year: Decimal
    financed_by_last_year: Decimal

    def __post_init__(self) -> None:
        if not self.company_name:
            raise ValueError("company_name must be non-empty")
        if len(self.currency) != 3:
            raise ValueError(f"currency must be 3 chars; got {self.currency!r}")

    def to_json(self) -> dict[str, Any]:
        return {
            "company_name": self.company_name,
            "period_end": _enc_date(self.period_end),
            "prior_period_end": _enc_date(self.prior_period_end),
            "currency": self.currency,
            "sections": [s.to_json() for s in self.sections],
            "net_current_assets_this_year": _enc_dec(self.net_current_assets_this_year),
            "net_current_assets_last_year": _enc_dec(self.net_current_assets_last_year),
            "total_assets_less_liab_this_year": _enc_dec(self.total_assets_less_liab_this_year),
            "total_assets_less_liab_last_year": _enc_dec(self.total_assets_less_liab_last_year),
            "financed_by_this_year": _enc_dec(self.financed_by_this_year),
            "financed_by_last_year": _enc_dec(self.financed_by_last_year),
        }


# ---------------------------------------------------------------------------
# Profit & Loss
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProfitAndLossLine:
    section: SubClassification
    account_code: str
    account_name: str
    this_year: Decimal = _ZERO
    last_year: Decimal = _ZERO

    def __post_init__(self) -> None:
        if not self.account_code:
            raise ValueError("account_code must be non-empty")
        if not self.account_name:
            raise ValueError("account_name must be non-empty")

    def to_json(self) -> dict[str, Any]:
        return {
            "section": self.section.value,
            "account_code": self.account_code,
            "account_name": self.account_name,
            "this_year": _enc_dec(self.this_year),
            "last_year": _enc_dec(self.last_year),
        }


@dataclass(frozen=True, slots=True)
class ProfitAndLossSection:
    section: SubClassification
    title: str
    lines: tuple[ProfitAndLossLine, ...]
    subtotal_this_year: Decimal
    subtotal_last_year: Decimal

    def __post_init__(self) -> None:
        if not self.title:
            raise ValueError("title must be non-empty")

    def to_json(self) -> dict[str, Any]:
        return {
            "section": self.section.value,
            "title": self.title,
            "lines": [line.to_json() for line in self.lines],
            "subtotal_this_year": _enc_dec(self.subtotal_this_year),
            "subtotal_last_year": _enc_dec(self.subtotal_last_year),
        }


@dataclass(frozen=True, slots=True)
class ProfitAndLoss:
    company_name: str
    period_end: date
    prior_period_end: date
    currency: str
    sections: tuple[ProfitAndLossSection, ...]
    gross_profit_this_year: Decimal
    gross_profit_last_year: Decimal
    net_profit_before_tax_this_year: Decimal
    net_profit_before_tax_last_year: Decimal
    net_profit_after_tax_this_year: Decimal
    net_profit_after_tax_last_year: Decimal

    def __post_init__(self) -> None:
        if not self.company_name:
            raise ValueError("company_name must be non-empty")
        if len(self.currency) != 3:
            raise ValueError(f"currency must be 3 chars; got {self.currency!r}")

    def to_json(self) -> dict[str, Any]:
        return {
            "company_name": self.company_name,
            "period_end": _enc_date(self.period_end),
            "prior_period_end": _enc_date(self.prior_period_end),
            "currency": self.currency,
            "sections": [s.to_json() for s in self.sections],
            "gross_profit_this_year": _enc_dec(self.gross_profit_this_year),
            "gross_profit_last_year": _enc_dec(self.gross_profit_last_year),
            "net_profit_before_tax_this_year": _enc_dec(self.net_profit_before_tax_this_year),
            "net_profit_before_tax_last_year": _enc_dec(self.net_profit_before_tax_last_year),
            "net_profit_after_tax_this_year": _enc_dec(self.net_profit_after_tax_this_year),
            "net_profit_after_tax_last_year": _enc_dec(self.net_profit_after_tax_last_year),
        }


# ---------------------------------------------------------------------------
# General Ledger
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GeneralLedgerEntry:
    journal_ref: str
    running_balance: Decimal
    journal_date: date | None = None
    journal_kind: str = ""
    description: str = ""
    department: str = ""
    debit: Decimal = _ZERO
    credit: Decimal = _ZERO

    def to_json(self) -> dict[str, Any]:
        return {
            "journal_date": _enc_date(self.journal_date),
            "journal_kind": self.journal_kind,
            "journal_ref": self.journal_ref,
            "description": self.description,
            "department": self.department,
            "debit": _enc_dec(self.debit),
            "credit": _enc_dec(self.credit),
            "running_balance": _enc_dec(self.running_balance),
        }


@dataclass(frozen=True, slots=True)
class GeneralLedgerAccount:
    account_code: str
    account_name: str
    entries: tuple[GeneralLedgerEntry, ...]
    period_total_debit: Decimal
    period_total_credit: Decimal
    closing_balance: Decimal

    def __post_init__(self) -> None:
        if not self.account_code:
            raise ValueError("account_code must be non-empty")
        if not self.account_name:
            raise ValueError("account_name must be non-empty")

    def to_json(self) -> dict[str, Any]:
        return {
            "account_code": self.account_code,
            "account_name": self.account_name,
            "entries": [e.to_json() for e in self.entries],
            "period_total_debit": _enc_dec(self.period_total_debit),
            "period_total_credit": _enc_dec(self.period_total_credit),
            "closing_balance": _enc_dec(self.closing_balance),
        }


@dataclass(frozen=True, slots=True)
class GeneralLedger:
    company_name: str
    period_start: date
    period_end: date
    currency: str
    accounts: tuple[GeneralLedgerAccount, ...]
    company_registration: str = ""

    def __post_init__(self) -> None:
        if not self.company_name:
            raise ValueError("company_name must be non-empty")
        if len(self.currency) != 3:
            raise ValueError(f"currency must be 3 chars; got {self.currency!r}")

    def to_json(self) -> dict[str, Any]:
        return {
            "company_name": self.company_name,
            "company_registration": self.company_registration,
            "period_start": _enc_date(self.period_start),
            "period_end": _enc_date(self.period_end),
            "currency": self.currency,
            "accounts": [a.to_json() for a in self.accounts],
        }


# Re-exported for convenience — keeps `field` warning suppressed if unused.
_ = field  # type: ignore[unused-ignore]
