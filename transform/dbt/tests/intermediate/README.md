# Intermediate reconciliation

Sales tests compare enrichment and original-unit daily grouping with source rows. Inventory tests check opening + received - issued = closing, exact predecessor identity/sequence/units, segment anchors/ranges/cumulative reconstruction and complete discontinuity diagnostics. Generic preservation compares all parent fields, including NULL distinctions.

**Failure interpretation:** Inspect the exact dataset/product/warehouse ledger in source order. A real discontinuity is retained, not automatically repaired. An arithmetic/preservation failure is different from an expected gap flag.

```bash
uv run --locked inventory-dw-dss transform --test --select int_inventory_segments int_sales_lines_enriched
```

Build required inputs first. See the [test guide](../README.md) for selection and failure diagnosis; field contracts and native fixtures live beside [the models](../../models/README.md).
