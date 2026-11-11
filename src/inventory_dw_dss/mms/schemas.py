"""Data contracts shared by the MMS models, service, CLI and app.

Quantities are in each product's stock unit; values are in the sales currency.
"""
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date
import math
from types import MappingProxyType


class MMSError(ValueError):
    """Input data or configuration that MMS cannot use safely."""


class ArtifactError(MMSError):
    """A trained model bundle that is missing, altered or incompatible."""


def as_date(value):
    """Accept a date or an ISO 'YYYY-MM-DD' string."""
    if type(value) is date:
        return value
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise MMSError(f"Expected an ISO date YYYY-MM-DD, got {value!r}") from None


def check_number(value, name, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise MMSError(f"{name} must be a finite number")
    if minimum is not None and value < minimum:
        raise MMSError(f"{name} must be >= {minimum}")
    return float(value)


def to_dict(value):
    """JSON-compatible form used for storage, CSV and CLI output."""
    if is_dataclass(value):
        return {f.name: to_dict(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {str(k): to_dict(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_dict(v) for v in value]
    if isinstance(value, date):
        return value.isoformat()
    return value


@dataclass(frozen=True)
class InventoryRow:
    """One product at the end of the analysis date.

    available_stock is pharmacy-wide (dispensary + storeroom) and drives order quantities;
    dispensary_stock is the shelf the customer buys from.
    """
    sku_id: str
    stock_unit: str
    available_stock: float
    dispensary_stock: float
    sales_7d: float
    sales_30d: float
    sales_90d: float
    revenue_90d: float | None = None
    product_name: str | None = None
    sales_std_90d: float | None = None   # daily std over 90 days; None means Poisson variance
    abc_class: str | None = None         # A/B/C by 90-day sales value
    eligible: bool = True                # may be ordered (sold recently, not consignment)
    days_since_last_receipt: int | None = None
    features: Mapping = field(default_factory=dict)  # extra model inputs from the mart
    flags: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.sku_id or not self.stock_unit:
            raise MMSError("SKU and stock unit are required")
        for name in ("available_stock", "dispensary_stock"):
            check_number(getattr(self, name), name)
        for name in ("sales_7d", "sales_30d", "sales_90d"):
            check_number(getattr(self, name), name, 0)
        if not self.sales_7d <= self.sales_30d <= self.sales_90d:
            raise MMSError(f"{self.sku_id}: sales totals must grow with the lookback window")
        if self.abc_class not in (None, "A", "B", "C"):
            raise MMSError("abc_class must be A, B, C or null")
        object.__setattr__(self, "features", MappingProxyType(dict(self.features)))
        object.__setattr__(self, "flags", tuple(self.flags))

    @property
    def daily_demand(self):
        """MA90: average units sold per day over the last 90 days (the demand forecast, MB1)."""
        return self.sales_90d / 90

    @property
    def days_of_supply(self):
        """Days the pharmacy stock lasts at MA90 demand; None without demand."""
        return max(0.0, self.available_stock) / self.daily_demand if self.daily_demand else None

    @property
    def unit_value(self):
        """Average sales value per stock unit over 90 days."""
        return self.revenue_90d / self.sales_90d if self.revenue_90d and self.sales_90d else None


@dataclass(frozen=True)
class InventorySnapshot:
    analysis_date: date
    data_version: str
    rows: tuple[InventoryRow, ...]

    def __post_init__(self):
        object.__setattr__(self, "analysis_date", as_date(self.analysis_date))
        object.__setattr__(self, "rows", tuple(sorted(self.rows, key=lambda r: r.sku_id)))
        if len({r.sku_id for r in self.rows}) != len(self.rows):
            raise MMSError("Duplicate SKU in snapshot")


@dataclass(frozen=True)
class Observation:
    """What happened to one product on one day after the decision date."""
    observation_date: date
    sku_id: str
    sales_quantity: float
    stockout: bool                # dispensary closing balance <= 0
    received_quantity: float = 0
    stocktake: bool = False       # a stock count corrected the balance that day


PROFILES = ("RiskFirst", "RevenueAtRisk", "DaysOfSupply")
POLICIES = ("coverage", "service_level")


@dataclass(frozen=True)
class ScenarioConfig:
    """Manager inputs for one plan, applied in order: pstar -> ranking -> top_k -> policy -> budget."""
    analysis_date: date
    profile: str = "RiskFirst"
    pstar: float = 0.3                # minimum risk score to enter the review list
    top_k: int = 50                   # review list length
    unit_budget: int | None = None    # total units that may be allocated; None means unlimited
    policy: str = "coverage"
    coverage_days: float = 14         # coverage: days of MA90 demand; service_level: review period
    service_level: float = 0.95       # service_level: probability of covering demand
    lead_time_days: float = 2         # service_level: days between ordering and receipt
    abc_service: bool = False         # service_level: A 98%, B 95%, C 90%

    def __post_init__(self):
        object.__setattr__(self, "analysis_date", as_date(self.analysis_date))
        if self.profile not in PROFILES:
            raise MMSError(f"profile must be one of {PROFILES}")
        if self.policy not in POLICIES:
            raise MMSError(f"policy must be one of {POLICIES}")
        if not 0 <= check_number(self.pstar, "pstar") <= 1:
            raise MMSError("pstar must be in [0, 1]")
        if type(self.top_k) is not int or self.top_k <= 0:
            raise MMSError("top_k must be a positive integer")
        if self.unit_budget is not None and (type(self.unit_budget) is not int or self.unit_budget < 0):
            raise MMSError("unit_budget must be a nonnegative integer or None")
        if check_number(self.coverage_days, "coverage_days") <= 0:
            raise MMSError("coverage_days must be positive")
        if not 0.5 <= check_number(self.service_level, "service_level") < 1:
            raise MMSError("service_level must be in [0.5, 1)")
        check_number(self.lead_time_days, "lead_time_days", 0)
        if type(self.abc_service) is not bool:
            raise MMSError("abc_service must be a boolean")


@dataclass(frozen=True)
class DecisionItem:
    """One review-list line: why the product is listed and how much to order."""
    rank: int
    sku_id: str
    product_name: str | None
    stock_unit: str
    risk_score: float
    available_stock: float
    dispensary_stock: float
    daily_demand: float
    days_of_supply: float | None
    suggested_qty: int        # policy quantity before the budget
    allocated_qty: int        # quantity after the unit budget
    unit_value: float | None
    target_level: float | None = None   # service_level: order-up-to level S
    safety_stock: float | None = None   # service_level: S minus mean demand
    service_level: float | None = None
    abc_class: str | None = None
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioResult:
    config: ScenarioConfig
    items: tuple[DecisionItem, ...]
    summary: dict
    metadata: dict

    @property
    def orders(self):
        """Lines with a positive allocated quantity."""
        return tuple(i for i in self.items if i.allocated_qty > 0)
