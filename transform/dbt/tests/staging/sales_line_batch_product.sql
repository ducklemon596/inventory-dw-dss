-- =============================================================================
-- DATA QUALITY: Sales line batch product
-- =============================================================================
-- Composite FK: a non-null batch must belong to the line's product.

-- Records returned by this query represent integrity violations.
select sales_invoice_line_id, product_batch_id, product_id
from {{ ref('stg_sales_invoice_lines') }} as line
where product_batch_id is not null
  and (product_batch_id, product_id) not in (
      select product_batch_id, product_id from {{ ref('stg_product_batches') }}
  )
