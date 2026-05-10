"""Skill-private domain shapes and errors for the bookkeeping skill.

Not intended for import outside this skill — these types are skill-local
copies of (now-deleted) `quant.model.journal`, `quant.model.period_reports`,
`quant.model.manual_journal_drafts`, plus skill-private copies of the
still-live `quant.model.chart_of_accounts` and `quant.model.fixed_asset`.

Stdlib-only (frozen dataclasses) so the skill runs in the sandbox without
a `setup_command`.
"""
