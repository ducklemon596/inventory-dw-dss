with expected as (
    select
        products.product_id,
        manufacturers.manufacturer_name,
        drug_classes.drug_class_name,
        categories.category_name
    from {{ ref('stg_products') }} as products
    left join {{ ref('stg_manufacturers') }} as manufacturers
        on products.manufacturer_id = manufacturers.manufacturer_id
    left join {{ ref('stg_drug_classes') }} as drug_classes
        on products.drug_class_id = drug_classes.drug_class_id
    left join {{ ref('stg_categories') }} as categories
        on products.category_id = categories.category_id
)
select coalesce(expected.product_id, actual.product_id) as product_id
from expected
full outer join {{ ref('dim_product') }} as actual on expected.product_id = actual.product_id
where expected.product_id is null or actual.product_id is null
{% for column in ['manufacturer_name', 'drug_class_name', 'category_name'] %}
    or isNull(expected.{{ column }}) != isNull(actual.{{ column }})
    or ifNull(expected.{{ column }} != actual.{{ column }}, false)
{% endfor %}
settings join_use_nulls = 1
