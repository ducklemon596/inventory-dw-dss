-- =============================================================================
-- DATA QUALITY: Product batch natural key
-- =============================================================================
-- Matches PostgreSQL UNIQUE NULLS NOT DISTINCT, including absent expiry dates.

-- Records returned by this query represent integrity violations.
select product_id, product_batch_number, expiration_date, count() as row_count
from {{ ref('stg_product_batches') }}
group by product_id, product_batch_number, expiration_date

-- Return only failing groups.
having count() > 1
