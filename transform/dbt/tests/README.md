# dbt tests

Tests are the executable warehouse contract. A singular SQL test returns failures; no returned rows means pass. Generic tests are macros invoked by YAML; native unit tests use supplied small fixtures to check model behavior. The full build runs all selected models/seed and their tests.

| Folder | Main safeguards |
|---|---|
| [staging](staging/README.md) | Strict normalization, source row/key coverage and batch association |
| [intermediate](intermediate/README.md) | Enrichment, balance, predecessor ordering, anchors and segment arithmetic |
| [uom](uom/README.md) | Published versions, approval/target compatibility, conversion and coverage |
| [marts](marts/README.md) | Daily observation selection, calendar/product labels and sales semantics |
| [generic](generic/README.md) | Reusable grain, preservation, schema and JOIN cardinality |

Column not-null/unique/relationship checks are declared beside model schemas. Unit fixtures live beside relevant models in `_unit_tests.yml` / `_uom_unit_tests.yml`, not in this directory. [The complete test guide](../../../tests/README.md) has Python and acceptance commands.

```bash
uv run --locked inventory-dw-dss transform --test --select fct_sales_line
uv run --locked inventory-dw-dss transform
```

A selected test can reference multiple models; ensure all inputs exist and reflect one accepted state. Inspect failing row keys and compiled SQL before editing a rule. Passing compile or a row-count-only check does not prove field-level correctness. Never convert missing/invalid values to zero to silence tests.

Inspect returned failing keys and SQL under `target/compiled/inventory_dw/` in the dbt project. A model selection includes its attached tests; cross-model checks can also read unselected relations. Use the complete build for acceptance after targeted changes.
