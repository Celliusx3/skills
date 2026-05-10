"""Typed domain errors for the bookkeeping skill.

Each script catches its own error class and emits a single-line JSON
error envelope on stdout, exit code 1:

    {"error": "JournalizeError", "message": "..."}

Mirrors the typed errors from the former `quant.service.bookkeeping`
service module so the failure surface is unchanged.
"""

from __future__ import annotations


class JournalizeError(ValueError):
    """Malformed input that would produce an unbalanced or undefined journal."""


class DepreciationServiceError(ValueError):
    """Inputs would produce an undefined depreciation result."""


class VoucherNumberGenerationError(ValueError):
    """The (type, year_month) bucket has run dry of serials."""


class AccountCodeGenerationError(ValueError):
    """No code can be allocated for the (classification, sub) bucket."""


class SheetsParseError(ValueError):
    """A Sheets / JSON payload cannot be parsed into a typed model."""


class TrialBalanceComputationError(ValueError):
    """The journal references account_codes the COA doesn't define."""
