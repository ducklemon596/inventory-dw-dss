# Inventory staging

These views retain source documents, product lots and movement observations. The shared [Staging guide](../README.md) explains normalization and commands; [_staging.yml](../_staging.yml) is the complete field/type/test reference.

## stg_inventory_documents

[SQL](stg_inventory_documents.sql) reads `source('raw', 'inventory_document')`. It returns one row per `inventory_document_id`, with `inventory_document_number`, after identity validation and text normalization. `int_inventory_movements_enriched` joins these document codes to movements.

A document code can occur at different times or locations. The document view does not assign one assumed warehouse or transaction timestamp to all its rows.

## stg_product_batches

[SQL](stg_product_batches.sql) reads `source('raw', 'product_batch')`. It returns one `product_batch_id` with `product_id`, `product_batch_number` and `expiration_date`. It validates IDs and expiry while preserving a missing expiry. Its direct consumer is `int_sales_lines_enriched`, which joins on both batch and product.

A batch belongs to one product; the same batch text alone is not a unique lot identity. Source inventory movements have no verified batch relationship, so this view does not assign lots to stock.

## stg_inventory_movements

[SQL](stg_inventory_movements.sql) reads `source('raw', 'inventory_movement')`. Its grain is one `inventory_movement_id`, with alternate lineage identity `(dataset_name, dataset_row_number)`. It exposes 25 fields covering:

- Dataset/row, movement, document, product and warehouse identities and `movement_at`.
- Transaction-recorded product descriptions, status, classification and extracted description references.
- `opening_stock_quantity`, `received_quantity`, `issued_quantity`, `closing_stock_quantity` and each quantity's unit ID.

The `cleaned` CTE applies field-specific missing markers. The projection parses four exact quantities, preserves event-time precision and validates recognized categorical domains. `UNKNOWN` remains a recorded transaction type. RETURN direction comes from received/issued quantities; negative balances stay negative.

Direct consumers are `int_inventory_movements_enriched`, `int_product_stock_units` and `dim_date`. For example, opening 10, receipt 5, issue 3 and closing 12 remain four recorded quantities. Intermediate derives a delta of 2 and checks the row balance; Staging preserves the observations needed for that check.

After editing, build the selected view and its tests. A quantity/unit/order change affects the full inventory chain and the sales stock-unit evidence branch. Use a complete build for acceptance so sales conversion, stock reconstruction and dimension relationships are checked together.
