# Public command regression

[test_commands.py](test_commands.py) checks public scope/date validation, help without optional pandas, destination dispatch, dbt selection/version forwarding and nonzero failure status. It requires no running databases. The pandas group is used by the PostgreSQL dispatch case.

```bash
uv run --locked --group bootstrap python -m unittest discover -s tests/cli -v
```

[PostgreSQL integration](../oltp_ingestion/README.md) and [raw integration](../extraction/README.md) additionally execute the public full/range commands against disposable databases, including repeated execution. They preserve the operational source/raw databases. The [complete test guide](../README.md) documents regression prerequisites and order.
