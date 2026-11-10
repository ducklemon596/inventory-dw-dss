# Production integration ledger — 2026-11-10

Plan: `docs/superpowers/plans/2026-11-10-mms-production.md`.
Continues the original [MMS ledger](mms-progress.md), whose last paragraph records
the initial pre-commit handoff. That implementation was subsequently committed
as `855d131` and pushed to `origin/feature/add_model` at the user's request.

## Decisions and scope

- Keep working in the existing requested checkout and feature branch. Preserve
  original source files, UOM references and warehouse code. No schema deployment
  or production write is authorized by a scenario operation.
- Implement the ClickHouse normalized release contract and raw-mart audit; do not
  silently carry sparse observed balances forward or convert missing days to zero.
  Cost: live production requires a separately approved release/publication step.
- The user explicitly authorized creating new artifacts and experiments after
  confirming there are no original TN files. Add new versioned training plus
  labelled simulation data for a concrete trained demonstration. Cost: simulated
  model performance is not evidence about the downloaded pharmacy's performance.
- Keep original-TN reference checks available but label the generated NEW baseline
  as a regression snapshot from current implementation, not independent validation.
- No team UI repository exists in the checkout. Provide a shared runtime,
  embeddable rendering function and a generated runnable app as integration targets.

## Tasks and evidence

1. ClickHouse provider: complete. Twelve tests cover SELECT-only reads, bound
   values, identifier validation, approval flags, versions, release changes,
   outcomes and unapproved raw observations.
2. Reference/artifact verification: complete. Golden comparisons require explicit
   cohort/date/artifact/data/snapshot/outcome versions. Missing original files,
   unknown output paths and malformed/vacuous reference cases fail explicitly.
3. Runtime/CLI/UI: complete. Demo/DuckDB/ClickHouse share settings, production
   configuration never falls back silently, read clients close promptly, and
   team apps may inject a runtime without resetting their page configuration.
4. Newly authorized training: complete. Fixed-seed HistGB fits only eligible
   historical rows and independent future labels; cutoff includes label ends.
   Missing windows fail, SOP windows are reported separately, both classes and
   minimum sample count are required, and immutable outputs refuse overwrites.
5. Download/source audit: complete. The actual README v2 archive was downloaded,
   nested ZIP read without executing scripts, and only two original raw CSVs
   extracted. CRC, sizes, SHA256, headers and consecutive RowNumber were checked.
   Actual files match documented row counts: sales 649656, stock 804027.
6. Concrete trained app: complete. `reports/mms-trained-demo/` contains the actual
   new HistGB artifact, DuckDB simulation, NEW1–NEW7 reports, saved decision,
   four-case regression baseline and app. Seed 7 training used 261 samples,
   41 positive labels and cutoff 2025-06-03; evaluation starts 2025-06-30.

## Independent review and fixes

No Critical issues. Both Important findings were reproduced with failing tests
and fixed: runtime/source changes now clear old comparisons/manager actions,
and malformed JSON `cases: null/1` returns structured CLI errors. The synthetic
readiness flag was regraded as material provenance information and fixed with a
regression. An invalid seed is also rejected before reading data or training.

The review set aside live ClickHouse compatibility/performance, real-data approval,
original TN equivalence, calibration/business effectiveness and old Windows/UOM
issues. These are explicitly not claimed as verified. ClickHouse port 8123 was
unavailable and no Docker executable was found in this environment.

The actual CSV audit found no SKU with exact-day observations at both locations
at 2025-06-30 and no complete following 30-day two-location cohort. Source files
are genuine, but this does not prove pharmacy available stock or zero demand.
Live release approval and original-TN equivalence therefore remain unfulfilled
external acceptance conditions. This is not hidden by the simulation results.

## Final checks

- `uv run --locked --extra ui --group dev pytest tests/mms tests/extraction -q`:
  **90 passed, 4 subtests passed** after the review fixes.
- Actual `bootstrap-demo` completed, producing a trained artifact and all reports.
- All four generated reference cases passed against the saved bundle.
- Source audit ran on the complete downloaded CSVs, not only fixtures.
- Existing repository-wide Windows `fcntl`/path and CRLF/UOM checksum limitations
  remain unchanged; this does not claim full warehouse acceptance.

Large raw files, archives and generated artifacts stay ignored by Git. Regenerate
the trained demo from the documented fixed-seed command after cloning.
