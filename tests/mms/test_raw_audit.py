import csv

from inventory_dw_dss.mms.data.raw_audit import audit_source_exports


def test_real_export_audit_preserves_rows_and_does_not_approve_missing_stock(tmp_path):
    sales, stock = tmp_path/"sales.csv", tmp_path/"stock.csv"
    with sales.open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f)
        w.writerow(["RowNumber","DateTime","DrugCode","Unit"])
        w.writerow([1,"30 Jun 2025 10:00:00","A","Tab"])
    with stock.open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f)
        w.writerow(["RowNumber","DateTime","DrugCode","Warehouse"])
        w.writerow([1,"30 Jun 2025 10:00:00","A","Apotek"])
    report=audit_source_exports(sales,stock,"2025-06-30")
    assert report["sales"]["rows"] == 1
    assert report["sales"]["row_numbers_contiguous"]
    assert len(report["sales"]["sha256"]) == 64
    assert report["both_locations_observed_at_t"] == 0
    assert report["complete_30day_two_location_outcomes"] == 0
    assert report["production_ready"] is False
