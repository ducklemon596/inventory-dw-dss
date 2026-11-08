# Shared dbt macros

| File / macros | Responsibility |
|---|---|
| [staging_normalization.sql](staging_normalization.sql): `stg_text` | Trim whitespace and field-specific missing markers; preserve business codes unless a field's rule says otherwise |
| `stg_integer` | Integer syntax, positive/nonnegative policy, accurate range cast |
| `stg_decimal` | Signed decimal syntax, precision/scale guards; percentage comma/percent normalization and 0–100 bounds |
| `stg_date`, `stg_timestamp` | Format/range/round-trip validation; microsecond timestamp precision |
| `stg_domain` | Explicit case/whitespace normalization and allowed categorical labels |
| [uom_mapping_version.sql](uom_mapping_version.sql): `uom_mapping_version_literal` | Validate version identifier shape and emit one safe SQL literal |

These are SQL-generating Jinja helpers, not Python data processing. Non-nullable parsing occurs before conversion to Nullable where necessary so malformed optional numbers cannot silently become NULL. Empty/missing optional fields remain NULL; placeholder branches inside parsers are not replacements in final records.

A normalization change affects every calling model. Update [normalization cases](../../../tests/staging/README.md), build staging, inspect compiled SQL and run full downstream regression. Do not add global case folding to product codes/units or relax strictness to make invalid input pass. Business aggregations belong in models, not parser macros. Generic data-test macros are documented separately under [tests/generic](../tests/generic/README.md).
