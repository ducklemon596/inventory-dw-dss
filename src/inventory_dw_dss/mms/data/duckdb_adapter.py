"""Read normalized MMS exports, never reinterpret raw observed balances."""
from datetime import timedelta
from pathlib import Path

from .mock import MockDataProvider
from ..core.schemas import MMSValidationError, as_date


class DuckDBDataProvider:
    """Caller owns the connection; all reads for one snapshot share a transaction."""

    def __init__(self, connection):
        self.connection = connection

    def snapshot_dates(self):
        import duckdb
        try:
            if isinstance(self.connection, (str, Path)):
                with duckdb.connect(str(self.connection), read_only=True) as connection:
                    return DuckDBDataProvider(connection).snapshot_dates()
            return tuple(as_date(row[0]) for row in self.connection.execute(
                "SELECT DISTINCT analysis_date FROM mms_inventory_daily ORDER BY analysis_date").fetchall())
        except duckdb.Error as exc:
            raise MMSValidationError(f"Cannot read snapshot dates: {exc}") from exc

    def get_snapshot(self, analysis_date, filters=None):
        import duckdb
        try:
            return self._get_snapshot(analysis_date, filters)
        except duckdb.Error as exc:
            raise MMSValidationError(f"Cannot read normalized MMS export: {exc}") from exc

    def _get_snapshot(self, analysis_date, filters=None):
        if isinstance(self.connection, (str, Path)):
            import duckdb
            with duckdb.connect(str(self.connection), read_only=True) as connection:
                return DuckDBDataProvider(connection).get_snapshot(analysis_date, filters)
        t = as_date(analysis_date)
        self.connection.execute("BEGIN TRANSACTION")
        try:
            inventory = self._rows("SELECT * FROM mms_inventory_daily WHERE analysis_date = ?", [t])
            sales = self._rows("SELECT * FROM mms_sales_daily WHERE sales_date BETWEEN ? AND ?",
                               [t-timedelta(days=89), t])
            result = MockDataProvider(inventory, sales).get_snapshot(t, filters)
            self.connection.execute("COMMIT")
            return result
        except Exception:
            self.connection.execute("ROLLBACK")
            raise

    def _rows(self, sql, parameters):
        cursor = self.connection.execute(sql, parameters)
        names = [c[0] for c in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]
