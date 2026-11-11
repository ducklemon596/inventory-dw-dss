import csv
import io
from dataclasses import replace

from inventory_dw_dss.mms.core.schemas import ScenarioConfig
from inventory_dw_dss.mms.ui_presenters import csv_export, item_rows, config_matches, item_advice
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


def test_plain_explanations_distinguish_partial_allocation_and_unknown_coverage():
    item=service().execute_scenario(ScenarioConfig(T,unit_budget_q=15)).review_list[0]
    partial=replace(item,eligible=True,suggested_q=20,allocated_q=5,dos=None,flags=())
    assert item_advice(partial,include_coverage=False)=="Needs 20; limited to 5"
    assert "Stock cover unavailable" in item_advice(partial)
    no_need=replace(partial,suggested_q=0,allocated_q=0)
    assert "No replenishment needed" in item_advice(no_need)
    assert "quantity limit reached" not in item_advice(no_need)
