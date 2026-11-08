# Governed UOM seed

[uom_conversion_mapping.csv](uom_conversion_mapping.csv) is the exact union of immutable published mapping snapshots: 190 v1 rows and 207 v2 rows, **397 total**. It is not transaction input. [_uom.yml](_uom.yml) defines the complete column schema and seed key; [UOM tests](../tests/uom/README.md) enforce publication and domain rules; `dbt_project.yml` fixes column types for loading.

**Key:** `(mapping_version,product_id,sales_unit)`. The seed field `product_id` means POS **DrugCode**, not the numeric OLTP product key. Joins use exact code and unit labels. Factor/evidence decimals must retain supplied precision.

Only Tier A + approved + positive factor + compatible verified stock target authorizes conversion. Tier B candidates and Tier C quarantined values remain evidence; their numeric candidates never authorize arithmetic. The version is pinned during builds and compiled into the conversion view.

```bash
uv run --locked inventory-dw-dss transform --select uom_conversion_mapping+
uv run --locked python -m unittest discover -s tests/uom -v
```

This targeted build assumes compatible existing upstream views/Dimensions. Use a full build for initial setup or acceptance. Source snapshots, checksums and publishing instructions live in [reference UOM](../../../data/reference/uom/README.md) and [quantity semantics](../../../docs/data-semantics.md). Never overwrite published snapshots or silently edit existing seed version rows. Keep readers paused during seed reset/build; seed load is not a multi-model atomic release.
