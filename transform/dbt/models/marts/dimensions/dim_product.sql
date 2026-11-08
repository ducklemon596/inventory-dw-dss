-- Current catalog attributes; transaction-recorded labels remain in the facts.
{{ config(materialized='table', engine='MergeTree()', order_by='product_id') }}

select
    products.product_id as product_id,
    products.product_code as product_code,
    products.product_name as product_name,
    products.manufacturer_id as manufacturer_id,
    manufacturers.manufacturer_name as manufacturer_name,
    products.drug_class_id as drug_class_id,
    drug_classes.drug_class_name as drug_class_name,
    products.category_id as category_id,
    categories.category_name as category_name
from {{ ref('stg_products') }} as products
left join {{ ref('stg_manufacturers') }} as manufacturers
    on products.manufacturer_id = manufacturers.manufacturer_id
left join {{ ref('stg_drug_classes') }} as drug_classes
    on products.drug_class_id = drug_classes.drug_class_id
left join {{ ref('stg_categories') }} as categories
    on products.category_id = categories.category_id
