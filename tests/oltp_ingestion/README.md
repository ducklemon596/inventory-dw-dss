# Optional bootstrap tests

Entry points: `test_preparation.py` and `integration.py`.

Parser tests cover composite fields, signed quantities, number/percentage formats, all interval boundaries, source-key preservation and failed/atomic preparation. `integration.py` uses temporary files and a disposable PostgreSQL database for schema repeatability, stable-PK upserts, catalogs, source namespaces, date/dataset selection, batch FKs and rollback.

```bash
uv run --locked --group bootstrap python -m unittest discover -s tests/oltp_ingestion -v
uv run --locked --group bootstrap python tests/oltp_ingestion/integration.py
```

The integration also invokes public full/range commands against a disposable database, checking automatic preparation/cache reuse, source changes, stable PKs and retained unmatched rows. Requires the optional bootstrap dependency group. Do not use production preparation/loading to reproduce fixture failures; reference source CSVs and operational OLTP remain unchanged.

[Complete test order and acceptance](../README.md) explains required services, version pinning, compiled artifacts and generated logs. Unit tests need no databases; integration scripts use only their documented read-only/disposable scope.
