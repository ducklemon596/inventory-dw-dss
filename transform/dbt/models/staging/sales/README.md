# Sales staging

These views expose recorded sales headers and item rows. Normalization and execution rules are in the [Staging guide](../README.md); exact output contracts are in [_staging.yml](../_staging.yml).

## stg_sales_invoices

[SQL](stg_sales_invoices.sql) reads `source('raw', 'sales_invoice')` and returns one row per `sales_invoice_id`, with `sales_invoice_number`. It validates the numeric identity and trims the source number. Its direct consumer is `int_sales_lines_enriched`.

The header groups source lines by invoice code. Time, shift, cashier, payment and recorded amounts remain on the lines because their invoice-wide scope is not uniformly established. Adding header attributes would require a confirmed grouping rule.

## stg_sales_invoice_lines

[SQL](stg_sales_invoice_lines.sql) reads `source('raw', 'sales_line')`. Its grain is one `sales_invoice_line_id`, with alternate lineage identity `(dataset_name, dataset_row_number)`. `int_sales_lines_enriched` consumes every line; `dim_date` reads event dates.

The `cleaned` CTE applies field-specific text rules. The final projection validates numeric ranges, event/shift dates and categorical domains, then assigns business names. It returns 35 fields:

- Source identity and relationships: line, dataset/row, invoice, product, original unit and cashier.
- Recorded event/shift, product/classification descriptions and optional batch identity/label.
- Signed `sold_quantity`, unit price, price tier, recorded amounts and percentages.
- Payment, membership, print count and separately recorded shift attributes.

Raw `quantity` becomes `sold_quantity`; `_pct` fields become percentages on a 0–100 scale. Raw labels remain distinct from parsed attributes, such as `shift_label` versus `shift_date`. Optional amounts stay NULL, while recorded zero remains zero. Staging does not recalculate totals or assign sales eligibility.

For example, two lines under one invoice code can retain different payment/shift values. The view preserves both observations so enrichment does not need to pick an arbitrary header value. Missing batch information also keeps its original line rather than removing it.

For a change, build the selected model using the shared command, inspect its 35-column contract, then build `int_sales_lines_enriched+` and the required dimensions. Parser changes require the normalization regression; projection changes require the sales preservation and UOM tests.
