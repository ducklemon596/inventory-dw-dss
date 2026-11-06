INSERT INTO oltp.product(drug_code)
SELECT "DrugCode" FROM staging.sales_raw UNION SELECT "DrugCode" FROM staging.stock_raw
ON CONFLICT DO NOTHING;
INSERT INTO oltp.warehouse(warehouse_name)
SELECT DISTINCT "Warehouse" FROM staging.stock_raw ON CONFLICT DO NOTHING;
INSERT INTO oltp.unit(unit_code)
SELECT "Unit" FROM staging.sales_raw
UNION SELECT staging.stock_unit("InitialStock") FROM staging.stock_raw
UNION SELECT staging.stock_unit("StockIn") FROM staging.stock_raw
UNION SELECT staging.stock_unit("StockOut") FROM staging.stock_raw
UNION SELECT staging.stock_unit("RemainingStock") FROM staging.stock_raw
ON CONFLICT DO NOTHING;
INSERT INTO oltp.cashier(source_code)
SELECT DISTINCT "CashierID" FROM staging.sales_raw ON CONFLICT DO NOTHING;
INSERT INTO oltp.sales_invoice(invoice_number)
SELECT DISTINCT "InvoiceNumber" FROM staging.sales_raw ON CONFLICT DO NOTHING;
INSERT INTO oltp.inventory_document(document_number)
SELECT DISTINCT "DocumentNumber" FROM staging.stock_raw ON CONFLICT DO NOTHING;

INSERT INTO oltp.sales_line (
 source_row_number, invoice_id, product_id, unit_id, cashier_id, sold_at,
 shift, drug_name, manufacturer, drug_class, category, batch_and_expiry_date,
 quantity, unit_price, price_tier, discount_pct, discount_amount, service_fee,
 packaging_fee, subtotal, invoice_discount_pct, promo_discount_pct, tax_pct,
 additional_fee, total_price, payment_type, print_count, is_member)
SELECT s."RowNumber"::bigint, i.invoice_id, p.product_id, u.unit_id, c.cashier_id,
 to_timestamp(s."DateTime", 'DD Mon YYYY HH24:MI:SS')::timestamp,
 s."Shift", s."DrugName", NULLIF(s."Manufacturer",'-'), NULLIF(s."DrugClass",'-'),
 NULLIF(s."Category",'-'), s."BatchAndExpiryDate",
 staging.number_value(s."Quantity"), staging.number_value(s."UnitPrice"), s."PriceTier",
 staging.number_value(replace(s."DiscountPct",'%', '')), staging.number_value(s."DiscountAmount"),
 staging.number_value(s."ServiceFee"), staging.number_value(s."PackagingFee"),
 staging.number_value(s."Subtotal"), staging.number_value(replace(s."InvoiceDiscountPct",'%', '')),
 staging.number_value(replace(s."PromoDiscountPct",'%', '')), staging.number_value(replace(s."TaxAmount",'%', '')),
 staging.number_value(s."AdditionalFee"), staging.number_value(s."TotalPrice"),
 s."PaymentType", s."PrintCount"::integer, s."IsMember"
FROM staging.sales_raw s
JOIN oltp.sales_invoice i ON i.invoice_number=s."InvoiceNumber"
JOIN oltp.product p ON p.drug_code=s."DrugCode"
JOIN oltp.unit u ON u.unit_code=s."Unit"
JOIN oltp.cashier c ON c.source_code=s."CashierID"
ON CONFLICT (source_row_number) DO NOTHING;

INSERT INTO oltp.inventory_movement (
 source_row_number, document_id, product_id, warehouse_id, occurred_at,
 drug_name, drug_class, category, drug_type, status, description,
 initial_stock, stock_in, stock_out, remaining_stock,
 initial_unit_id, in_unit_id, out_unit_id, remaining_unit_id)
SELECT s."RowNumber"::bigint, d.document_id, p.product_id, w.warehouse_id,
 to_timestamp(s."DateTime", 'DD Mon YYYY HH24:MI:SS')::timestamp,
 s."DrugName", NULLIF(s."DrugClass",'-'), NULLIF(s."Category",'-'),
 s."DrugType", s."Status", s."TransactionDescription",
 staging.stock_quantity(s."InitialStock"), staging.stock_quantity(s."StockIn"),
 staging.stock_quantity(s."StockOut"), staging.stock_quantity(s."RemainingStock"),
 a.unit_id, b.unit_id, c.unit_id, e.unit_id
FROM staging.stock_raw s
JOIN oltp.inventory_document d ON d.document_number=s."DocumentNumber"
JOIN oltp.product p ON p.drug_code=s."DrugCode"
JOIN oltp.warehouse w ON w.warehouse_name=s."Warehouse"
JOIN oltp.unit a ON a.unit_code=staging.stock_unit(s."InitialStock")
JOIN oltp.unit b ON b.unit_code=staging.stock_unit(s."StockIn")
JOIN oltp.unit c ON c.unit_code=staging.stock_unit(s."StockOut")
JOIN oltp.unit e ON e.unit_code=staging.stock_unit(s."RemainingStock")
ON CONFLICT (source_row_number) DO NOTHING;

DO $$ BEGIN
 IF (SELECT count(*) FROM staging.sales_raw) <> (SELECT count(*) FROM oltp.sales_line) THEN
  RAISE EXCEPTION 'Sales row count mismatch';
 END IF;
 IF (SELECT count(*) FROM staging.stock_raw) <> (SELECT count(*) FROM oltp.inventory_movement) THEN
  RAISE EXCEPTION 'Stock row count mismatch';
 END IF;
END $$;
