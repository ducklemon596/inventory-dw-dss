# Python source

The installed [inventory_dw_dss package](inventory_dw_dss/README.md) exposes `load postgres`, `load raw` and `transform` through the `inventory-dw-dss` entrypoint in [pyproject.toml](../pyproject.toml). CSV preparation belongs to the optional PostgreSQL path; raw loading reads the transactional database, and transformation delegates to the installed dbt runner. Analytical SQL stays in [dbt](../transform/dbt/README.md). The [MMS subpackage](inventory_dw_dss/mms/README.md) is the decision-support layer on top of the marts.
