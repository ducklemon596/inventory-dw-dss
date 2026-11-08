# Conformed dimensions

These four full-rebuild MergeTree tables describe the shared product, warehouse, unit and calendar roles used by facts. [_dimensions.yml](_dimensions.yml) is the complete field/type/test contract. Real numeric identities come from OLTP; `dim_date` is keyed by the calendar date.

## dim_product

[SQL](dim_product.sql) reads `stg_products` and LEFT JOINs `stg_manufacturers`, `stg_drug_classes` and `stg_categories`. Its grain is one `product_id`. The nine output fields are product ID/code/name and the three classification ID/name pairs.

The dimension exposes current Type 1 catalog attributes. Missing classifications remain NULL; no synthetic unknown catalog entry is added. Transaction-recorded names remain in the facts. For example, a renamed product has its current name in this dimension while an older sales line still carries the name recorded on that line.

All three facts reference `product_id` for analytical joins. Product dimension SQL is not a parent in the fact `ref()` graph, so a fact ancestor selection alone does not refresh it. Lookup uniqueness, nullable labels, source preservation and fact join cardinality are covered by existing tests.

## dim_warehouse

[SQL](dim_warehouse.sql) projects `stg_warehouses` into one row per `warehouse_id`, with `warehouse_name`. It retains each recorded location as a separate entity.

The inventory movement and daily facts reference this dimension. There is no sales warehouse relationship. Changing warehouse identity or grouping changes the interpretation of inventory ledgers; changing a label refreshes the current description. Key/name uniqueness, exact preservation and inventory relationships are tested.

## dim_unit

[SQL](dim_unit.sql) projects `stg_units` into one row per `unit_id`, with its exact `unit_code`. It also includes reserved key `0`, labeled `NOT_VERIFIED_STOCK_UNIT`. This row represents unverified stock-unit evidence, never a physical unit or conversion target. The dimension contains labels rather than product-independent conversion factors.

Sales reference the original unit and a stock-unit evidence role. Only a missing `verified_stock_unit_id` becomes key `0` in the sales fact; its upstream value and fact unit code remain NULL. Inventory movement facts reference opening, receipt, issue and closing unit roles; daily facts reference their observed closing unit. These roles can join the same dimension independently. Box and Tab remain separate labels even when a particular product has an approved conversion.

Use `unit_id != 0` when counting physical units or selecting verified business units; exclude `verified_stock_unit_id = 0` from verified-unit calculations. Key `0` cannot authorize a conversion. Source units use positive OLTP identities; tests reject a source key collision, a missing/duplicate/mislabeled special member, or its use in original sales/inventory unit roles. Identity/label uniqueness, exact preservation of every real source unit and every fact unit-role relationship are tested. Unit changes also affect stock evidence and sales conversion, requiring a complete branch rebuild.

## dim_date

[SQL](dim_date.sql) reads `stg_sales_invoice_lines.sold_at` and `stg_inventory_movements.movement_at`. It takes the earliest and latest event years, then generates every calendar date in those complete years. If both event sources are empty, the calendar is empty. Shift and expiry dates do not set calendar coverage.

At one row per `calendar_date`, its ten fields cover civil year/quarter/month/day, ISO weekday/week/year, month start and weekend. All three facts reference this dimension through their event/observation date roles. Calendar coverage supplies labels; it does not generate sales or stock observations on missing dates.

Tests cover exact bounds/coverage, leap days, ISO boundaries, empty event sources and all fact date relationships.

## Run and modify

From the repository root:

```bash
uv run --locked inventory-dw-dss transform --select dimensions
```

Build parent Staging views first when their SQL changed, or select `+dim_product` for that dimension's ancestors. Use `transform --test --select dimensions` through the public CLI for existing dimensions; a complete build validates all fact relationships as well. [dbt execution](../../../README.md) explains selection and cross-model test dependencies.

Keep one parent row per dimension key and preserve nullable catalog values. Validate fact row counts after analytical joins whenever a dimension join changes. These joins must not multiply transactions or use `ANY JOIN` to hide duplicate dimension keys.
