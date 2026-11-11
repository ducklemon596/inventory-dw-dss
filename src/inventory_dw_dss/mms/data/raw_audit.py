"""Inspect downloaded source evidence without changing warehouse or stock semantics."""
import hashlib
from pathlib import Path

from ..core.schemas import MMSValidationError, as_date


def audit_source_exports(sales_path, stock_path, analysis_date):
    import duckdb
    t = as_date(analysis_date)
    report = {"analysis_date": str(t), "production_ready": False}
    try:
        with duckdb.connect() as c:
            for table, path, extra in (("sales", Path(sales_path), "Unit"), ("stock", Path(stock_path), "Warehouse")):
                digest = hashlib.sha256()
                with path.open("rb") as source:
                    for chunk in iter(lambda: source.read(1024*1024), b""):
                        digest.update(chunk)
                c.execute(f"CREATE TEMP TABLE {table} AS SELECT RowNumber seq, DrugCode sku, "
                    "CAST(try_strptime(DateTime, '%d %b %Y %H:%M:%S') AS DATE) d, "
                    f"{extra} extra FROM read_csv(?, all_varchar=true)", [str(path)])
                n, first, last, skus, days, ids, lower, upper, invalid = c.execute(
                    f"SELECT count(*),min(d)::VARCHAR,max(d)::VARCHAR,count(DISTINCT sku),count(DISTINCT d),"
                    "count(DISTINCT try_cast(seq AS BIGINT)),min(try_cast(seq AS BIGINT)),max(try_cast(seq AS BIGINT)),"
                    f"count(*) FILTER (WHERE d IS NULL OR NOT regexp_full_match(seq,'[1-9][0-9]*')) FROM {table}").fetchone()
                report[table] = {"file": str(path), "sha256": digest.hexdigest(), "bytes": path.stat().st_size,
                    "rows": n, "first_date": first, "last_date": last, "sku_count": skus, "observed_dates": days,
                    "row_numbers_contiguous": bool(n and ids == n and lower == 1 and upper == n and not invalid),
                    "invalid_sequence_or_dates": invalid}
            report["warehouses"] = [{"name": name, "rows": n} for name,n in c.execute(
                "SELECT extra,count(*) FROM stock GROUP BY extra ORDER BY extra").fetchall()]
            report["sales_90day_dense_single_unit_skus"] = c.execute(
                "SELECT count(*) FROM (SELECT sku FROM sales WHERE d BETWEEN ?::DATE-89 AND ?::DATE "
                "GROUP BY sku HAVING count(DISTINCT d)=90 AND count(DISTINCT extra)=1)",[t,t]).fetchone()[0]
            report["both_locations_observed_at_t"] = c.execute(
                "SELECT count(*) FROM (SELECT sku FROM stock WHERE d=? AND extra IN ('Apotek','Gudang Obat 1') "
                "GROUP BY sku HAVING count(DISTINCT extra)=2)",[t]).fetchone()[0]
            report["complete_30day_two_location_outcomes"] = c.execute(
                "SELECT count(*) FROM (SELECT sku FROM (SELECT sku,d FROM stock WHERE d>?::DATE AND d<=?::DATE+30 "
                "AND extra IN ('Apotek','Gudang Obat 1') GROUP BY sku,d HAVING count(DISTINCT extra)=2) "
                "GROUP BY sku HAVING count(*)=30)",[t,t]).fetchone()[0]
    except duckdb.Error as exc:
        raise MMSValidationError(f"Source CSV schema/date audit failed ({type(exc).__name__})") from exc
    report["interpretation"] = ["Complete source sequence is not proof of physical availability or historical arrival time",
        "Absent SKU/day observations are not zero balances or verified zero demand",
        "Exact-day two-location coverage is diagnostic, not approval of available stock"]
    return report
