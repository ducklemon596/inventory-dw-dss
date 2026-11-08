# Governed sales UOM conversion

Recorded sales and inventory can use different units for the same DrugCode. Conversion is
a separate enrichment: original sales quantities, units, financial fields and historical
inventory models remain unchanged. No sales warehouse or net-return relationship is inferred.
Version pinning fixes mapping decisions; reproducibility also requires the same source/export
vintage. Stock-unit evidence spans that export and does not establish point-in-time knowledge.

**Status: COMPLETE.** Both supplied immutable snapshots are integrated and independently
validated. The official seed contains **397 rows**: 190 v1 and 207 v2. The original research
skeleton/changelog were unavailable; the maintained changelog records source checksums and
the verified snapshot diff without reconstructing research artifacts.

## Reference and versioning

- Seed: [`uom_conversion_mapping.csv`](../transform/dbt/seeds/uom_conversion_mapping.csv).
- Immutable sources: [v1](../data/reference/uom/uom_conversion_mapping_v1.csv) and
  [v2](../data/reference/uom/uom_conversion_mapping_v2.csv).
- [Changelog and publication rules](../data/reference/uom/MAPPING_CHANGELOG.md).
- Default variable: `uom_mapping_version: uom_mapping_v2_2026-11-08` in `dbt_project.yml`.

| Version | Available pairs / SKUs | Approved | Candidate | Quarantined |
|---|---:|---:|---:|---:|
| v2 | 207 / 197 | 87 | 89 | 31 |
| v1 | 190 / 182 | 73 | 87 | 30 |

Seed keys are `(mapping_version, product_id, sales_unit)`. The mapping's **`product_id`
is POS DrugCode**, joined exactly to sales `product_code`; the numeric OLTP product ID is
retained separately. All mapping codes and unit labels match actual source domains without
case folding or normalization. All v2 targets agree with recorded stock-unit evidence.

All supplied evidence fields are preserved. Approved/candidate factors use nullable
`Decimal(18,6)`; mode shares and price ratios use `Decimal(38,18)` to preserve source digits.
Every seed field was compared with the original CSV after loading: all 397 rows match exactly. The 190 common pairs have identical decisions/evidence
except their version stamp; v2 adds 17 pairs across 15 SKUs.
Non-approved `factor_approved` is missing; a candidate numeric factor never means approval.
The immutable source checksum and exact seed/snapshot row union are tested in Python.

## Models and safeguards

| Model | Grain / behavior |
|---|---|
| `int_product_stock_units` | Dataset × product; verify all quantity-unit fields and agreement across warehouses before exposing a stock unit |
| `int_sales_quantity_converted` | One original sales line; retain all 42 input columns, add version, stock unit, factor, result, status and evidence |
| `int_sales_uom_coverage` | Dataset × product × original unit × mapping version; line counts and absolute original-unit quantities |

These are views. Conversion rules:

- **identity:** exact sales-unit equality with verified product stock unit; retain quantity,
  apply factor one and distinguish it from approved cross-unit conversion.
- **approved:** only Tier A + explicit approved status + positive approved factor + compatible
  verified target; multiply with exact Decimal128 arithmetic to `Nullable(Decimal(38,12))`.
- **candidate / quarantined:** retain status and original quantity; result and applied factor are missing.
- **unmapped:** no supported mapping/stock evidence; original quantity remains, result is missing.

The selected version is stamped on every row. The selected-version existence test gates
builds, and SQL guards reject unpublished versions when querying the model. There is no
fallback or cross-version merge. Explicit factors contradicting a verified identity raise
an error. Mapping uniqueness, target compatibility, source preservation and exact conversion
are tested. A factor one between different unit labels remains an **approved** conversion,
never inferred identity. Price checks are evidence; they do not create or revoke supplied approvals.

## Run and inspect

From the repository root, with the existing servers running:

```bash
uv run --locked dbt seed --select uom_conversion_mapping --project-dir transform/dbt --profiles-dir transform/dbt
uv run --locked dbt build --project-dir transform/dbt --profiles-dir transform/dbt \
  --vars '{"uom_mapping_version":"uom_mapping_v2_2026-11-08"}'
uv run --locked dbt show --select uom_coverage_summary --project-dir transform/dbt --profiles-dir transform/dbt
uv run --locked dbt show --select uom_coverage_measurement --limit 20 --project-dir transform/dbt --profiles-dir transform/dbt
uv run --locked python -m unittest discover -s tests/uom -v
uv run --locked python tests/uom/integration.py
```

Deployment should pin the version explicitly. To select another authentic published version,
pass its identifier to `--vars`, rebuild the conversion/coverage views and run tests before
reading coverage. `dbt show --vars` alone does not rebuild an existing version-pinned view.
Both v1 and v2 are selectable; unknown versions still fail. Replace the version value with
`uom_mapping_v1_2026-11-08` to reproduce v1. Pass the same `--vars` value to coverage analyses
when inspecting v1; the default remains v2.

New approvals require a **new immutable snapshot**, not editing existing rows. Append the
new version to the seed, retain old versions and evidence, add its expected counts/checksum,
and validate each version independently. Both current snapshots are retained byte-for-byte;
new approvals must never edit either one. No dependency upgrades or extraction changes are needed.

## Measured full-DW coverage

Both full builds preserve 649,656 distinct sales-line IDs, with exactly one selected version
stamped on every row. Measurements use the same full DW scope, including pairs absent in v1.

| Metric | v1 | v2 |
|---|---:|---:|
| Identity lines | 636,919 | 636,919 |
| Approved conversion lines | 6,889 | 8,859 |
| Candidate lines | 107 | 109 |
| Quarantined lines | 33 | 34 |
| Unmapped lines | 5,708 | 3,735 |
| Known conversion-needed lines | 9,002 | 9,002 |
| Approved row coverage among conversion-needed lines | 76.527438% | 98.411464% |
| Approved observed conversion-needed pairs | 73 / 207 | 87 / 207 |
| Fully / partially / unresolved conversion-needed SKUs | 68 / 4 / 125 | 80 / 5 / 112 |

The 17 pairs absent from v1 account for 1,973 known conversion-needed lines, which stay
unmapped under v1 rather than using v2 factors. Version v1 leaves 17 pairs absent from its snapshot unmapped; these lines are not filled from v2.

The 3,735 v2 unmapped lines across 19 products lack stock-unit evidence and cannot be
classified as known conversion-needed or identity. All 207 observed conversion-needed pairs
match v2; v1 deliberately leaves its 17 absent pairs unmapped. Pair coverage is separate
from row coverage and SKU coverage.

Quantity coverage is `covered absolute recorded quantity / total absolute recorded quantity`
**within one SKU and its original sales unit**; zero denominators return missing percentages.
Absolute quantities avoid cancellation from negative recorded quantities. They do not turn
sales into net sales. The coverage view has 3,351 SKU/unit groups, including identity and
unmapped observations. Quantities from Box, Tab, Strip or different SKU/unit groups are never
pooled into a global quantity denominator. The detailed analysis exposes each group's covered
and unresolved quantities and percentage.

The research's global **98.55% v2** and **75.04% v1** quantity figures are not claimed reproduced:
its weighting/aggregation implementation was unavailable. Provide
that methodology or compatible denominator/weights to validate a global measure. Counts and
per-SKU/unit results above are measured directly; no expected percentage was forced.

## Validation and performance

Full dbt builds with **each version independently**: **252 PASS** per version, no warnings,
errors or skips: 23 models, one seed, 220 data tests,
eight native unit tests. New tests cover cross-warehouse unit agreement, exact fractional,
negative and zero quantities, all statuses, version isolation, factor-one cross-unit conversion,
source preservation and coverage reconciliation. Six Python reference tests protect both
checksums, exact seed union, governance and unchanged v1 decisions in v2. Unknown versions
are rejected; v1 is validated against its own decisions rather than v2 coverage.
Compiled-SQL tests use a disposable ClickHouse DB to verify
unknown-version errors, candidate-factor exclusion and contradictory identity rejection.

Existing extraction regression and its 107 staging nodes pass; all 52 normalization cases
and existing Python tests pass. Historical reconciliation still has 804,027 movements,
188 gaps, 8,335 segments and 496,938 daily observations. No historical SQL was changed.

The conversion views take approximately 0.03 seconds to create; creation does not compute
all sales. An uncached full conversion-status query took **0.34 s**, reading about **1.87M
rows / 73 MB**, with no writes. The richer coverage summary took **1.97 s** locally.
These costs support retaining views; no incremental materialization was introduced.

The seed is the dbt input for the approved snapshots. Published source files remain immutable under `data/reference/uom/`; the changelog records version checksums and changes. The analytical models keep original sales quantities and apply only the selected version’s approved factors.
