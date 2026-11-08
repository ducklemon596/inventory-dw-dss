# Conformed dimensions

Dimensions describe facts; they do not aggregate measures or create transactions. Product, warehouse and unit keys reuse numeric OLTP IDs. Calendar_date is a Date32 natural date key. JOIN facts using these keys, not labels. ClickHouse sorting keys do not enforce unique/FK constraints; tests do.

[_dimensions.yml](_dimensions.yml) is the complete schema/test contract. Run dimensions and their tests with:

```bash
uv run --locked dbt build --select +dim_product +dim_unit +dim_warehouse +dim_date --project-dir transform/dbt --profiles-dir transform/dbt --vars '{"uom_mapping_version":"uom_mapping_v2_2026-11-08"}'
```

This selection does not rebuild facts. Use the full build after broad raw changes. Related fact tests run in the [mart suite](../../../tests/README.md).

### Model: `dim_product`

**Purpose:** Expose the current product catalog and classification names.

**Grain:** One product_id; product_code is the unique DrugCode business key. Materialization: **table**.

**Inputs:** [stg_products](../../staging/reference/stg_products.sql), [stg_manufacturers](../../staging/reference/stg_manufacturers.sql), [stg_drug_classes](../../staging/reference/stg_drug_classes.sql), [stg_categories](../../staging/reference/stg_categories.sql).

**Main logic:**

1. Read product identities, current names and optional classification IDs.
2. LEFT JOIN manufacturer, drug class and category by their numeric IDs.
3. Preserve all products and nullable attributes as Type 1 current values.

**Important columns:** `product_id`, `product_code`, nullable `product_name` and manufacturer/class/category IDs/names.

**Output:** All three Facts join this dimension by product_id in analytical queries; it is not a parent ref in their SQL.

**Business rules:** Optional NULL means missing catalog information. Do not replace it with a fabricated label. Facts retain line-recorded names; joining this dimension reclassifies history using current attributes.

**How to modify it safely:** Keep product business-key mapping and left joins; adding Type 1 attributes must not remove products or fan out facts. No SCD2 is configured.

**Tests:** ID/business-key uniqueness, nullable lookup relationships, preserves_source_rows, matches_declared_schema, product_dimension_labels and native missing-attribute fixture; all three facts reference product_id. Use the selected-model command in [dbt execution](../../../README.md) or the test instructions at the start of this README. Full column types and declared tests: [_dimensions.yml](_dimensions.yml).

### Model: `dim_warehouse`

**Purpose:** Describe recorded inventory warehouses.

**Grain:** One warehouse_id; warehouse_name is also unique in the current contract. Materialization: **table**.

**Inputs:** [stg_warehouses](../../staging/reference/stg_warehouses.sql).

**Main logic:**

1. Read typed warehouse staging.
2. Project the numeric identity and exact recorded name.
3. Rebuild the current two-column lookup without adding sales relationships.

**Important columns:** `warehouse_id`, `warehouse_name`.

**Output:** The movement and daily inventory Facts join this dimension by warehouse_id; sales has no warehouse FK.

**Business rules:** Only inventory facts have a warehouse FK; a product being stocked in a warehouse does not identify where a sale occurred.

**How to modify it safely:** Preserve identity and uniqueness; test both inventory fact joins if adding attributes.

**Tests:** Not-null/unique ID and name, source preservation, exact schema; inventory fact relationships and dimensional JOIN cardinality. Use the selected-model command in [dbt execution](../../../README.md) or the test instructions at the start of this README. Full column types and declared tests: [_dimensions.yml](_dimensions.yml).

### Model: `dim_unit`

**Purpose:** Describe exact recorded units for all quantity roles.

**Grain:** One unit_id; unit_code is an exact unique business label. Materialization: **table**.

**Inputs:** [stg_units](../../staging/reference/stg_units.sql).

**Main logic:**

1. Read typed unit staging.
2. Project the source identity and exact label.
3. Publish the full lookup so every quantity role can join the same dimension.

**Important columns:** `unit_id`, `unit_code`.

**Output:** All three Facts join their original/verified/four-role stock units to this dimension as documented; the Fact SQL does not ref it.

**Business rules:** Labels are not synonyms and do not encode a factor. Sales original/verified units and four inventory quantity-unit roles use separate FKs.

**How to modify it safely:** Do not normalize differing labels into one unit. Label changes can invalidate historical sales conversion; run UOM and fact relationship tests.

**Tests:** ID/label uniqueness, preservation, exact schema and every fact unit-role relationship/JOIN cardinality test. Use the selected-model command in [dbt execution](../../../README.md) or the test instructions at the start of this README. Full column types and declared tests: [_dimensions.yml](_dimensions.yml).

### Model: `dim_date`

**Purpose:** Provide calendar attributes for complete years covered by observed event dates.

**Grain:** One calendar_date, Date32. Materialization: **table**.

**Inputs:** [stg_sales_invoice_lines](../../staging/sales/stg_sales_invoice_lines.sql), [stg_inventory_movements](../../staging/inventory/stg_inventory_movements.sql).

**Main logic:**

1. Find minimum/maximum dates across typed sales and inventory events.
2. Expand the bounds to complete calendar years; return no rows if both inputs are empty.
3. Generate each date and derive civil year/quarter/month, ISO weekday/week/year, month start and weekend.

**Important columns:** `calendar_date`, `calendar_year`, `calendar_month`, `iso_day_of_week`, `iso_week`, `iso_year`, `month_start_date`, `is_weekend`.

**Output:** All three Facts join sold_date, movement_date or observation_date to calendar_date; calendar rows do not create Fact observations.

**Business rules:** Calendar rows never generate sales or stock observations. ISO year can differ from civil year near New Year.

**How to modify it safely:** Preserve Date32 range behavior, empty-source handling, leap days and ISO definitions; event-bound changes require rebuilding date coverage.

**Tests:** Date uniqueness/not-null, exact schema, calendar_integrity, native full-year leap/ISO and empty-input fixtures; all fact date relationships. Use the selected-model command in [dbt execution](../../../README.md) or the test instructions at the start of this README. Full column types and declared tests: [_dimensions.yml](_dimensions.yml).
