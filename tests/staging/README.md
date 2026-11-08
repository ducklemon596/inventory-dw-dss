# Normalization edge cases

Entry points: `integration.py`.

The script reads compiled normalization macros and evaluates 52 ClickHouse cases, including valid missing values, malformed/overflow IDs and decimals, timestamps, dates, domains and optional values that must raise instead of silently becoming NULL. Its case evaluation uses SELECT queries; the temporary dbt compile can also perform adapter connection probes.

```bash
uv run --locked python tests/staging/integration.py
```

The script compiles its own temporary fixture from the real macros. Preserve strictness when adding cases; malformed nonempty data and absent optional data have different expected behavior.

[Complete test order and acceptance](../README.md) explains required services, version pinning, compiled artifacts and generated logs. Unit tests need no databases; integration scripts use only their documented read-only/disposable scope.
