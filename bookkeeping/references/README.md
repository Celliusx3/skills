# Bookkeeping skill — invocation cheatsheet

Quick reference for the LLM agent. Pair with `read_skill("bookkeeping")`
to load the full SKILL.md, then call individual scripts via
`run_skill_script("bookkeeping", "scripts/<file>.py", ["<json>"])`.

All numeric amounts are **strings** (Decimal-precision); dates are
**ISO 8601** (`YYYY-MM-DD`). Output is single-line JSON; errors come
through as `{"error": "<class>", "message": "..."}` with exit 1.

## Common period-close pipeline

```
read_skill("bookkeeping")

→ scripts/parse_sheets.py {"kind":"coa","rows":[...]}            → coa
→ scripts/parse_sheets.py {"kind":"flat_ledger","rows":[...]}    → flat_ledger rows
→ scripts/parse_sheets.py {"kind":"manual_journals","rows":[...]} → manual_journals rows
→ scripts/journalize.py    {"flat_ledger":..., "manual_journals":..., dates}  → journal
→ scripts/period_reports/trial_balance.py    {journal, coa, ...}  → trial_balance
→ scripts/period_reports/balance_sheet.py    {journal, coa, ...}  → balance_sheet
→ scripts/period_reports/profit_and_loss.py  {journal, coa, ...}  → profit_and_loss
→ scripts/period_reports/general_ledger.py   {journal, coa, ...}  → general_ledger
```

## Drafter pipelines (depreciation / accruals)

```
→ scripts/voucher_number.py  {existing_journal_refs, voucher_type, posting_date}  → voucher_number
→ scripts/account_code.py    {existing_codes, classification, sub_classification} → account_code
→ scripts/depreciation.py    {register, period_start, period_end}                  → run
```

## Failure modes (exit 1 + envelope)

| Script | Error class | Common cause |
|--------|-------------|--------------|
| journalize | `JournalizeError` | period_end < period_start |
| period_reports/trial_balance | `TrialBalanceComputationError` | journal references account_codes the COA doesn't define |
| depreciation | `DepreciationServiceError` | period_end < period_start, unsupported method, or invalid asset register |
| voucher_number | `VoucherNumberGenerationError` | bucket exhausted (>9999 vouchers/month) |
| account_code | `AccountCodeGenerationError` | (classification, sub) has no range mapping or bucket is full |
| parse_sheets | `SheetsParseError` | malformed COA header / values; flat_ledger and manual_journals skip individual bad rows silently |
| any | `ValueError` | input JSON missing required fields or wrong shape |

## JSON shapes

See `_common/models.py` for the canonical structures of each domain
type. The `to_json()` method on each class produces the wire shape;
`from_json()` parses it back.
