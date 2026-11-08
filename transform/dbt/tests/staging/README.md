# Staging validation

`normalized_values` reads every projection to exercise optional casts and string guards; source counts detect lost/duplicated rows. Source-key tests and batch/product natural/association checks protect identity and optional batch correctness. Declared not-null, unique and relationship tests complement these checks.

**Failure interpretation:** Investigate the raw value and source PK first. Parser failures should remain visible; a missing optional value is different from malformed nonempty text.

```bash
uv run --locked inventory-dw-dss transform --test --select staging
```

Build required inputs first. See the [test guide](../README.md) for selection and failure diagnosis; field contracts and native fixtures live beside [the models](../../models/README.md).
