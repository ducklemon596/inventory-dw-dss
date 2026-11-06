CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS oltp;
CREATE TABLE IF NOT EXISTS staging.sales_raw (
"RowNumber" text,
"DateTime" text,
"Shift" text,
"CashierID" text,
"InvoiceNumber" text,
"Manufacturer" text,
"DrugClass" text,
"Category" text,
"DrugCode" text,
"DrugName" text,
"BatchAndExpiryDate" text,
"PrescriptionNumber" text,
"PatientID" text,
"DoctorID" text,
"SalespersonID" text,
"Quantity" text,
"Unit" text,
"PriceTier" text,
"UnitPrice" text,
"SalesPromo" text,
"PromoName" text,
"DiscountPct" text,
"DiscountAmount" text,
"ServiceFee" text,
"PackagingFee" text,
"TaxInvoiceNumber" text,
"Subtotal" text,
"InvoiceDiscountPct" text,
"IsMember" text,
"PromoDiscountPct" text,
"TaxAmount" text,
"AdditionalFee" text,
"PaymentType" text,
"PrintCount" text,
"TotalPrice" text
);
CREATE TABLE IF NOT EXISTS staging.stock_raw (
"RowNumber" text,
"DateTime" text,
"Warehouse" text,
"DrugCode" text,
"DrugName" text,
"DocumentNumber" text,
"TransactionDescription" text,
"InitialStock" text,
"StockIn" text,
"StockOut" text,
"RemainingStock" text,
"DrugClass" text,
"Category" text,
"DrugType" text,
"Status" text
);

CREATE OR REPLACE FUNCTION staging.number_value(value text) RETURNS numeric
LANGUAGE sql IMMUTABLE STRICT AS $$
 SELECT NULLIF(replace(trim(value), ',', '.'), '')::numeric
$$;
CREATE OR REPLACE FUNCTION staging.stock_quantity(value text) RETURNS numeric
LANGUAGE sql IMMUTABLE STRICT AS $$
 SELECT replace(replace(substring(trim(value) from '^[-+0-9.,]+'), '.', ''), ',', '.')::numeric
$$;
CREATE OR REPLACE FUNCTION staging.stock_unit(value text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT AS $$
 SELECT NULLIF(trim(regexp_replace(trim(value), '^[-+0-9.,]+', '')), '')
$$;
CREATE TABLE IF NOT EXISTS oltp.product (
 product_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 drug_code text NOT NULL UNIQUE
);
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
CREATE TABLE IF NOT EXISTS oltp.sales_invoice (
 invoice_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 invoice_number text NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS oltp.sales_line (
 sales_line_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 source_row_number bigint NOT NULL UNIQUE,
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
 is_member text
);
CREATE TABLE IF NOT EXISTS oltp.inventory_document (
 document_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 document_number text NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS oltp.inventory_movement (
 movement_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 source_row_number bigint NOT NULL UNIQUE,
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
 remaining_unit_id bigint NOT NULL REFERENCES oltp.unit
);
