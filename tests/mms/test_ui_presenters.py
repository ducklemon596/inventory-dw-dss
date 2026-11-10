import csv
import io
from dataclasses import replace

from inventory_dw_dss.mms.core.schemas import ScenarioConfig
from inventory_dw_dss.mms.ui_presenters import csv_export, item_rows, config_matches
from test_scenarios import service
from test_data import T


def test_exports_preserve_units_quantities_and_escape_spreadsheet_formulas():
    result=service().execute_scenario(ScenarioConfig(T,unit_budget_q=15))
    item=replace(result.review_list[0],sku_id="=SUM(1,2)",available_stock=-2.)
    payload=csv_export([item])
    row=next(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
    assert row["sku_id"] == "'=SUM(1,2)"
    assert row["available_stock"] == "-2.0"
    assert row["stock_unit"] == "tablet"
    assert row["suggested_q"] == "0"
    assert len(item_rows(result.review_list,query="b")) == 1
    assert item_rows(result.review_list,query="missing") == []


def test_visible_plan_is_bound_to_all_submitted_scenario_parameters():
    s=service()
    configs=[ScenarioConfig(T),ScenarioConfig(T,profile="LowStock")]
    comparison=s.compare_scenarios(configs)
    assert config_matches(comparison,configs)
    assert not config_matches(comparison,[replace(configs[0],unit_budget_q=0),configs[1]])
    assert not config_matches(comparison,configs[:1])
