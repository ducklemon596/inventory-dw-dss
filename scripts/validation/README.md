# Validator wrappers

`validate_source_sequence.py` and `validate_inventory_history.py` import the maintained Python package and call its `main()`. Keep these wrappers short; do not add a second implementation here.

[Script commands](../README.md) describe required files, database settings and outputs. [Package validation](../../src/inventory_dw_dss/validation/README.md) explains each validator and failure scope. Both are read-only with optional local JSON output; run after dbt and while extraction/build are idle.
