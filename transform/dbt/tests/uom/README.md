# UOM governance and conversion

Tests enforce selected version existence, published counts/domains, unique version/code/unit pairs, compatible verified stock targets, approved-only arithmetic, exact quantity preservation and exhaustive coverage partitions. Unit fixtures check statuses, exact signed decimals, version isolation and cross-warehouse evidence.

**Failure interpretation:** Check version pin and immutable source, then exact business-code/unit match and stock evidence. Candidate/quarantined numeric evidence is not authorization. A new version needs explicit reviewed publication contracts.

```bash
uv run --locked inventory-dw-dss transform --test --select int_sales_quantity_converted int_product_stock_units int_sales_uom_coverage
```

Build required inputs first. See the [test guide](../README.md) for selection and failure diagnosis; field contracts and native fixtures live beside [the models](../../models/README.md).
