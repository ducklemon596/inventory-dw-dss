-- Current Type 1 catalog labels enrich product identity; transaction-recorded labels remain in the facts.
-- Optional classifications remain missing through LEFT JOINs.
{{ config(
    materialized='table',
    engine='MergeTree()',
    order_by='product_id'
) }}

SELECT
    products.product_id AS product_id,
    products.product_code AS product_code,
    products.product_name AS product_name,
    products.manufacturer_id AS manufacturer_id,
    manufacturers.manufacturer_name AS manufacturer_name,
    products.drug_class_id AS drug_class_id,
    drug_classes.drug_class_name AS drug_class_name,
    products.category_id AS category_id,
    categories.category_name AS category_name
FROM {{ ref('stg_products') }} AS products
LEFT JOIN {{ ref('stg_manufacturers') }} AS manufacturers
    ON products.manufacturer_id = manufacturers.manufacturer_id
LEFT JOIN {{ ref('stg_drug_classes') }} AS drug_classes
    ON products.drug_class_id = drug_classes.drug_class_id
LEFT JOIN {{ ref('stg_categories') }} AS categories
    ON products.category_id = categories.category_id
