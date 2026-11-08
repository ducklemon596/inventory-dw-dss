# Mart contract regression

Entry points: `integration.py`.

The integration script copies the required Dimensions and three sales fixture rows (approved, candidate and unverified stock-unit evidence) into a disposable database, runs compiled dbt checks, then injects missing parents, duplicate Dimension fan-out, source-key collisions, missing/duplicate special members, invalid stock-unit FK substitutions, unresolved quantity NULL-to-zero replacement and an extra warehouse field. Exact source preservation permits only the declared stock-unit FK representation change.

```bash
uv run --locked python tests/marts/integration.py
```

Run the pinned full dbt build first. The script expects current approved/candidate fixture availability and exactly compiled YAML tests. It proves those faults are detected, not every possible source mutation.

[Complete test order and acceptance](../README.md) explains required services, version pinning, compiled artifacts and generated logs. Unit tests need no databases; integration scripts use only their documented read-only/disposable scope.
