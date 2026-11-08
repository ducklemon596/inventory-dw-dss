# SQL outside dbt

[oltp](oltp/README.md) contains transactional schema and bootstrap upserts. Analytical SQL belongs in [transform/dbt](../transform/dbt/README.md). There is no independent warehouse schema loader under this directory.
