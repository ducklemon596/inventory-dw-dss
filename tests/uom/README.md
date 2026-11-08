# UOM reference and failure tests

Entry points: `test_reference.py` and `integration.py`.

Six reference tests protect immutable v1/v2 SHA-256 values, exact seed union, explicit governance and preserved historical decisions. `integration.py` executes compiled conversion SQL with disposable tables to reject unknown versions, candidate arithmetic and contradictory identity factors.

```bash
uv run --locked python -m unittest discover -s tests/uom -v
uv run --locked python tests/uom/integration.py
```

Run the pinned full dbt build first for integration. Never replace expected checksums after an unexplained reference edit; a new approval needs a new published version.

[Complete test order and acceptance](../README.md) explains required services, version pinning, compiled artifacts and generated logs. Unit tests need no databases; integration scripts use only their documented read-only/disposable scope.
