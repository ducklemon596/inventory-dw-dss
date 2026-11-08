# Extraction regression

Entry points: `test_publication.py` and `integration.py`.

Publication unit tests cover identifier rejection, acknowledged exchange/rename bookkeeping and rollback order. `integration.py` uses disposable PG/raw/DW databases to exercise public incremental/full/range commands, inclusive calendar boundaries and independent watermarks, stable PK rereads, retained unmatched rows, reference refresh, locks and injected failures.

```bash
uv run --locked python -m unittest discover -s tests/extraction -v
uv run --locked python tests/extraction/integration.py
```

Unknown exchange acknowledgement is retained for inspection; the integration fixture manually resolves that ambiguity. A green test does not establish automatic hard-crash recovery or global cross-table atomicity.

[Complete test order and acceptance](../README.md) explains required services, version pinning, compiled artifacts and generated logs. Unit tests need no databases; integration scripts use only their documented read-only/disposable scope.
