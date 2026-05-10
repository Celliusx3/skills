---
name: bookkeeping
description: Journalize ledger rows into double-entry journal, compute depreciation, draft trial balance / balance sheet / P&L / general ledger, generate voucher numbers and chart-of-accounts codes, parse Sheets payloads.
metadata:
  author: cellstudio
  license: Proprietary
---

# Bookkeeping skill

Stateless bookkeeping primitives for the canvas. Ports the math from the
former `quant.service.bookkeeping` Python library into a sandbox-runnable
skill (network=none, read-only, stdlib only).

## Invocation contract

Each script reads **a single JSON object** from `argv[1]` and prints
**a single line of JSON** on stdout. Errors → exit 1 with
`{"error": "<class>", "message": "..."}` on stdout (still single-line).

```bash
python scripts/<name>.py '<json input>'
```

The LLM agent calls these via `run_skill_script("bookkeeping", "scripts/<name>.py", ["<json>"])`.

## Scripts

| Script | Input | Output |
|--------|-------|--------|
| `scripts/voucher_number.py` | `{"existing_journal_refs": [...], "voucher_type": "PV"\|"OR"\|"JV"\|"CN"\|"DN", "posting_date": "YYYY-MM-DD"}` | `{"voucher_number": "PV2410-0001"}` |
| `scripts/account_code.py` | `{"existing_codes": [...], "classification": "ASSET"\|..., "sub_classification": "FIXED_ASSET"\|...}` | `{"account_code": "200-0000"}` |
| `scripts/journalize.py` | `{"flat_ledger": [...], "manual_journals": [...], "period_start": "YYYY-MM-DD", "period_end": "YYYY-MM-DD"}` | `{"journal": {"rows": [...]}}` |
| `scripts/depreciation.py` | `{"register": {"assets": [...]}, "period_start": "YYYY-MM-DD", "period_end": "YYYY-MM-DD"}` | `{"run": {...}}` |
| `scripts/parse_sheets.py` | `{"kind": "coa"\|"flat_ledger"\|"manual_journals", "rows": [["header", ...], ["row1", ...], ...]}` | `{"<kind>": ...}` |
| `scripts/period_reports/trial_balance.py` | `{"journal": {...}, "coa": {...}, "company_name": "...", "period_end": "YYYY-MM-DD", "currency": "MYR"}` | `{"trial_balance": {...}}` |
| `scripts/period_reports/balance_sheet.py` | adds `"prior_period_end"` | `{"balance_sheet": {...}}` |
| `scripts/period_reports/profit_and_loss.py` | adds `"prior_period_end"` | `{"profit_and_loss": {...}}` |
| `scripts/period_reports/general_ledger.py` | adds `"period_start"`, `"company_registration"` | `{"general_ledger": {...}}` |

## Domain shapes

See `_common/models.py` for the canonical JSON shapes. All amounts are strings
formatted as `Decimal` (e.g. `"142.30"`) — stdlib `json` can't natively encode
`decimal.Decimal`, so scripts emit / accept strings.

## Data flow on the canvas

A typical period-close pipeline:

```
SHEETS_READ (flat ledger)  ─┐
SHEETS_READ (manual JVs)   ─┼─→ LLM_AGENT (tool: run_skill_script)
SHEETS_READ (chart of accs) ─┤      │
                              │      ├─ journalize.py → journal JSON
                              │      ├─ trial_balance.py → TB JSON
                              │      ├─ balance_sheet.py → BS JSON
                              │      ├─ profit_and_loss.py → P&L JSON
                              │      └─ general_ledger.py → GL JSON
                              │
                              └─→ render via pdf-renderer skill or write to Sheets
```

## Errors

Every script catches its own typed errors and emits a JSON error envelope
on exit 1:

```json
{"error": "JournalizeError", "message": "period_end (...) precedes period_start (...)."}
```

Error classes:
- `JournalizeError` — unbalanced or out-of-window journal input
- `DepreciationServiceError` — invalid asset register or unsupported method
- `VoucherNumberGenerationError` — bucket exhausted (>9999 vouchers/month)
- `AccountCodeGenerationError` — no range mapping or bucket exhausted
- `SheetsParseError` — malformed Sheets headers or rows
- `TrialBalanceComputationError` — journal references unknown account_codes
