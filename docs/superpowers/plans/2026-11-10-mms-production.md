# MMS Production Integration Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans task by task.

**Goal:** Complete production connection and verification tooling without fabricating missing source evidence.
**Architecture:** Read-only normalized ClickHouse releases, shared runtime factory, strict reference checks.
**Tech Stack:** Existing Python 3.12, clickhouse-connect, DuckDB, sklearn, pytest, Streamlit.
**Spec:** docs/superpowers/specs/2026-11-10-mms-production-design.md

## Global constraints

- Preserve sparse observed-mart semantics and immutable UOM reference files.
- Never train a substitute production artifact, infer missing days as zero, or issue warehouse writes.
- Do not claim live/TN acceptance without original approved inputs.
- Keep environment compatibility with existing DuckDB/demo UI users.

## Review focus

Release changes between reads; mixed product units; unexpected schema/boolean metadata;
malformed/empty reference suites; production configuration silently choosing demo.
Each is covered in the corresponding task's tests.

### Task 1: Read-only ClickHouse provider and audit

Files: `mms/data/clickhouse_adapter.py`, `tests/mms/test_clickhouse.py`.
Produces `ClickHouseDataProvider.get_snapshot(T, filters)`, `.get_outcomes()`,
`audit_warehouse(client, database)` and a release-approved normalized data contract.

- [x] Write failing tests for equivalent snapshots, bound dates, validated identifiers,
  missing approval flags, mismatched releases, explicit booleans and outcome coverage.
- [x] Run tests and verify failure before implementing.
- [x] Implement queries and metadata consistency checks, reusing the existing snapshot builder.
- [x] Run `pytest tests/mms/test_clickhouse.py -q`; expect all pass.

### Task 2: Artifact and TN reference verification

Files: `mms/verification.py`, `tests/mms/test_verification.py`.
Produces `check_artifact`, `run_reference_suite` JSON-compatible reports.

- [x] Write failing tests for artifact checksum/version/cutoff checks and golden
  scenario/backtest expectations; reject empty, unknown and wrong-version cases.
- [x] Implement strict report checks; no retraining and no invented expected results.
- [x] Run targeted verification tests; expect pass with both passing and failing cases.

### Task 3: Shared runtime, CLI and team UI entrypoint

Files: `mms/runtime.py`, `mms/cli.py`, `mms/ui.py`, `pyproject.toml`, runtime/CLI/UI tests.
Consumes providers and verification functions. Produces shared source selection,
an `inventory-mms` entrypoint and embeddable UI rendering.

- [x] Write failing tests for all source choices, missing production config, JSON
  CLI failures, offline diagnostics, and Streamlit runtime integration.
- [x] Implement settings with no secret output, lazy optional imports, read-only
  clients and `render(configure_page=False)` for embedding.
- [x] Run MMS suite and build/lock checks; expect green MMS tests and valid artifacts.

### Task 4: Integration documentation and final review

- [x] Document exact ClickHouse DDL, environment variables, CLI and reference schema.
- [x] Record external dependencies and live readiness evidence in the execution ledger.
- [x] Run MMS/extraction tests and independent final review; fix Important/Critical findings.
- [x] Leave concrete code and commands ready for real inputs; report unavailable
  production/TN acceptance explicitly. Retain changes on the feature branch.

## Authorized scope addition

New artifact training and the complete labelled simulation app were authorized during execution. The pipeline, real-source download/audit and NEW1?NEW7 reports are implemented; see docs/mms-production-progress.md for evidence and remaining live approval boundaries.
