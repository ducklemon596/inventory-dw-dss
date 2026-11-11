# Inventory Studio

The Streamlit dashboard provides a Vietnamese manager workflow for MMS. It
uses the same services as the CLI; changing a widget never invokes ETL or dbt.

![Inventory Studio desktop](images/mms-dashboard.png)

## Start locally

The already generated trained demonstration is available at:

```powershell
uv run --locked --extra ui streamlit run reports/mms-trained-demo/app.py --server.address 127.0.0.1 --server.port 8501
```

Open http://127.0.0.1:8501. If the generated directory does not exist after
cloning, run `inventory-mms bootstrap-demo --output reports/mms-trained-demo
--seed 7` with the MMS/UI extra first; see [the integration guide](mms-production.md).
The trained app prominently identifies its simulation data. The real downloaded
source files and available-stock approval remain separate concerns.

For environment-configured sources, run
`streamlit run src/inventory_dw_dss/mms/ui.py`; existing DuckDB/ClickHouse settings
and the injected-runtime embedding interface are preserved.

## Workflow

The main workflow was simplified on 2026-11-11. See
[the current screen guide](mms-simple-ui.md): one scenario by default, three
primary tabs, plain-language allocation explanations and collapsed advanced
tools.

1. Select the date, target days of stock and total quantity that can be allocated.
   Click **Xem đề xuất nhập hàng**. Three cards summarize item counts and quantity.
2. **Hàng cần chú ý** shows the priority list with days of stock and allocation
   explanations. Search filters the visible table; CSV exports the full list.
3. **Xác nhận lượng nhập** shows allocated items and accepts, rejects, edits or
   records notes. Bulk approval marks only positive allocations. Saving does not
   submit a purchase order.
4. **Lịch sử đã lưu** reopens exact results and actions. Historical follow-up
   checks data-version compatibility before reading observations.
5. **Tùy chỉnh nâng cao** in the sidebar enables 1–4 scenarios, ranking profiles,
   risk thresholds and quantity limits. Q denotes SKU-specific units, not money.
6. The collapsed advanced section below results retains comparison, pairwise
   overlap, exact scores and 7/14/30-day backtests. Scores are not calibrated
   probabilities. Backtests retain the actual evaluated horizon across reruns.

Changing scenario controls marks the old plan as stale and disables saving or
evaluation until rerun. Starting a new run clears manager drafts; switching
between scenarios in the same run preserves drafts outside widget lifecycles.
Drafts are session-local: click **Lưu quyết định** for durable SQLite storage.
Switching data sources/releases/artifacts clears old comparison and manager state.

Empty and zero-budget lists remain valid tables. Undefined historical metrics
appear as blank/“—”, not zero. Optional details expose reproducibility metadata
and JSON downloads without putting raw payloads in the primary workflow.

## Layout and verification

Desktop uses a teal parameter sidebar, three metric cards and native tables.
At mobile widths, metric cards form two columns with the third card full width,
and the sidebar collapses. Tables retain their own horizontal scrolling.

The UI/presenter/tracking checks cover source switches, stale parameters, pending
notes, persisted backtests, per-scenario manager drafts, zero budgets and numeric
CSV preservation. Text cells are escaped for spreadsheet formulas; numeric
negative stock remains numeric. Browser QA used a fresh headless Chrome session
against the local trained app after the integrated browser reported no connected
browser. Desktop/mobile screenshots showed no page errors or mobile page overflow.
