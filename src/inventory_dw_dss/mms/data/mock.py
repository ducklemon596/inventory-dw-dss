from copy import deepcopy
from datetime import timedelta
import json

from ..core.schemas import InventoryRow, InventorySnapshot, MMSValidationError, as_date, finite


class MockDataProvider:
    """In-memory copy of normalized inventory and explicitly complete daily sales.

    Each daily row is an affirmative observation, including explicit zeros.
    Providers must not generate zeros from missing warehouse rows.
    """

    def __init__(self, inventory, sales):
        self._inventory = deepcopy(inventory)
        self._sales = deepcopy(sales)
        self._sales_by_sku = {}
        for row in self._sales:
            self._sales_by_sku.setdefault(row["sku_id"], []).append(row)

    def get_snapshot(self, analysis_date, filters=None):
        t = as_date(analysis_date)
        filters = filters or {}
        if set(filters) - {"sku_ids"}:
            raise MMSValidationError("Unsupported snapshot filter")
        inventory = [r for r in self._inventory if as_date(r["analysis_date"]) == t]
        if not inventory:
            raise MMSValidationError(f"No verified snapshot for {t}")
        versions = {(r["snapshot_version"], r["data_version"]) for r in inventory}
        if len(versions) != 1:
            raise MMSValidationError("Mixed snapshot/data versions")
        rows = []
        seen = set()
        for raw in inventory:
            sku = raw["sku_id"]
            if sku in seen:
                raise MMSValidationError("Duplicate inventory SKU")
            seen.add(sku)
            if filters.get("sku_ids") is not None and sku not in filters["sku_ids"]:
                continue
            if raw["location_scope"] != "pharmacy_total" or as_date(raw["feature_as_of"]) > t:
                raise MMSValidationError("Unverified location scope or future feature date")
            days = {}
            for sale in self._sales_by_sku.get(sku, ()):
                d = as_date(sale["sales_date"])
                if sale["sku_id"] != sku or not t - timedelta(days=89) <= d <= t:
                    continue
                if d in days:
                    raise MMSValidationError("Duplicate daily sales event")
                finite(sale["quantity"], "quantity", 0)
                if sale.get("revenue") is not None:
                    finite(sale["revenue"], "revenue", 0)
                days[d] = sale
            if len(days) != 90:
                raise MMSValidationError(f"Incomplete 90-day sales coverage for {sku}")
            def total(n):
                return sum(r["quantity"] for d, r in days.items() if d > t-timedelta(days=n))
            features = raw.get("features") or {}
            if isinstance(features, str):
                features = json.loads(features)
            if not isinstance(features, dict):
                raise MMSValidationError("features must be a numeric JSON object")
            for key, value in features.items():
                finite(value, f"feature {key}")
            rows.append(InventoryRow(
                sku_id=sku, stock_unit=raw["stock_unit"], available_stock=raw["available_stock"],
                sales_7d=total(7), sales_30d=total(30), sales_90d=total(90),
                revenue_90d=(sum(r["revenue"] for r in days.values())
                             if all(r.get("revenue") is not None for r in days.values()) else None),
                eligible=raw["eligible"], features=features,
                days_since_last_receipt=raw.get("days_since_last_receipt"),
                flags=tuple(raw.get("flags", ())),
                observed_stockout_days=raw.get("observed_stockout_days"),
                diagnostic_observed_days=raw.get("diagnostic_observed_days"),
            ))
        snapshot_version, data_version = next(iter(versions))
        return InventorySnapshot(t, snapshot_version, data_version, tuple(rows))
