# Staging: typed source records

Staging converts raw text into named analytical types while preserving source grain. It trims whitespace, recognizes field-specific missing markers, validates integer ranges and Decimal precision, checks calendar/time round trips and normalizes approved category domains. Required malformed values fail; optional missing values stay NULL. Literal business codes and unit labels are not globally case-folded or replaced.

[Normalization macros](../../macros/README.md) implement these guards. [_sources.yml](_sources.yml) describes raw inputs; [_staging.yml](_staging.yml) describes typed outputs and their tests. These are input and output contracts respectively, not two copies of model SQL.

Do not add business aggregation, forecasting, UOM approval or inventory repair here. Keep one row per source row, preserve numeric/source identity associations and retain exact Decimal quantities. Snapshot input grains below also equal output grains; there are no JOINs in Staging.

Run all staging checks after raw loading:

```bash
uv run --locked dbt build --select staging --project-dir transform/dbt --profiles-dir transform/dbt --vars '{"uom_mapping_version":"uom_mapping_v2_2026-11-08"}'
```

For one model, replace `staging` with its name. `dbt test --select MODEL_NAME` with the same project/profile/version options tests an existing relation. Shared checks include `normalized_values`, `source_row_counts`, not-null/unique IDs and declared relationships. [Python normalization cases](../../../../tests/staging/README.md) exercise malformed edge values.

### Model: `stg_manufacturers`

**Purpose:** Expose a consistently typed manufacturer lookup.

**Grain:** One manufacturer record. One input record produces one output record. Materialization: **view**.

**Inputs:** `source('raw', 'manufacturer')`; [SQL](reference/stg_manufacturers.sql).

**Main logic:**

1. Read the raw record and trim field text using field-specific missing markers.
2. Parse IDs as positive UInt32; validate dates when present and cast labels to the declared String/LowCardinality types.
3. Expose business column names without filtering or aggregating records.

**Important columns:** `manufacturer_id` is the source numeric key; `manufacturer_name` provide its labels and attributes.

**Output:** `dim_product`.

**Business rules:** Preserve positive UInt32 identity and a required label.

**How to modify it safely:** Preserve ID/code distinctions and nullable fields; update YAML and normalization cases for any new parser rule. Rebuild dependent models after changing labels.

**Tests:** Declared ID not-null/uniqueness, relationships where applicable, shared normalization and source row counts. Run the selected-model command above. Complete contract: [_staging.yml](_staging.yml).

### Model: `stg_drug_classes`

**Purpose:** Expose a consistently typed drug classification lookup.

**Grain:** One drug classification record. One input record produces one output record. Materialization: **view**.

**Inputs:** `source('raw', 'drug_class')`; [SQL](reference/stg_drug_classes.sql).

**Main logic:**

1. Read the raw record and trim field text using field-specific missing markers.
2. Parse IDs as positive UInt32; validate dates when present and cast labels to the declared String/LowCardinality types.
3. Expose business column names without filtering or aggregating records.

**Important columns:** `drug_class_id` is the source numeric key; `drug_class_name` provide its labels and attributes.

**Output:** `dim_product`.

**Business rules:** Preserve positive UInt32 identity and a required label.

**How to modify it safely:** Preserve ID/code distinctions and nullable fields; update YAML and normalization cases for any new parser rule. Rebuild dependent models after changing labels.

**Tests:** Declared ID not-null/uniqueness, relationships where applicable, shared normalization and source row counts. Run the selected-model command above. Complete contract: [_staging.yml](_staging.yml).

### Model: `stg_categories`

**Purpose:** Expose a consistently typed category lookup.

**Grain:** One product category record. One input record produces one output record. Materialization: **view**.

**Inputs:** `source('raw', 'category')`; [SQL](reference/stg_categories.sql).

**Main logic:**

1. Read the raw record and trim field text using field-specific missing markers.
2. Parse IDs as positive UInt32; validate dates when present and cast labels to the declared String/LowCardinality types.
3. Expose business column names without filtering or aggregating records.

**Important columns:** `category_id` is the source numeric key; `category_name` provide its labels and attributes.

**Output:** `dim_product`.

**Business rules:** Preserve positive UInt32 identity and a required label.

**How to modify it safely:** Preserve ID/code distinctions and nullable fields; update YAML and normalization cases for any new parser rule. Rebuild dependent models after changing labels.

**Tests:** Declared ID not-null/uniqueness, relationships where applicable, shared normalization and source row counts. Run the selected-model command above. Complete contract: [_staging.yml](_staging.yml).

### Model: `stg_products`

**Purpose:** Expose a consistently typed current product catalog.

**Grain:** One product catalog record. One input record produces one output record. Materialization: **view**.

**Inputs:** `source('raw', 'product')`; [SQL](reference/stg_products.sql).

**Main logic:**

1. Read the raw record and trim field text using field-specific missing markers.
2. Parse IDs as positive UInt32; validate dates when present and cast labels to the declared String/LowCardinality types.
3. Expose business column names without filtering or aggregating records.

**Important columns:** `product_id` is the source numeric key; `product_code`, `product_name`, `manufacturer_id`, `drug_class_id`, `category_id` provide its labels and attributes.

**Output:** `dim_product`, `int_inventory_movements_enriched`, `int_product_stock_units`, `int_sales_lines_enriched`.

**Business rules:** DrugCode becomes product_code; numeric identity remains separate. Optional catalog attributes remain NULL.

**How to modify it safely:** Preserve ID/code distinctions and nullable fields; update YAML and normalization cases for any new parser rule. Rebuild dependent models after changing labels.

**Tests:** Declared ID not-null/uniqueness, relationships where applicable, shared normalization and source row counts. Run the selected-model command above. Complete contract: [_staging.yml](_staging.yml).

### Model: `stg_warehouses`

**Purpose:** Expose a consistently typed warehouse lookup.

**Grain:** One warehouse record. One input record produces one output record. Materialization: **view**.

**Inputs:** `source('raw', 'warehouse')`; [SQL](reference/stg_warehouses.sql).

**Main logic:**

1. Read the raw record and trim field text using field-specific missing markers.
2. Parse IDs as positive UInt32; validate dates when present and cast labels to the declared String/LowCardinality types.
3. Expose business column names without filtering or aggregating records.

**Important columns:** `warehouse_id` is the source numeric key; `warehouse_name` provide its labels and attributes.

**Output:** `dim_warehouse`, `int_inventory_movements_enriched`.

**Business rules:** Preserve the recorded warehouse identity/name; do not infer sales assignment.

**How to modify it safely:** Preserve ID/code distinctions and nullable fields; update YAML and normalization cases for any new parser rule. Rebuild dependent models after changing labels.

**Tests:** Declared ID not-null/uniqueness, relationships where applicable, shared normalization and source row counts. Run the selected-model command above. Complete contract: [_staging.yml](_staging.yml).

### Model: `stg_units`

**Purpose:** Expose a consistently typed unit lookup.

**Grain:** One unit-of-measure record. One input record produces one output record. Materialization: **view**.

**Inputs:** `source('raw', 'unit')`; [SQL](reference/stg_units.sql).

**Main logic:**

1. Read the raw record and trim field text using field-specific missing markers.
2. Parse IDs as positive UInt32; validate dates when present and cast labels to the declared String/LowCardinality types.
3. Expose business column names without filtering or aggregating records.

**Important columns:** `unit_id` is the source numeric key; `unit_code` provide its labels and attributes.

**Output:** `dim_unit`, `int_inventory_movements_enriched`, `int_product_stock_units`, `int_sales_lines_enriched`.

**Business rules:** Unit labels remain exact business labels; Box and Tab are not synonyms.

**How to modify it safely:** Preserve ID/code distinctions and nullable fields; update YAML and normalization cases for any new parser rule. Rebuild dependent models after changing labels.

**Tests:** Declared ID not-null/uniqueness, relationships where applicable, shared normalization and source row counts. Run the selected-model command above. Complete contract: [_staging.yml](_staging.yml).

### Model: `stg_cashiers`

**Purpose:** Expose a consistently typed cashier lookup.

**Grain:** One cashier record. One input record produces one output record. Materialization: **view**.

**Inputs:** `source('raw', 'cashier')`; [SQL](reference/stg_cashiers.sql).

**Main logic:**

1. Read the raw record and trim field text using field-specific missing markers.
2. Parse IDs as positive UInt32; validate dates when present and cast labels to the declared String/LowCardinality types.
3. Expose business column names without filtering or aggregating records.

**Important columns:** `cashier_id` is the source numeric key; `cashier_code` provide its labels and attributes.

**Output:** `int_sales_lines_enriched`.

**Business rules:** Cashier source_code becomes cashier_code; keep code formatting.

**How to modify it safely:** Preserve ID/code distinctions and nullable fields; update YAML and normalization cases for any new parser rule. Rebuild dependent models after changing labels.

**Tests:** Declared ID not-null/uniqueness, relationships where applicable, shared normalization and source row counts. Run the selected-model command above. Complete contract: [_staging.yml](_staging.yml).

### Model: `stg_sales_invoices`

**Purpose:** Expose a consistently typed sales header lookup.

**Grain:** One sales invoice header. One input record produces one output record. Materialization: **view**.

**Inputs:** `source('raw', 'sales_invoice')`; [SQL](sales/stg_sales_invoices.sql).

**Main logic:**

1. Read the raw record and trim field text using field-specific missing markers.
2. Parse IDs as positive UInt32; validate dates when present and cast labels to the declared String/LowCardinality types.
3. Expose business column names without filtering or aggregating records.

**Important columns:** `sales_invoice_id` is the source numeric key; `sales_invoice_number` provide its labels and attributes.

**Output:** `int_sales_lines_enriched`.

**Business rules:** Do not promote line-level financial values to this header.

**How to modify it safely:** Preserve ID/code distinctions and nullable fields; update YAML and normalization cases for any new parser rule. Rebuild dependent models after changing labels.

**Tests:** Declared ID not-null/uniqueness, relationships where applicable, shared normalization and source row counts. Run the selected-model command above. Complete contract: [_staging.yml](_staging.yml).

### Model: `stg_inventory_documents`

**Purpose:** Expose a consistently typed inventory document lookup.

**Grain:** One inventory document header. One input record produces one output record. Materialization: **view**.

**Inputs:** `source('raw', 'inventory_document')`; [SQL](inventory/stg_inventory_documents.sql).

**Main logic:**

1. Read the raw record and trim field text using field-specific missing markers.
2. Parse IDs as positive UInt32; validate dates when present and cast labels to the declared String/LowCardinality types.
3. Expose business column names without filtering or aggregating records.

**Important columns:** `inventory_document_id` is the source numeric key; `inventory_document_number` provide its labels and attributes.

**Output:** `int_inventory_movements_enriched`.

**Business rules:** A warehouse document is not assumed to be a sales invoice.

**How to modify it safely:** Preserve ID/code distinctions and nullable fields; update YAML and normalization cases for any new parser rule. Rebuild dependent models after changing labels.

**Tests:** Declared ID not-null/uniqueness, relationships where applicable, shared normalization and source row counts. Run the selected-model command above. Complete contract: [_staging.yml](_staging.yml).

### Model: `stg_product_batches`

**Purpose:** Expose a consistently typed batch lookup.

**Grain:** One product batch record. One input record produces one output record. Materialization: **view**.

**Inputs:** `source('raw', 'product_batch')`; [SQL](inventory/stg_product_batches.sql).

**Main logic:**

1. Read the raw record and trim field text using field-specific missing markers.
2. Parse IDs as positive UInt32; validate dates when present and cast labels to the declared String/LowCardinality types.
3. Expose business column names without filtering or aggregating records.

**Important columns:** `product_batch_id` is the source numeric key; `product_id`, `product_batch_number`, `expiration_date` provide its labels and attributes.

**Output:** `int_sales_lines_enriched`.

**Business rules:** Keep missing expiry nullable and preserve batch/product association; do not fabricate batches.

**How to modify it safely:** Preserve ID/code distinctions and nullable fields; update YAML and normalization cases for any new parser rule. Rebuild dependent models after changing labels.

**Tests:** Declared ID not-null/uniqueness, relationships where applicable, shared normalization and source row counts. `product_batch_natural_key` also protects product/batch/expiry identity. Run the selected-model command above. Complete contract: [_staging.yml](_staging.yml).

### Model: `stg_sales_invoice_lines`

**Purpose:** Expose typed recorded sales lines.

**Grain:** One source sales line, keyed by sales_invoice_line_id; alternate (dataset_name,dataset_row_number). One input record produces one output record. Materialization: **view**.

**Inputs:** `source('raw', 'sales_line')`; [SQL](sales/stg_sales_invoice_lines.sql).

**Main logic:**

1. Normalize raw fields separately; preserve source identity and original labels.
2. Parse DateTime64(6), Decimal(18,6) quantities/amounts, bounded percentages and optional batch/shift attributes.
3. Rename invoice/batch/unit identifiers and business quantities; preserve every source line.

**Important columns:** `sold_at`, `sold_quantity`, `unit_price`, line-recorded descriptions/financials, `unit_id`, `product_batch_id`, and dataset/source-row lineage.

**Output:** `dim_date`, `int_sales_lines_enriched`.

**Business rules:** No quantity conversion, invoice total formula, return matching or warehouse assignment. Optional monetary values stay nullable; candidate concepts do not exist in this layer.

**How to modify it safely:** Keep all original fields, precision and source keys. Add cast failure cases and check every downstream projection before changing a column.

**Tests:** `sales_line_source_key`, `sales_line_batch_product`, source counts, strict normalization, primary ID and declared header/product/unit/cashier/batch relationships. Run the selected-model command above. Complete contract: [_staging.yml](_staging.yml).

### Model: `stg_inventory_movements`

**Purpose:** Expose typed recorded inventory observations.

**Grain:** One source inventory movement, keyed by inventory_movement_id; alternate dataset/source row. One input record produces one output record. Materialization: **view**.

**Inputs:** `source('raw', 'inventory_movement')`; [SQL](inventory/stg_inventory_movements.sql).

**Main logic:**

1. Normalize descriptions and field-specific missing markers without reclassifying unknown descriptions.
2. Parse time, four Decimal(18,6) quantities and their four UInt32 unit IDs.
3. Expose movement/product/warehouse/document identities and unchanged transaction classification.

**Important columns:** `movement_at`, `opening_stock_quantity`, `received_quantity`, `issued_quantity`, `closing_stock_quantity`, four unit IDs, `transaction_type` and source lineage.

**Output:** `dim_date`, `int_inventory_movements_enriched`, `int_product_stock_units`.

**Business rules:** Negative balances, RETURN direction, UNKNOWN and zero-flow rows remain. No movement-type sign inference or balance adjustment.

**How to modify it safely:** Preserve all quantity roles and ordering identifiers; verify parser cases, unit relationships and exact recorded balance before building inventory descendants.

**Tests:** `inventory_movement_source_key`, source counts, normalization, primary ID and declared document/product/warehouse/unit relationships. Intermediate tests check recorded balance and unit agreement. Run the selected-model command above. Complete contract: [_staging.yml](_staging.yml).
