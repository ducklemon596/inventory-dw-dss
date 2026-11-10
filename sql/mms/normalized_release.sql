-- Data-owner setup only. MMS application queries never execute this DDL.
-- Run in the chosen MMS database; publish a NEW immutable release, never mutate
-- an existing release or replace observed-closing balances with available stock.
CREATE TABLE IF NOT EXISTS mms_release_metadata (
    release_id String,
    schema_version String,
    data_version String,
    location_scope String,
    available_stock_verified UInt8 DEFAULT 0,
    daily_sales_verified UInt8 DEFAULT 0,
    units_verified UInt8 DEFAULT 0,
    sop_rules_verified UInt8 DEFAULT 0,
    approved_by String,
    approval_reference String,
    outcome_version String DEFAULT '',
    data_cutoff Nullable(Date)
) ENGINE = MergeTree ORDER BY release_id;

CREATE TABLE IF NOT EXISTS mms_inventory_daily (
    release_id String,
    analysis_date Date,
    sku_id String,
    available_stock Float64,
    stock_unit String,
    location_scope String,
    snapshot_version String,
    data_version String,
    feature_as_of Date,
    eligible UInt8,
    features String DEFAULT '{}',
    days_since_last_receipt Nullable(UInt32),
    flags Array(String),
    observed_stockout_days Nullable(UInt16),
    diagnostic_observed_days Nullable(UInt16),
    CONSTRAINT eligible_boolean CHECK eligible IN (0,1)
) ENGINE = MergeTree ORDER BY (release_id, analysis_date, sku_id);

CREATE TABLE IF NOT EXISTS mms_sales_daily (
    release_id String,
    sku_id String,
    sales_date Date,
    quantity Float64,
    revenue Nullable(Float64)
) ENGINE = MergeTree ORDER BY (release_id, sales_date, sku_id);

CREATE TABLE IF NOT EXISTS mms_outcomes_daily (
    release_id String,
    observation_date Date,
    sku_id String,
    sales_quantity Float64,
    stockout UInt8,
    received_quantity Float64,
    sop_day UInt8,
    CONSTRAINT stockout_boolean CHECK stockout IN (0,1),
    CONSTRAINT sop_boolean CHECK sop_day IN (0,1)
) ENGINE = MergeTree ORDER BY (release_id, observation_date, sku_id);
