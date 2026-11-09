# MMS verification

Run `uv run --locked --extra ui --group dev pytest tests/mms -q` from the repo
root. Tests do not require running PostgreSQL, ClickHouse or ETL. They exercise
real DuckDB in memory, a temporary fitted HistGB artifact (never a production
replacement), temporary SQLite storage and Streamlit AppTest form interactions.

Coverage includes as-of boundaries, missing/duplicate data, artifact feature
order/checksum, deterministic scenario constraints, independent historical
outcomes, SOP exclusions, manager action validation and save/reopen workflow.

The existing warehouse suites and disposable-database integration instructions
remain in [the main test guide](../README.md). Windows cannot import the existing
POSIX `fcntl` bootstrap lock. Existing published UOM checksum failures must be
investigated separately, never fixed by altering expected hashes.
