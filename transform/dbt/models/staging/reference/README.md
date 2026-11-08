# Reference staging

These seven views expose the current source catalogs. Each reads one raw table, normalizes its fields through `cleaned`, then returns one typed record per source identity. IDs retain their source association; optional product classifications remain missing when absent.

| Model / purpose | Raw input | Grain and output fields | Direct model consumers |
|---|---|---|---|
| [stg_products](stg_products.sql): shared pharmacy product catalog | `product` | One `product_id`; `product_code`, `product_name`, `manufacturer_id`, `drug_class_id`, `category_id` | `dim_product`, `int_sales_lines_enriched`, `int_inventory_movements_enriched`, `int_product_stock_units` |
| [stg_manufacturers](stg_manufacturers.sql): manufacturer lookup | `manufacturer` | One `manufacturer_id`; `manufacturer_name` | `dim_product` |
| [stg_drug_classes](stg_drug_classes.sql): source drug classifications | `drug_class` | One `drug_class_id`; `drug_class_name` | `dim_product` |
| [stg_categories](stg_categories.sql): merchandise categories | `category` | One `category_id`; `category_name` | `dim_product` |
| [stg_warehouses](stg_warehouses.sql): recorded inventory locations | `warehouse` | One `warehouse_id`; `warehouse_name` | `dim_warehouse`, `int_inventory_movements_enriched` |
| [stg_units](stg_units.sql): original unit labels | `unit` | One `unit_id`; `unit_code` | `dim_unit`, `int_sales_lines_enriched`, `int_inventory_movements_enriched`, `int_product_stock_units` |
| [stg_cashiers](stg_cashiers.sql): pseudonymous cashier lookup | `cashier` | One `cashier_id`; `cashier_code` | `int_sales_lines_enriched` |

Product `drug_code` is renamed to `product_code`; numeric `product_id` remains a separate identity. Cashier `source_code` becomes `cashier_code`. Manufacturer, class and category IDs on a product remain optional. Classification labels are independent catalogs, and unit labels such as Box and Tab do not carry an implicit conversion factor.

A sale of product code P keeps the product name recorded on that sale when it is enriched. Joining `dim_product` later provides P's current catalog name. This distinction lets consumers choose the appropriate meaning without rewriting past descriptions.

See the shared [Staging guide](../README.md) for execution and parser rules, and [_staging.yml](../_staging.yml) for every output field/type/test. A catalog label change affects dimensions or enrichments that read it. Check lookup uniqueness before editing joins downstream; an arbitrary duplicate parent can multiply transaction rows.
