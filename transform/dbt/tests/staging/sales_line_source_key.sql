-- =============================================================================
-- DATA QUALITY: Sales line source key
-- =============================================================================
-- Record numbers are unique within each transaction dataset.

-- Records returned by this query represent integrity violations.
select dataset_name, dataset_row_number, count() as row_count
from {{ ref('stg_sales_invoice_lines') }}
group by dataset_name, dataset_row_number

-- Return only failing groups.
having count() > 1
