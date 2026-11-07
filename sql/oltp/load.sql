-- OLTP LOAD PIPELINE
-- ==================
-- Contract: `incoming_sales` and `incoming_stock` are temporary text tables made
-- by the Python loader and populated with COPY. `inventory.source_dataset` is set
-- for this transaction. Run after schema.sql and do not execute this file alone.
-- All commands run inside one transaction; any raised exception rolls everything back.

-- COMMAND 01 — validate source keys.
-- Each selected CSV row must have one source RowNumber per dataset. Duplicates
-- would make the idempotent upsert ambiguous, so reject them before any writes.
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM incoming_sales GROUP BY "RowNumber"::bigint HAVING count(*) > 1)
 OR EXISTS (SELECT 1 FROM incoming_stock GROUP BY "RowNumber"::bigint HAVING count(*) > 1) THEN
  RAISE EXCEPTION 'Duplicate source row key in selected input';
 END IF;
END $$;

-- COMMAND 02 — create missing product identities.
-- Products can arrive in either feed; insert the union once and keep existing IDs.
INSERT INTO oltp.product(drug_code)
SELECT "DrugCode" FROM incoming_sales UNION SELECT "DrugCode" FROM incoming_stock
ON CONFLICT DO NOTHING;

-- COMMAND 03 — collect and validate product catalog observations.
-- Combine labels from this run with the existing product master. Empty strings and
-- '-' mean missing. A missing label does not erase a known master value; conflicting
-- non-null labels for one drug code abort the transaction.
CREATE TEMP TABLE catalog_observation ON COMMIT DROP AS
SELECT "DrugCode" AS drug_code, NULLIF(btrim("DrugName"),'') AS drug_name,
 NULLIF(NULLIF(btrim("Manufacturer"),'-'),'') AS manufacturer,
 NULLIF(NULLIF(btrim("DrugClass"),'-'),'') AS drug_class,
 NULLIF(NULLIF(btrim("Category"),'-'),'') AS category FROM incoming_sales
UNION
SELECT "DrugCode", NULLIF(btrim("DrugName"),''), NULL::text,
 NULLIF(NULLIF(btrim("DrugClass"),'-'),''), NULLIF(NULLIF(btrim("Category"),'-'),'') FROM incoming_stock
UNION
SELECT p.drug_code, p.drug_name, m.manufacturer_name, d.drug_class_name, c.category_name
FROM oltp.product p
LEFT JOIN oltp.manufacturer m USING(manufacturer_id)
LEFT JOIN oltp.drug_class d USING(drug_class_id)
LEFT JOIN oltp.category c USING(category_id)
WHERE p.drug_code IN (SELECT "DrugCode" FROM incoming_sales UNION SELECT "DrugCode" FROM incoming_stock);

DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM catalog_observation GROUP BY drug_code HAVING
 count(DISTINCT drug_name)>1 OR count(DISTINCT manufacturer)>1 OR
 count(DISTINCT drug_class)>1 OR count(DISTINCT category)>1) THEN
 RAISE EXCEPTION 'Conflicting product attributes; resolve source data before loading';
 END IF;
END $$;
-- COMMAND 04 — upsert catalog labels and resolve product foreign keys.
-- Insert only unseen labels, then update product master attributes from the
-- validated observations. Transaction snapshots remain on their source rows.
INSERT INTO oltp.manufacturer(manufacturer_name)
SELECT DISTINCT manufacturer FROM catalog_observation WHERE manufacturer IS NOT NULL ON CONFLICT DO NOTHING;
INSERT INTO oltp.drug_class(drug_class_name)
SELECT DISTINCT drug_class FROM catalog_observation WHERE drug_class IS NOT NULL ON CONFLICT DO NOTHING;
INSERT INTO oltp.category(category_name)
SELECT DISTINCT category FROM catalog_observation WHERE category IS NOT NULL ON CONFLICT DO NOTHING;
WITH attributes AS (
 SELECT drug_code, max(drug_name) AS drug_name, max(manufacturer) AS manufacturer,
 max(drug_class) AS drug_class, max(category) AS category
 FROM catalog_observation GROUP BY drug_code
)
UPDATE oltp.product p SET drug_name=a.drug_name, manufacturer_id=m.manufacturer_id,
 drug_class_id=d.drug_class_id, category_id=c.category_id
FROM attributes a
LEFT JOIN oltp.manufacturer m ON m.manufacturer_name=a.manufacturer
LEFT JOIN oltp.drug_class d ON d.drug_class_name=a.drug_class
LEFT JOIN oltp.category c ON c.category_name=a.category
WHERE p.drug_code=a.drug_code
AND ROW(
     p.drug_name,p.manufacturer_id,p.drug_class_id,p.category_id
 )
 IS DISTINCT FROM ROW(
     a.drug_name,m.manufacturer_id,d.drug_class_id,c.category_id
 );
DROP TABLE catalog_observation;

-- COMMAND 05 — resolve shared natural-key entities.
-- Insert missing warehouses, units, cashiers, invoices, and inventory documents.
-- ON CONFLICT preserves existing surrogate IDs and allows detail FKs to resolve.
INSERT INTO oltp.warehouse(warehouse_name)
SELECT DISTINCT "Warehouse" FROM incoming_stock ON CONFLICT DO NOTHING;
INSERT INTO oltp.unit(unit_code)
SELECT "Unit" FROM incoming_sales
UNION SELECT initial_stock_unit FROM incoming_stock
UNION SELECT stock_in_unit FROM incoming_stock
UNION SELECT stock_out_unit FROM incoming_stock
UNION SELECT remaining_stock_unit FROM incoming_stock
ON CONFLICT DO NOTHING;
INSERT INTO oltp.cashier(source_code)
SELECT DISTINCT "CashierID" FROM incoming_sales ON CONFLICT DO NOTHING;
INSERT INTO oltp.sales_invoice(invoice_number)
SELECT DISTINCT "InvoiceNumber" FROM incoming_sales ON CONFLICT DO NOTHING;
INSERT INTO oltp.inventory_document(document_number)
SELECT DISTINCT "DocumentNumber" FROM incoming_stock ON CONFLICT DO NOTHING;

-- COMMAND 06 — resolve product batches referenced by sales rows.
-- Rows with no parsed batch number do not create a placeholder batch. The natural
-- key includes expiry; the schema treats NULL expiry as a comparable key value.
INSERT INTO oltp.product_batch(product_id, batch_number, expiry_date)
SELECT DISTINCT p.product_id, s.batch_number, NULLIF(s.expiry_date, '')::date
FROM incoming_sales s JOIN oltp.product p ON p.drug_code = s."DrugCode"
WHERE NULLIF(s.batch_number, '') IS NOT NULL
ON CONFLICT ON CONSTRAINT product_batch_natural_key DO NOTHING;

-- COMMAND 07 — prepare per-run statistics.
-- ANALYZE improves join estimates for the following temporary-table resolutions.
-- `load_stats` records row counts and final reconciliation counts by dataset.
ANALYZE incoming_sales;
ANALYZE incoming_stock;
CREATE TEMP TABLE load_stats (
 dataset text PRIMARY KEY, rows_read bigint, inserted bigint, updated bigint, unchanged bigint,
 matched bigint DEFAULT 0
) ON COMMIT DROP;

-- COMMAND 08 — resolve each incoming sales row to its OLTP foreign keys.
-- The joins must produce exactly one candidate per input row; optional batch lookup
-- can return NULL when the source row has no recognized batch.
CREATE TEMP TABLE candidate_sales ON COMMIT DROP AS
SELECT
 current_setting('inventory.source_dataset') AS source_dataset,
 s."RowNumber"::bigint AS source_row_number,
 i.invoice_id AS invoice_id,
 p.product_id AS product_id,
 u.unit_id AS unit_id,
 c.cashier_id AS cashier_id,
 s.event_datetime::timestamp AS sold_at,
 s."Shift" AS shift,
 s."DrugName" AS drug_name,
 NULLIF(s."Manufacturer", '-') AS manufacturer,
 NULLIF(s."DrugClass", '-') AS drug_class,
 NULLIF(s."Category", '-') AS category,
 s."BatchAndExpiryDate" AS batch_and_expiry_date,
 replace(s."Quantity", ',', '.')::numeric AS quantity,
 replace(s."UnitPrice", ',', '.')::numeric AS unit_price,
 s."PriceTier" AS price_tier,
 NULLIF(s.discount_pct_value, '')::numeric AS discount_pct,
 NULLIF(replace(s."DiscountAmount", ',', '.'), '')::numeric AS discount_amount,
 NULLIF(replace(s."ServiceFee", ',', '.'), '')::numeric AS service_fee,
 NULLIF(replace(s."PackagingFee", ',', '.'), '')::numeric AS packaging_fee,
 NULLIF(replace(s."Subtotal", ',', '.'), '')::numeric AS subtotal,
 NULLIF(s.invoice_discount_pct_value, '')::numeric AS invoice_discount_pct,
 NULLIF(s.promo_discount_pct_value, '')::numeric AS promo_discount_pct,
 NULLIF(s.tax_pct_value, '')::numeric AS tax_pct,
 NULLIF(replace(s."AdditionalFee", ',', '.'), '')::numeric AS additional_fee,
 NULLIF(replace(s."TotalPrice", ',', '.'), '')::numeric AS total_price,
 s."PaymentType" AS payment_type,
 NULLIF(s."PrintCount", '')::integer AS print_count,
 s."IsMember" AS is_member,
 b.batch_id AS batch_id,
 NULLIF(s.shift_date, '')::date AS shift_date,
 NULLIF(s.shift_period, '') AS shift_period,
 NULLIF(s.shift_cashier_code, '') AS shift_cashier_code,
 NULLIF(s.price_tier_number, '')::integer AS price_tier_number
FROM incoming_sales s
JOIN oltp.sales_invoice i ON i.invoice_number = s."InvoiceNumber"
JOIN oltp.product p ON p.drug_code = s."DrugCode"
JOIN oltp.unit u ON u.unit_code = s."Unit"
JOIN oltp.cashier c ON c.source_code = s."CashierID"
LEFT JOIN oltp.product_batch b ON b.product_id = p.product_id AND b.batch_number = s.batch_number
 AND b.expiry_date IS NOT DISTINCT FROM NULLIF(s.expiry_date, '')::date;
DO $$ BEGIN
 IF (SELECT count(*) FROM incoming_sales) <> (SELECT count(*) FROM candidate_sales) THEN
  RAISE EXCEPTION 'sales: input rows lost or multiplied during FK resolution';
 END IF;
END $$;
-- COMMAND 09 — classify sales rows before writing.
-- Compare every persisted business attribute with the candidate. This separates
-- inserts, changed rows, and identical rows without relying on aggregate totals.
INSERT INTO load_stats(dataset, rows_read, inserted, updated, unchanged)
SELECT 'sales', count(*), count(*) FILTER (WHERE t.sales_line_id IS NULL),
 count(*) FILTER (WHERE t.sales_line_id IS NOT NULL AND ROW(
     t.invoice_id, t.product_id, t.unit_id, t.cashier_id,
     t.sold_at, t.shift, t.drug_name, t.manufacturer,
     t.drug_class, t.category, t.batch_and_expiry_date, t.quantity,
     t.unit_price, t.price_tier, t.discount_pct, t.discount_amount,
     t.service_fee, t.packaging_fee, t.subtotal, t.invoice_discount_pct,
     t.promo_discount_pct, t.tax_pct, t.additional_fee, t.total_price,
     t.payment_type, t.print_count, t.is_member, t.batch_id,
     t.shift_date, t.shift_period, t.shift_cashier_code, t.price_tier_number
 ) IS DISTINCT FROM ROW(
     n.invoice_id, n.product_id, n.unit_id, n.cashier_id,
     n.sold_at, n.shift, n.drug_name, n.manufacturer,
     n.drug_class, n.category, n.batch_and_expiry_date, n.quantity,
     n.unit_price, n.price_tier, n.discount_pct, n.discount_amount,
     n.service_fee, n.packaging_fee, n.subtotal, n.invoice_discount_pct,
     n.promo_discount_pct, n.tax_pct, n.additional_fee, n.total_price,
     n.payment_type, n.print_count, n.is_member, n.batch_id,
     n.shift_date, n.shift_period, n.shift_cashier_code, n.price_tier_number
 )),
 count(*) FILTER (WHERE t.sales_line_id IS NOT NULL AND ROW(
     t.invoice_id, t.product_id, t.unit_id, t.cashier_id,
     t.sold_at, t.shift, t.drug_name, t.manufacturer,
     t.drug_class, t.category, t.batch_and_expiry_date, t.quantity,
     t.unit_price, t.price_tier, t.discount_pct, t.discount_amount,
     t.service_fee, t.packaging_fee, t.subtotal, t.invoice_discount_pct,
     t.promo_discount_pct, t.tax_pct, t.additional_fee, t.total_price,
     t.payment_type, t.print_count, t.is_member, t.batch_id,
     t.shift_date, t.shift_period, t.shift_cashier_code, t.price_tier_number
 ) IS NOT DISTINCT FROM ROW(
     n.invoice_id, n.product_id, n.unit_id, n.cashier_id,
     n.sold_at, n.shift, n.drug_name, n.manufacturer,
     n.drug_class, n.category, n.batch_and_expiry_date, n.quantity,
     n.unit_price, n.price_tier, n.discount_pct, n.discount_amount,
     n.service_fee, n.packaging_fee, n.subtotal, n.invoice_discount_pct,
     n.promo_discount_pct, n.tax_pct, n.additional_fee, n.total_price,
     n.payment_type, n.print_count, n.is_member, n.batch_id,
     n.shift_date, n.shift_period, n.shift_cashier_code, n.price_tier_number
 ))
FROM candidate_sales n
LEFT JOIN oltp.sales_line t USING (source_dataset, source_row_number);

-- COMMAND 10 — insert new sales rows or update changed sales rows.
-- The scoped source key keeps sales_line_id stable. The WHERE clause suppresses
-- no-op updates, so unchanged records retain their existing tuple version.
INSERT INTO oltp.sales_line AS t (
 source_dataset, source_row_number, invoice_id, product_id,
 unit_id, cashier_id, sold_at, shift,
 drug_name, manufacturer, drug_class, category,
 batch_and_expiry_date, quantity, unit_price, price_tier,
 discount_pct, discount_amount, service_fee, packaging_fee,
 subtotal, invoice_discount_pct, promo_discount_pct, tax_pct,
 additional_fee, total_price, payment_type, print_count,
 is_member, batch_id, shift_date, shift_period,
 shift_cashier_code, price_tier_number
)
SELECT
 source_dataset, source_row_number, invoice_id, product_id,
 unit_id, cashier_id, sold_at, shift,
 drug_name, manufacturer, drug_class, category,
 batch_and_expiry_date, quantity, unit_price, price_tier,
 discount_pct, discount_amount, service_fee, packaging_fee,
 subtotal, invoice_discount_pct, promo_discount_pct, tax_pct,
 additional_fee, total_price, payment_type, print_count,
 is_member, batch_id, shift_date, shift_period,
 shift_cashier_code, price_tier_number
 FROM candidate_sales
ON CONFLICT (source_dataset, source_row_number) DO UPDATE SET
 invoice_id = excluded.invoice_id,
 product_id = excluded.product_id,
 unit_id = excluded.unit_id,
 cashier_id = excluded.cashier_id,
 sold_at = excluded.sold_at,
 shift = excluded.shift,
 drug_name = excluded.drug_name,
 manufacturer = excluded.manufacturer,
 drug_class = excluded.drug_class,
 category = excluded.category,
 batch_and_expiry_date = excluded.batch_and_expiry_date,
 quantity = excluded.quantity,
 unit_price = excluded.unit_price,
 price_tier = excluded.price_tier,
 discount_pct = excluded.discount_pct,
 discount_amount = excluded.discount_amount,
 service_fee = excluded.service_fee,
 packaging_fee = excluded.packaging_fee,
 subtotal = excluded.subtotal,
 invoice_discount_pct = excluded.invoice_discount_pct,
 promo_discount_pct = excluded.promo_discount_pct,
 tax_pct = excluded.tax_pct,
 additional_fee = excluded.additional_fee,
 total_price = excluded.total_price,
 payment_type = excluded.payment_type,
 print_count = excluded.print_count,
 is_member = excluded.is_member,
 batch_id = excluded.batch_id,
 shift_date = excluded.shift_date,
 shift_period = excluded.shift_period,
 shift_cashier_code = excluded.shift_cashier_code,
 price_tier_number = excluded.price_tier_number
WHERE ROW(
     t.invoice_id, t.product_id, t.unit_id, t.cashier_id,
     t.sold_at, t.shift, t.drug_name, t.manufacturer,
     t.drug_class, t.category, t.batch_and_expiry_date, t.quantity,
     t.unit_price, t.price_tier, t.discount_pct, t.discount_amount,
     t.service_fee, t.packaging_fee, t.subtotal, t.invoice_discount_pct,
     t.promo_discount_pct, t.tax_pct, t.additional_fee, t.total_price,
     t.payment_type, t.print_count, t.is_member, t.batch_id,
     t.shift_date, t.shift_period, t.shift_cashier_code, t.price_tier_number
 ) IS DISTINCT FROM ROW(
     excluded.invoice_id, excluded.product_id, excluded.unit_id, excluded.cashier_id,
     excluded.sold_at, excluded.shift, excluded.drug_name, excluded.manufacturer,
     excluded.drug_class, excluded.category, excluded.batch_and_expiry_date, excluded.quantity,
     excluded.unit_price, excluded.price_tier, excluded.discount_pct, excluded.discount_amount,
     excluded.service_fee, excluded.packaging_fee, excluded.subtotal, excluded.invoice_discount_pct,
     excluded.promo_discount_pct, excluded.tax_pct, excluded.additional_fee, excluded.total_price,
     excluded.payment_type, excluded.print_count, excluded.is_member, excluded.batch_id,
     excluded.shift_date, excluded.shift_period, excluded.shift_cashier_code, excluded.price_tier_number
 );
-- COMMAND 11 — reconcile sales payloads after upsert.
-- `matched` counts rows whose stored payload now equals the selected input payload.
UPDATE load_stats SET matched = (
 SELECT count(*) FROM candidate_sales n JOIN oltp.sales_line t USING (source_dataset, source_row_number)
 WHERE ROW(
     t.invoice_id, t.product_id, t.unit_id, t.cashier_id,
     t.sold_at, t.shift, t.drug_name, t.manufacturer,
     t.drug_class, t.category, t.batch_and_expiry_date, t.quantity,
     t.unit_price, t.price_tier, t.discount_pct, t.discount_amount,
     t.service_fee, t.packaging_fee, t.subtotal, t.invoice_discount_pct,
     t.promo_discount_pct, t.tax_pct, t.additional_fee, t.total_price,
     t.payment_type, t.print_count, t.is_member, t.batch_id,
     t.shift_date, t.shift_period, t.shift_cashier_code, t.price_tier_number
 ) IS NOT DISTINCT FROM ROW(
     n.invoice_id, n.product_id, n.unit_id, n.cashier_id,
     n.sold_at, n.shift, n.drug_name, n.manufacturer,
     n.drug_class, n.category, n.batch_and_expiry_date, n.quantity,
     n.unit_price, n.price_tier, n.discount_pct, n.discount_amount,
     n.service_fee, n.packaging_fee, n.subtotal, n.invoice_discount_pct,
     n.promo_discount_pct, n.tax_pct, n.additional_fee, n.total_price,
     n.payment_type, n.print_count, n.is_member, n.batch_id,
     n.shift_date, n.shift_period, n.shift_cashier_code, n.price_tier_number
 )
) WHERE dataset = 'sales';

-- COMMAND 12 — resolve each incoming stock row to its OLTP foreign keys.
-- Resolve document, product, warehouse, and all four units. A missing or ambiguous
-- reference is detected by the candidate-count check immediately after this query.
CREATE TEMP TABLE candidate_stock ON COMMIT DROP AS
SELECT
 current_setting('inventory.source_dataset') AS source_dataset,
 s."RowNumber"::bigint AS source_row_number,
 d.document_id AS document_id,
 p.product_id AS product_id,
 w.warehouse_id AS warehouse_id,
 s.event_datetime::timestamp AS occurred_at,
 s."DrugName" AS drug_name,
 NULLIF(s."DrugClass", '-') AS drug_class,
 NULLIF(s."Category", '-') AS category,
 s."DrugType" AS drug_type,
 s."Status" AS status,
 s."TransactionDescription" AS description,
 s.initial_stock_quantity::numeric AS initial_stock,
 s.stock_in_quantity::numeric AS stock_in,
 s.stock_out_quantity::numeric AS stock_out,
 s.remaining_stock_quantity::numeric AS remaining_stock,
 a.unit_id AS initial_unit_id,
 b.unit_id AS in_unit_id,
 c.unit_id AS out_unit_id,
 e.unit_id AS remaining_unit_id,
 s.transaction_type AS transaction_type,
 NULLIF(s.supplier_name, '') AS supplier_name,
 NULLIF(s.referenced_invoice_number, '') AS referenced_invoice_number,
 NULLIF(s.patient_code, '') AS patient_code
FROM incoming_stock s
JOIN oltp.inventory_document d ON d.document_number = s."DocumentNumber"
JOIN oltp.product p ON p.drug_code = s."DrugCode"
JOIN oltp.warehouse w ON w.warehouse_name = s."Warehouse"
JOIN oltp.unit a ON a.unit_code = s.initial_stock_unit
JOIN oltp.unit b ON b.unit_code = s.stock_in_unit
JOIN oltp.unit c ON c.unit_code = s.stock_out_unit
JOIN oltp.unit e ON e.unit_code = s.remaining_stock_unit;
DO $$ BEGIN
 IF (SELECT count(*) FROM incoming_stock) <> (SELECT count(*) FROM candidate_stock) THEN
  RAISE EXCEPTION 'stock: input rows lost or multiplied during FK resolution';
 END IF;
END $$;
-- COMMAND 13 — classify inventory rows before writing.
-- As for sales, compare all mapped payload fields to distinguish new, changed,
-- and unchanged movements under the `(source_dataset, source_row_number)` key.
INSERT INTO load_stats(dataset, rows_read, inserted, updated, unchanged)
SELECT 'stock', count(*), count(*) FILTER (WHERE t.movement_id IS NULL),
 count(*) FILTER (WHERE t.movement_id IS NOT NULL AND ROW(
     t.document_id, t.product_id, t.warehouse_id, t.occurred_at,
     t.drug_name, t.drug_class, t.category, t.drug_type,
     t.status, t.description, t.initial_stock, t.stock_in,
     t.stock_out, t.remaining_stock, t.initial_unit_id, t.in_unit_id,
     t.out_unit_id, t.remaining_unit_id, t.transaction_type, t.supplier_name,
     t.referenced_invoice_number, t.patient_code
 ) IS DISTINCT FROM ROW(
     n.document_id, n.product_id, n.warehouse_id, n.occurred_at,
     n.drug_name, n.drug_class, n.category, n.drug_type,
     n.status, n.description, n.initial_stock, n.stock_in,
     n.stock_out, n.remaining_stock, n.initial_unit_id, n.in_unit_id,
     n.out_unit_id, n.remaining_unit_id, n.transaction_type, n.supplier_name,
     n.referenced_invoice_number, n.patient_code
 )),
 count(*) FILTER (WHERE t.movement_id IS NOT NULL AND ROW(
     t.document_id, t.product_id, t.warehouse_id, t.occurred_at,
     t.drug_name, t.drug_class, t.category, t.drug_type,
     t.status, t.description, t.initial_stock, t.stock_in,
     t.stock_out, t.remaining_stock, t.initial_unit_id, t.in_unit_id,
     t.out_unit_id, t.remaining_unit_id, t.transaction_type, t.supplier_name,
     t.referenced_invoice_number, t.patient_code
 ) IS NOT DISTINCT FROM ROW(
     n.document_id, n.product_id, n.warehouse_id, n.occurred_at,
     n.drug_name, n.drug_class, n.category, n.drug_type,
     n.status, n.description, n.initial_stock, n.stock_in,
     n.stock_out, n.remaining_stock, n.initial_unit_id, n.in_unit_id,
     n.out_unit_id, n.remaining_unit_id, n.transaction_type, n.supplier_name,
     n.referenced_invoice_number, n.patient_code
 ))
FROM candidate_stock n
LEFT JOIN oltp.inventory_movement t USING (source_dataset, source_row_number);

-- COMMAND 14 — insert new movements or update changed movements.
-- Keep movement_id stable on conflict and skip writes when all mapped values match.
INSERT INTO oltp.inventory_movement AS t (
 source_dataset, source_row_number, document_id, product_id,
 warehouse_id, occurred_at, drug_name, drug_class,
 category, drug_type, status, description,
 initial_stock, stock_in, stock_out, remaining_stock,
 initial_unit_id, in_unit_id, out_unit_id, remaining_unit_id,
 transaction_type, supplier_name, referenced_invoice_number, patient_code
)
SELECT
 source_dataset, source_row_number, document_id, product_id,
 warehouse_id, occurred_at, drug_name, drug_class,
 category, drug_type, status, description,
 initial_stock, stock_in, stock_out, remaining_stock,
 initial_unit_id, in_unit_id, out_unit_id, remaining_unit_id,
 transaction_type, supplier_name, referenced_invoice_number, patient_code
 FROM candidate_stock
ON CONFLICT (source_dataset, source_row_number) DO UPDATE SET
 document_id = excluded.document_id,
 product_id = excluded.product_id,
 warehouse_id = excluded.warehouse_id,
 occurred_at = excluded.occurred_at,
 drug_name = excluded.drug_name,
 drug_class = excluded.drug_class,
 category = excluded.category,
 drug_type = excluded.drug_type,
 status = excluded.status,
 description = excluded.description,
 initial_stock = excluded.initial_stock,
 stock_in = excluded.stock_in,
 stock_out = excluded.stock_out,
 remaining_stock = excluded.remaining_stock,
 initial_unit_id = excluded.initial_unit_id,
 in_unit_id = excluded.in_unit_id,
 out_unit_id = excluded.out_unit_id,
 remaining_unit_id = excluded.remaining_unit_id,
 transaction_type = excluded.transaction_type,
 supplier_name = excluded.supplier_name,
 referenced_invoice_number = excluded.referenced_invoice_number,
 patient_code = excluded.patient_code
WHERE ROW(
     t.document_id, t.product_id, t.warehouse_id, t.occurred_at,
     t.drug_name, t.drug_class, t.category, t.drug_type,
     t.status, t.description, t.initial_stock, t.stock_in,
     t.stock_out, t.remaining_stock, t.initial_unit_id, t.in_unit_id,
     t.out_unit_id, t.remaining_unit_id, t.transaction_type, t.supplier_name,
     t.referenced_invoice_number, t.patient_code
 ) IS DISTINCT FROM ROW(
     excluded.document_id, excluded.product_id, excluded.warehouse_id, excluded.occurred_at,
     excluded.drug_name, excluded.drug_class, excluded.category, excluded.drug_type,
     excluded.status, excluded.description, excluded.initial_stock, excluded.stock_in,
     excluded.stock_out, excluded.remaining_stock, excluded.initial_unit_id, excluded.in_unit_id,
     excluded.out_unit_id, excluded.remaining_unit_id, excluded.transaction_type, excluded.supplier_name,
     excluded.referenced_invoice_number, excluded.patient_code
 );
-- COMMAND 15 — reconcile inventory payloads after upsert.
UPDATE load_stats SET matched = (
 SELECT count(*) FROM candidate_stock n JOIN oltp.inventory_movement t USING (source_dataset, source_row_number)
 WHERE ROW(
     t.document_id, t.product_id, t.warehouse_id, t.occurred_at,
     t.drug_name, t.drug_class, t.category, t.drug_type,
     t.status, t.description, t.initial_stock, t.stock_in,
     t.stock_out, t.remaining_stock, t.initial_unit_id, t.in_unit_id,
     t.out_unit_id, t.remaining_unit_id, t.transaction_type, t.supplier_name,
     t.referenced_invoice_number, t.patient_code
 ) IS NOT DISTINCT FROM ROW(
     n.document_id, n.product_id, n.warehouse_id, n.occurred_at,
     n.drug_name, n.drug_class, n.category, n.drug_type,
     n.status, n.description, n.initial_stock, n.stock_in,
     n.stock_out, n.remaining_stock, n.initial_unit_id, n.in_unit_id,
     n.out_unit_id, n.remaining_unit_id, n.transaction_type, n.supplier_name,
     n.referenced_invoice_number, n.patient_code
 )
) WHERE dataset = 'stock';

-- COMMAND 16 — enforce final reconciliation.
-- Every selected row must match a target row, and the classified totals must equal
-- rows read. Failure raises an exception and rolls back the complete load.
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM load_stats WHERE rows_read <> matched
 OR rows_read <> inserted + updated + unchanged) THEN
  RAISE EXCEPTION 'Post-upsert reconciliation failed';
 END IF;
END $$;

-- COMMAND 17 — return the machine-readable receipt to the Python loader.
-- Dataset statistics describe only this run; totals describe the complete target
-- tables after upsert. Python persists the receipt as a JSON report.
SELECT json_build_object(
 'datasets', (SELECT json_object_agg(dataset, json_build_object('rows_read', rows_read,
 'inserted', inserted, 'updated', updated, 'unchanged', unchanged, 'matched', matched)) FROM load_stats),
 'totals', json_build_object(
 'sales_lines', (SELECT count(*) FROM oltp.sales_line),
 'inventory_movements', (SELECT count(*) FROM oltp.inventory_movement),
 'products', (SELECT count(*) FROM oltp.product),
 'batches', (SELECT count(*) FROM oltp.product_batch),
 'invoices', (SELECT count(*) FROM oltp.sales_invoice),
 'warehouses', (SELECT count(*) FROM oltp.warehouse))
);
