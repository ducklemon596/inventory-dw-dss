# Python source

The installed [inventory_dw_dss package](inventory_dw_dss/README.md) exposes `load postgres`, `load raw` and `transform` through the `inventory-dw-dss` entrypoint in [pyproject.toml](../pyproject.toml). CSV preparation belongs to the optional PostgreSQL path; raw loading reads the transactional database, and transformation delegates to the installed dbt runner. Analytical SQL stays in [dbt](../transform/dbt/README.md).
