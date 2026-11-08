# Validator unit tests

Entry points: `test_source_sequence.py / test_inventory_history.py`.

Tests exercise canonical field serialization, passport association/sequence failures and inventory reconciliation failure cases without accessing databases. They protect evidence logic rather than duplicate model business calculations.

```bash
uv run --locked python -m unittest discover -s tests/validation -v
```

A failure can mean a serializer or scope contract changed. Preserve supplied passport bytes and review the serialization before changing expectations.

[Complete test order and acceptance](../README.md) explains required services, version pinning, compiled artifacts and generated logs. Unit tests need no databases; integration scripts use only their documented read-only/disposable scope.
