# Staging types and normalization

Staging views preserve one row per raw record. They validate values again even
when bootstrap has already cleaned OLTP. Raw and PostgreSQL remain unchanged.
Business descriptions are in `_staging.yml`; technical conversion rules live in
`macros/staging_normalization.sql`.

## Compact types

The complete current raw dataset was profiled before selecting these types.

| Values | Previous type | Staging type | Fixed bytes/value |
|---|---|---|---|
| IDs and dataset row numbers | Int64 | UInt32 | 8 → 4 |
| Document print count | Int32 | UInt16 | 4 → 2 |
| Price tier number | Int32 | UInt8 | 4 → 1 |
| Quantities and monetary values | Decimal(38,6) | Decimal(18,6) | 16 → 8 |
| Percentages | Decimal(38,6) | Decimal(9,4) | 16 → 4 |
| Repeated short labels | String | LowCardinality(String) | Dictionary-dependent |

Optional values retain nullability; dictionary-encoded optional labels use
`LowCardinality(Nullable(String))`. IDs can grow to 4,294,967,295; larger values
fail instead of wrapping. Quantities and money allow 12 integer and 6 fractional
digits. Percentages allow 4 fractional digits and must be between 0 and 100.
Observed maxima include 804,027 for IDs, 1,700,000 for monetary values and 200,211
for stock balances; stock can be negative. Observed effective percentage scale is 2.
Dates remain Date32 (4 bytes); expiration dates currently extend to 2123. Timestamps
remain DateTime64(6) (8 bytes) to preserve microseconds. Calendar bounds are explicit:
1900-01-01 through 2299-12-31. No business timezone is inferred.

Fixed-width payload per sales row changes from 268 to 123 bytes; per inventory
movement from 144 to 76 bytes. These figures exclude strings, dictionary overhead,
null masks and compression. **Views store no result rows:** this does not reduce
raw disk usage. Savings apply to typed query results and downstream materialization;
LowCardinality benefits depend on data and workload.

## Missing values and text

- Trim surrounding whitespace, including tabs, newlines and nonbreaking spaces.
  Whitespace-only text becomes NULL. Missing required values fail conversion/tests.
- Optional numeric/date/ID fields and descriptive product/manufacturer/class/category/
  supplier/price-tier labels recognize whole-value `-`, `null`, `none`, `n/a`
  case-insensitively. Zero dates (`0000-00-00`) are recognized only for optional dates.
- Identifiers and free-text descriptions do not use that global marker list.
  Preserve leading zeros, case and meaningful internal whitespace in codes/names;
  `NA` and `N/A` can remain literal identifiers. Free text is trimmed only.
- A standalone `-` batch number means an unknown batch number. Keep the batch row,
  its product_batch_id and relationships, but expose product_batch_number as nullable.
  All 252 such rows in the current raw dataset are retained. Batch natural-key
  uniqueness still includes the nullable number and expiration date.
- Missing quantities/fees are never filled with zero. Preserve actual zero and
  negative quantities/amounts. No inventory balance or invoice-total formulas are imposed.

## Strict values

Numeric text must use ordinary signed decimal notation. Money/quantity fields do
not guess thousands separators or decimal commas. Percentages additionally accept
a trailing `%` and decimal comma, such as `2,86%`. Reject malformed text, NaN,
infinity, overflow and significant fractional digits exceeding the chosen scale;
extra trailing zeroes are allowed. Conversion to a non-nullable base type occurs
before restoring optional NULLs, because direct nullable casts can hide parse errors.

Dates must be ISO dates; timestamps must use `YYYY-MM-DD HH:MM:SS[.ffffff]` (a `T`
separator is accepted). Reject invalid calendar dates rather than accepting parser
rollover; round-trip validation also protects against range clamping and truncation.

Categorical values normalize case and whitespace to these explicit domains:

| Column | Allowed labels |
|---|---|
| payment_method | TUNAI, KARTU, KREDIT |
| membership_status | NON MEMBER, MEMBER |
| shift_period | PAGI, SORE |
| consignment_status | NON KONSINYASI, KONSINYASI |
| product_status | AKTIF |
| transaction_type | SALE, TRANSFER, PURCHASE, UNKNOWN, IMPORT_STOCKTAKE, IMPORT_PRODUCT, RETURN, CREATE_PRODUCT |

Unknown nonempty labels fail; they are not converted to NULL or guessed. `UNKNOWN`
is a valid inventory classification and remains distinct from a missing value.
Update explicit domains after investigating a legitimate new label. Membership
remains a label rather than an inferred boolean.

## Checks

```bash
uv run --locked python tests/staging/integration.py
DBT_PROFILES_DIR=. uv run --locked --directory transform/dbt dbt build --select staging
```

The integration check compiles the real macros and executes valid/invalid SELECT
cases in ClickHouse without changing data. dbt checks accepted domains, existing
key/relationship constraints, raw-to-staging row counts and every projected column.
Malformed optional values therefore fail the build even when no financial metric
is being computed. No rows are silently filtered or deduplicated.
