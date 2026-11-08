# Python package

`inventory_dw_dss` provides the installed `inventory-dw-dss` command through uv.

- `cli.py`: operational extraction and explicit optional bootstrap commands.
- `extraction.py`: PostgreSQL snapshot reads, inclusive watermarks, validated raw publication and recovery.
- `oltp_ingestion/`: CSV preparation and initial OLTP upserts; requires the `bootstrap` dependency group.
- `validation/`: read-only export lineage and historical inventory reconciliation.

Reusable Python logic belongs in this package. SQL analytical transformations belong in
`transform/dbt/`; execution wrappers belong in `scripts/`. Validation modules are imported
only by their wrappers/tests and never by operational extraction. Bootstrap does not run
implicitly when a source connection fails.

```bash
uv run --locked inventory-dw-dss --help
uv run --locked inventory-dw-dss extract --batch-size 20000
```
