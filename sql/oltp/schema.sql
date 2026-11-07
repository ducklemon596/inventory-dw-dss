-- OLTP SCHEMA SETUP
-- =================
-- Purpose: create the current OLTP model on a fresh database and bring an older
-- installation forward without dropping tables, rows, or identity values.
-- Execution: loaded by the Python loader inside the same transaction as each upsert.
-- Idempotency: CREATE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS and guarded
-- constraints make repeat execution safe. Do not run load.sql before this file.

-- COMMAND 01 — create namespaces and compatibility metadata.
-- `staging` contains loader support objects; `oltp` contains operational entities.
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS oltp;
-- Preserve the old version/checksum ledger for existing installations. The active
-- loader does not execute migration files; one embedded backfill marker is used below.
CREATE TABLE IF NOT EXISTS staging.schema_migration (
 version text PRIMARY KEY, sha256 text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now()
);

-- COMMAND 02 — create product catalog entities.
-- These lookup tables are shared by products; product foreign keys remain nullable
-- because the source does not provide every label for every product.
CREATE TABLE IF NOT EXISTS oltp.manufacturer (
 manufacturer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 manufacturer_name text NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS oltp.drug_class (
 drug_class_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 drug_class_name text NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS oltp.category (
 category_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 category_name text NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS oltp.product (
 product_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 drug_code text NOT NULL UNIQUE,
 drug_name text,
 manufacturer_id bigint REFERENCES oltp.manufacturer,
 drug_class_id bigint REFERENCES oltp.drug_class,
 category_id bigint REFERENCES oltp.category
);
-- Upgrade columns individually because CREATE TABLE IF NOT EXISTS does not alter
-- a product table created by an older schema version.
ALTER TABLE oltp.product ADD COLUMN IF NOT EXISTS drug_name text;
ALTER TABLE oltp.product ADD COLUMN IF NOT EXISTS manufacturer_id bigint;
ALTER TABLE oltp.product ADD COLUMN IF NOT EXISTS drug_class_id bigint;
ALTER TABLE oltp.product ADD COLUMN IF NOT EXISTS category_id bigint;
-- Add missing lookup FKs without duplicating constraints already present on a
-- database that has previously received the catalog model.
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='oltp.product'::regclass AND conname='product_manufacturer_id_fkey') THEN
  ALTER TABLE oltp.product ADD CONSTRAINT product_manufacturer_id_fkey FOREIGN KEY (manufacturer_id) REFERENCES oltp.manufacturer;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='oltp.product'::regclass AND conname='product_drug_class_id_fkey') THEN
  ALTER TABLE oltp.product ADD CONSTRAINT product_drug_class_id_fkey FOREIGN KEY (drug_class_id) REFERENCES oltp.drug_class;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='oltp.product'::regclass AND conname='product_category_id_fkey') THEN
  ALTER TABLE oltp.product ADD CONSTRAINT product_category_id_fkey FOREIGN KEY (category_id) REFERENCES oltp.category;
 END IF;
END $$;

-- COMMAND 03 — create shared warehouse, unit, and cashier identities.
-- Natural source codes/names are unique; generated IDs are internal FK targets.
CREATE TABLE IF NOT EXISTS oltp.warehouse (
 warehouse_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 warehouse_name text NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS oltp.unit (
 unit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 unit_code text NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS oltp.cashier (
 cashier_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 source_code text NOT NULL UNIQUE
);

-- COMMAND 04 — create sales headers, product batches, and source lines.
-- A batch belongs to one product. NULL expiry dates participate in the natural
-- key as a single value, so the same product/batch without expiry is not duplicated.
CREATE TABLE IF NOT EXISTS oltp.sales_invoice (
 invoice_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 invoice_number text NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS oltp.product_batch (
 batch_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 product_id bigint NOT NULL REFERENCES oltp.product,
 batch_number text NOT NULL,
 expiry_date date,
 CONSTRAINT product_batch_natural_key UNIQUE NULLS NOT DISTINCT (product_id, batch_number, expiry_date),
 CONSTRAINT product_batch_product_key UNIQUE (batch_id, product_id)
);
CREATE TABLE IF NOT EXISTS oltp.sales_line (
 sales_line_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 source_dataset text NOT NULL DEFAULT 'pharmacy_2023_2025',
 source_row_number bigint NOT NULL,
 invoice_id bigint NOT NULL REFERENCES oltp.sales_invoice,
 product_id bigint NOT NULL REFERENCES oltp.product,
 unit_id bigint NOT NULL REFERENCES oltp.unit,
 cashier_id bigint NOT NULL REFERENCES oltp.cashier,
 sold_at timestamp NOT NULL,
 shift text,
 drug_name text NOT NULL,
 manufacturer text, drug_class text, category text,
 batch_and_expiry_date text,
 quantity numeric NOT NULL, unit_price numeric NOT NULL,
 price_tier text, discount_pct numeric, discount_amount numeric,
 service_fee numeric, packaging_fee numeric, subtotal numeric,
 invoice_discount_pct numeric, promo_discount_pct numeric,
 tax_pct numeric, additional_fee numeric, total_price numeric,
 payment_type text, print_count integer,
 is_member text,
 batch_id bigint,
 shift_date date,
 shift_period text,
 shift_cashier_code text,
 price_tier_number integer,
 CONSTRAINT sales_line_source_key UNIQUE (source_dataset, source_row_number),
 CONSTRAINT sales_line_batch_product_fk FOREIGN KEY (batch_id, product_id)
  REFERENCES oltp.product_batch (batch_id, product_id)
);
-- Upgrade fields introduced for source namespacing, parsed shift data, batches,
-- and price tiers while leaving all pre-existing sales rows and PKs intact.
ALTER TABLE oltp.sales_line ADD COLUMN IF NOT EXISTS source_dataset text NOT NULL DEFAULT 'pharmacy_2023_2025';
ALTER TABLE oltp.sales_line ADD COLUMN IF NOT EXISTS batch_id bigint;
ALTER TABLE oltp.sales_line ADD COLUMN IF NOT EXISTS shift_date date;
ALTER TABLE oltp.sales_line ADD COLUMN IF NOT EXISTS shift_period text;
ALTER TABLE oltp.sales_line ADD COLUMN IF NOT EXISTS shift_cashier_code text;
ALTER TABLE oltp.sales_line ADD COLUMN IF NOT EXISTS price_tier_number integer;
-- Replace the former RowNumber-only uniqueness with the scoped natural key. This
-- permits independent source datasets to reuse a RowNumber.
ALTER TABLE oltp.sales_line DROP CONSTRAINT IF EXISTS sales_line_source_row_number_key;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='oltp.sales_line'::regclass AND conname='sales_line_source_key') THEN
  ALTER TABLE oltp.sales_line ADD CONSTRAINT sales_line_source_key UNIQUE (source_dataset, source_row_number);
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='oltp.sales_line'::regclass AND conname='sales_line_batch_product_fk') THEN
  ALTER TABLE oltp.sales_line ADD CONSTRAINT sales_line_batch_product_fk FOREIGN KEY (batch_id, product_id)
   REFERENCES oltp.product_batch (batch_id, product_id);
 END IF;
END $$;

-- COMMAND 05 — create inventory headers and source movements.
-- A movement stores the source snapshot and its four quantity-unit pairs. It is
-- deliberately not linked to a sales batch because the source does not establish
-- a reliable movement-to-sale batch relationship.
CREATE TABLE IF NOT EXISTS oltp.inventory_document (
 document_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 document_number text NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS oltp.inventory_movement (
 movement_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 source_dataset text NOT NULL DEFAULT 'pharmacy_2023_2025',
 source_row_number bigint NOT NULL,
 document_id bigint NOT NULL REFERENCES oltp.inventory_document,
 product_id bigint NOT NULL REFERENCES oltp.product,
 warehouse_id bigint NOT NULL REFERENCES oltp.warehouse,
 occurred_at timestamp NOT NULL,
 drug_name text NOT NULL, drug_class text, category text,
 drug_type text, status text, description text,
 initial_stock numeric NOT NULL, stock_in numeric NOT NULL,
 stock_out numeric NOT NULL, remaining_stock numeric NOT NULL,
 initial_unit_id bigint NOT NULL REFERENCES oltp.unit,
 in_unit_id bigint NOT NULL REFERENCES oltp.unit,
 out_unit_id bigint NOT NULL REFERENCES oltp.unit,
 remaining_unit_id bigint NOT NULL REFERENCES oltp.unit,
 transaction_type text,
 supplier_name text,
 referenced_invoice_number text,
 patient_code text,
 CONSTRAINT inventory_movement_source_key UNIQUE (source_dataset, source_row_number)
);
-- Add fields from the parsed transaction description and source namespace when
-- upgrading a database created before those columns existed.
ALTER TABLE oltp.inventory_movement ADD COLUMN IF NOT EXISTS source_dataset text NOT NULL DEFAULT 'pharmacy_2023_2025';
ALTER TABLE oltp.inventory_movement ADD COLUMN IF NOT EXISTS transaction_type text;
ALTER TABLE oltp.inventory_movement ADD COLUMN IF NOT EXISTS supplier_name text;
ALTER TABLE oltp.inventory_movement ADD COLUMN IF NOT EXISTS referenced_invoice_number text;
ALTER TABLE oltp.inventory_movement ADD COLUMN IF NOT EXISTS patient_code text;
-- Match sales-line idempotency: preserve the surrogate movement ID, but scope the
-- source-row key by dataset.
ALTER TABLE oltp.inventory_movement DROP CONSTRAINT IF EXISTS inventory_movement_source_row_number_key;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='oltp.inventory_movement'::regclass AND conname='inventory_movement_source_key') THEN
  ALTER TABLE oltp.inventory_movement ADD CONSTRAINT inventory_movement_source_key UNIQUE (source_dataset, source_row_number);
 END IF;
END $$;

-- COMMAND 06 — perform the one-time product-catalog backfill for older databases.
-- This reads labels already stored on transaction lines. It is skipped when the
-- former catalog migration or this consolidated backfill marker is present.
-- Conflicting labels for one DrugCode stop the schema transaction instead of
-- selecting an arbitrary value. Transaction-level snapshots are not modified.
CREATE TEMP TABLE catalog_observation ON COMMIT DROP AS
SELECT p.drug_code, NULLIF(btrim(l.drug_name),'') AS drug_name,
 NULLIF(NULLIF(btrim(l.manufacturer),'-'),'') AS manufacturer,
 NULLIF(NULLIF(btrim(l.drug_class),'-'),'') AS drug_class,
 NULLIF(NULLIF(btrim(l.category),'-'),'') AS category
FROM oltp.sales_line l JOIN oltp.product p USING(product_id)
WHERE NOT EXISTS (SELECT 1 FROM staging.schema_migration WHERE version IN ('004_product_catalog.sql','consolidated_catalog_backfill'))
UNION
SELECT p.drug_code, NULLIF(btrim(l.drug_name),''), NULL::text,
 NULLIF(NULLIF(btrim(l.drug_class),'-'),''), NULLIF(NULLIF(btrim(l.category),'-'),'')
FROM oltp.inventory_movement l JOIN oltp.product p USING(product_id)
WHERE NOT EXISTS (SELECT 1 FROM staging.schema_migration WHERE version IN ('004_product_catalog.sql','consolidated_catalog_backfill'));

DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM catalog_observation GROUP BY drug_code HAVING
  count(DISTINCT drug_name)>1 OR count(DISTINCT manufacturer)>1 OR
  count(DISTINCT drug_class)>1 OR count(DISTINCT category)>1) THEN
  RAISE EXCEPTION 'Conflicting product attributes; resolve source data before loading';
 END IF;
END $$;
-- Insert distinct reference labels before assigning their generated IDs.
INSERT INTO oltp.manufacturer(manufacturer_name)
SELECT DISTINCT manufacturer FROM catalog_observation WHERE manufacturer IS NOT NULL ON CONFLICT DO NOTHING;
INSERT INTO oltp.drug_class(drug_class_name)
SELECT DISTINCT drug_class FROM catalog_observation WHERE drug_class IS NOT NULL ON CONFLICT DO NOTHING;
INSERT INTO oltp.category(category_name)
SELECT DISTINCT category FROM catalog_observation WHERE category IS NOT NULL ON CONFLICT DO NOTHING;
-- Resolve each product's nullable catalog FKs from the validated source labels.
-- The IS DISTINCT FROM guard avoids writing rows whose values already match.
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
 AND ROW(p.drug_name,p.manufacturer_id,p.drug_class_id,p.category_id)
  IS DISTINCT FROM ROW(a.drug_name,m.manufacturer_id,d.drug_class_id,c.category_id);
DROP TABLE catalog_observation;
-- Record completion in the same transaction: a failure rolls back both the
-- backfill and marker, allowing a later load to retry safely.
INSERT INTO staging.schema_migration(version,sha256)
VALUES ('consolidated_catalog_backfill','embedded-in-schema') ON CONFLICT DO NOTHING;
