# Source sequence integrity — validated 2026-11-08

**PASS:** the original ledger sequence and its association with source records
are preserved from the current POS CSV export through prepared CSV, PostgreSQL,
ClickHouse raw, dbt staging and intermediate. The DW can reproduce this export's
ledger order using `dataset_row_number`. This result is specific to the supplied
export vintage and does not establish a native POS/OLTP transaction or CDC sequence.

Validation reads PostgreSQL and ClickHouse without modifying source or raw data. PostgreSQL reads use a repeatable-read, read-only transaction; ClickHouse queries are read-only.

## Sequence lineage

| Layer | Actual source-sequence field | Record identity / event time |
|---|---|---|
| Original inventory CSV | `data/raw/stock_raw.csv.RowNumber` | `DrugCode`, `Warehouse`, `DateTime`, `DocumentNumber` |
| Prepared inventory CSV | `data/processed/1mo/stock/*.csv.RowNumber` | Original columns retained; parsed `event_datetime` and four quantities/units added |
| PostgreSQL | `oltp.inventory_movement.source_row_number` with `source_dataset` | Generated `movement_id`; `product_id`, `warehouse_id`; `occurred_at` |
| ClickHouse raw | `raw.inventory_movement.source_row_number` with `source_dataset` | The same `movement_id` and reference IDs, stored as text; `occurred_at` |
| dbt staging | `inventory_dw.stg_inventory_movements.dataset_row_number` with `dataset_name` | `inventory_movement_id` aliases `movement_id`; `movement_at` aliases `occurred_at` |
| dbt intermediate | `inventory_dw.int_inventory_movements_enriched.dataset_row_number` with `dataset_name` | Direct preservation of staging identifiers and event time |

The Excel `No`/`No.` → CSV `RowNumber` origin is supplied research provenance;
the original workbook was not available for independent re-extraction. All local
layers from the original CSV onward were compared against the supplied
[`sequence_passport_v2.json`](../data/reference/sequence_passport_v2.json).

Code tracing confirms that preprocessing validates `RowNumber` and retains its
original column. `_row_order` is only a temporary sorting helper and is dropped.
The loader directly assigns `s."RowNumber"::bigint` to `source_row_number`.
`movement_id` is a separate PostgreSQL identity column. Reference-resolution joins
and inserts do not promise source row order, so generated IDs are not ledger order.
Extraction copies existing columns using PostgreSQL `::text`; raw is physically
sorted by the generated PK, which does not remove the retained source sequence.
Staging casts the retained sequence to UInt32; intermediate passes it through.
Neither layer regenerates it with `row_number()`.

Sales follows the same pattern: `sales_raw.csv.RowNumber` → prepared `RowNumber`
→ `oltp.sales_line.source_row_number` → `raw.sales_line.source_row_number`
→ `stg_sales_invoice_lines.dataset_row_number`
→ `int_sales_lines_enriched.dataset_row_number`. Its separate generated key is
`sales_line_id`, exposed as `sales_invoice_line_id`.

## Validation results

Scope: `source_dataset` / `dataset_name = 'pharmacy_2023_2025'`. The following
inventory results hold independently at **all six accessible layers**:

| Check | Expected snapshot | Actual | Status |
|---|---:|---:|---|
| Rows | 804,027 | 804,027 | PASS |
| Non-null sequence | 804,027 | 804,027 | PASS |
| Distinct sequence | 804,027 | 804,027 | PASS |
| Sequence minimum / maximum | 1 / 804,027 | 1 / 804,027 | PASS |
| Sequence sum | 323,230,110,378 | 323,230,110,378 | PASS |
| Sequence sum of squares | 173,257,265,047,964,930 | 173,257,265,047,964,930 | PASS |
| Missing sequence / duplicate sequence rows | 0 / 0 | 0 / 0 | PASS |
| Sequence-to-record mapping | Exact match | 0 missing, extra or mismatched records at every hop | PASS |
| Ordered sequence/content fingerprints | Passport values | All match at all six layers | PASS |
| Product–warehouse series | 8,147 | 8,147 | PASS |
| Source-order transitions | 795,880 | 795,880 | PASS |
| Continuous / discontinuous transitions | 795,692 / 188 | 795,692 / 188 | PASS |
| Timestamp inversions under source sequence | 0 | 0 | PASS |

All 649,656 sales rows likewise retain sequences 1–649,656 without NULLs, missing
or duplicate sequence values. Sum 211,026,783,996 and sum of squares
91,396,614,598,064,916 match the passport. All sales fingerprints and every
cross-layer record comparison also match.

Both existing sets of 36 prepared monthly files match their stored SHA-256
checksums. Their manifest source hashes match the current original CSVs:

```text
stock: a0da6a0295e32f3ad2dae67bec706ad2c290181c35bf2aaf1eecd375199174fd
sales: d306bfdadfdf2e3ea5cd1eeb687c2fb827579407d0c2a85d550b433ae1239ec9
```

The prepared manifest retains the original source paths; source hashes verify that the files under `data/raw/` have identical content. The manifest and data remain unchanged.

## Record attachment and identifier mapping

The validation merge-joins explicitly ordered streams on the retained source
sequence. It compares individual values, independently of the fingerprint checks:

- Inventory: product code, warehouse name, event timestamp, transaction description,
  opening/received/issued/closing quantities, document number, transaction product
  name and all four unit codes.
- Sales: event timestamp, invoice number, product code, sold quantity and unit.
- Database-to-database hops also compare every identifier used in those records:
  inventory movement/product/warehouse/document/four units, and sales
  line/product/invoice/unit/cashier/optional batch IDs.

Quantities are compared as exact Python `Decimal` values, without float conversion
or rounding. NULLs are compared explicitly. Raw → staging allows the existing
trim/blank-to-NULL text normalization; intermediate must preserve staging values
exactly. Every hop has **zero unmatched records, zero payload mismatches and zero
identifier mismatches**, for both datasets.

Source `DrugCode` maps through `oltp.product.drug_code` / raw `drug_code` /
staging `product_code`; source `Warehouse` maps through `warehouse_name`; unit
labels map through `unit_code`; document/invoice numbers map through their header
tables. The passport's `product_id` and `warehouse_id` refer to these **business
labels**, not the newly generated numeric OLTP identifiers. This mapping reproduces
both content fingerprints and the ordered identity fingerprint.

## Fingerprint reproduction

The passport's normalization and the following serialization reproduce every
reference value. The original generator was not supplied; these exact procedures
were established by recomputing and matching all supplied fingerprint values.

1. Row fields: passport `row_field_order`; text trimmed and whitespace collapsed;
   timestamps `YYYY-MM-DD HH:MM:SS`; quantities integral text when integral,
   otherwise minimal decimal text. Join fields with `|`, encode UTF-8 and MD5.
2. S1: sort distinct sequence integers numerically, join decimal strings with `,`,
   with no trailing comma or newline; MD5 the UTF-8 bytes.
3. S2 multiset sum: interpret the first eight bytes of each row MD5 as an unsigned
   **big-endian** integer; sum modulo 2^64, retaining duplicate rows.
4. S2 set: sort distinct lowercase row-MD5 hex strings, join with `,`, no trailing
   separator; MD5 the UTF-8 bytes. Both source datasets have unique normalized
   content rows in this snapshot.
5. S3: in explicit source-sequence order, serialize `sequence:row_MD5_hex` on each
   line; join with LF and **no final LF**; MD5 the UTF-8 bytes.

| Fingerprint | Inventory: expected = actual | Sales: expected = actual |
|---|---|---|
| S1 | `facd289af19cea6830173f58e3b78b75` | `22207aff7f58230a24fc87a3aad2f64a` |
| S2 multiset sum64 | `3947342997120092640` | `6395143243885318083` |
| S2 content set | `65a946ad391fd2aadf2badced0c070a9` | `6f839ed8febc8923802811c0e3a4e7ca` |
| S3 ordered identity | `1ab4fce65e3b529dca707c0d1b8e88a5` | `a58f8b681d7bb820c8e4e0506abe9366` |

These hashes match independently at CSV, prepared, PostgreSQL, raw, staging and
intermediate. S1 establishes the sequence set; S2 checks content; S3 additionally
binds each sequence to its normalized record. Direct field comparisons above
provide the separate evidence that counts or sequence-only hashes cannot supply.
The supplied S1 values are not full-file CSV MD5 checksums.

## Ordering equivalence and ledger continuity

Within the scoped `product_id × warehouse_id` ledger:

| Ordering | Transitions | Continuous | Gaps | Gap rate | Same-timestamp gaps |
|---|---:|---:|---:|---:|---:|
| `dataset_row_number` | 795,880 | 795,692 | 188 | 0.023622% | 181 |
| `movement_at, dataset_row_number` | 795,880 | 795,692 | 188 | 0.023622% | 181 |
| `movement_at, inventory_movement_id` | 795,880 | 795,410 | 470 | 0.059054% | 263 |

CSV and all five downstream layers independently produce the 188-gap source-order
result. Separate ClickHouse window queries reproduce the same counts. Global
timestamps are nondecreasing by source sequence: zero inversions, with 40,522
adjacent equal-time pairs in inventory. Consequently adding event time before the
source sequence does not change this snapshot's order.

**The two identifiers are not equivalent:**

- `dataset_row_number = inventory_movement_id` on **0 of 804,027 rows**.
- Ordering by the generated identity alone changes **793,560 within-ledger ranks**
  across **5,736 ledgers** and changes the predecessor of **591,314 rows**.
- Timestamp plus identity changes the source predecessor of **409 rows** and
  produces **282 additional gaps** overall.
- There are **326** product/warehouse/timestamp tie groups containing **766 rows**;
  **324 groups** contain different closing balances. Reordering these tied records
  can also change the closing balance carried into the next timestamp. Therefore
  even strictly-later-time gaps rise from **7** under source order to **207**
  under timestamp/identity order.

This discrepancy first arises from **using the generated OLTP identity as an
ordering key**, not from losing the export sequence during a pipeline hop. The
smallest correction for future diagnostic/model queries is to use the preserved
source sequence within this export scope. No pipeline or stored IDs were changed.

## Existing source discontinuities and closing observations

All 188 discontinuities are already present in the original CSV. In 184, both
adjacent descriptions contain `stokopname`. The four other adjacencies are:

| Product / warehouse | Previous → current sequence | Previous closing → next opening | Offset |
|---|---|---|---:|
| `SW2106002231` / Apotek | 147912 → 149420 | 12 → 8 | -4 |
| `SW2106000039` / Apotek | 385491 → 386540 | 124 → 120 | -4 |
| `SW2106000407` / Apotek | 601084 → 601085 | 1195 → 1200 | +5 |
| `SW2106000407` / Apotek | 601085 → 602295 | 1190 → 1185 | -5 |

For example, sequences 147911 → 147912 are both stock-count descriptions at
2023-07-07 19:20:09: previous closing 14, next opening 18, offset +4. The first
non-stocktake row above later has offset -4. These are preserved observations;
no stock-count reset, compensation or deletion rule was applied.

The description-based 184/4 split reproduces the reference association counts.
It is not an implementation of the passport's business classification
`stocktake_batch_offset_net_zero`: the passport contains no row-level membership
or batch-grouping algorithm. Segments use local recorded opening anchors. Classification as net-zero stocktake batches remains unsupported without a row-level research algorithm.

Read-only diagnostic aggregation also reconciles the passport's closing checks:

- **496,938** observed product/warehouse/date groups.
- **144** groups have different closing quantities at their latest timestamp.
- **8** have no later ledger observation; **136** have a next opening to compare.
- Selecting the last **source-sequence** observation gives **133 matches** and
  **3 mismatches** against the next opening, matching the passport's 136/133 counts.

The export order resolves which row is last observed in that export. It does not
certify the true physical closing balance or repair the remaining discrepancies.
All four quantity units align within rows; adjacent closing/opening units match;
all 804,027 individual movement balance equations reconcile exactly.

## Current modeling constraints

The source sequence is validated for this export vintage only. Keep `(dataset_name, dataset_row_number)` scoped to the verified export and its passport fingerprints. `dataset_name` has no separate export-vintage field; a future export may reset or change row numbers. This key is not an extraction watermark. Event-time extraction retains its separately documented late-arrival and correction limitations.

Inventory models preserve source gaps, start locally anchored segments at each gap, and expose discontinuity differences as diagnostics. The evidence does not establish stock availability, historical knowledge time, stock-count reset semantics or native transaction order outside this export.

## Run the validator

Use the existing dependencies and running servers from the repository root:

```bash
uv run --locked python scripts/validation/validate_source_sequence.py \
  --passport data/reference/sequence_passport_v2.json \
  --output /tmp/source-sequence-validation.json
```

The [entry point](../scripts/validation/validate_source_sequence.py) calls the reusable
[validator](../src/inventory_dw_dss/validation/source_sequence.py). It reads ordered
streams in bounded batches, checks existing prepared-file checksums without
rerunning preparation and writes an optional JSON report. PostgreSQL and ClickHouse
reads are read-only. Connection settings use the same environment variables as
extraction. Results are reconciled to the supplied passport; snapshot counts are not
embedded as permanent pipeline constraints.
