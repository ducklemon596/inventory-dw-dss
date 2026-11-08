-- =============================================================================
-- DATA QUALITY: Sales dates and optional batch relationships
-- =============================================================================
select line.sales_invoice_line_id
from {{ ref('int_sales_lines_enriched') }} as line
left join {{ ref('stg_product_batches') }} as batch
    on line.product_batch_id = batch.product_batch_id
where line.sold_date != toDate32(line.sold_at)
    or (line.product_batch_id is null
        and (line.product_batch_number is not null or line.expiration_date is not null))
    or (line.product_batch_id is not null
        and (batch.product_batch_id is null or line.product_id != batch.product_id))
settings join_use_nulls = 1
