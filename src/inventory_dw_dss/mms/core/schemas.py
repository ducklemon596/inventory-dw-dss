"""Immutable service contracts. Missing observations are never numeric zero."""
from dataclasses import dataclass, fields, is_dataclass
from datetime import date
from enum import Enum
import math
from types import MappingProxyType
from collections.abc import Mapping


class MMSValidationError(ValueError):
    """The supplied data/configuration cannot safely be executed."""


class ArtifactError(MMSValidationError):
    """The trained artifact or its feature/version contract is unavailable."""


def as_date(value):
    if type(value) is date:
        return value
    try:
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError()
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise MMSValidationError("Expected an ISO analysis date YYYY-MM-DD") from None


def finite(value, name, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise MMSValidationError(f"{name} must be a finite number")
    if minimum is not None and value < minimum:
        raise MMSValidationError(f"{name} must be >= {minimum}")
    return float(value)


def to_dict(value):
    """Strict JSON-compatible serialization shared by UI, persistence and CLI."""
    if is_dataclass(value):
        return {f.name: to_dict(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {str(k): to_dict(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_dict(v) for v in value]
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


@dataclass(frozen=True)
class InventoryRow:
    sku_id: str
    stock_unit: str
    available_stock: float
    sales_7d: float
    sales_30d: float
    sales_90d: float
    revenue_90d: float | None
    eligible: bool = True
    days_since_last_receipt: int | None = None
    features: Mapping = None
    flags: tuple[str, ...] = ()
    observed_stockout_days: int | None = None
    diagnostic_observed_days: int | None = None

    def __post_init__(self):
        if not isinstance(self.sku_id, str) or not self.sku_id or not self.stock_unit:
            raise MMSValidationError("SKU and stock unit must be nonempty strings")
        if type(self.eligible) is not bool:
            raise MMSValidationError("eligible must be an explicit boolean")
        for key in ("days_since_last_receipt", "observed_stockout_days", "diagnostic_observed_days"):
            value = getattr(self, key)
            if value is not None and (type(value) is not int or value < 0):
                raise MMSValidationError(f"{key} must be a nonnegative integer or null")
        if (self.observed_stockout_days is not None and self.diagnostic_observed_days is not None
                and self.observed_stockout_days > self.diagnostic_observed_days):
            raise MMSValidationError("Stockout count cannot exceed observed day count")
        if isinstance(self.flags, str) or not all(isinstance(f, str) for f in self.flags):
            raise MMSValidationError("flags must be a sequence of strings")
        object.__setattr__(self, "flags", tuple(self.flags))
        finite(self.available_stock, "available_stock")
        for key in ("sales_7d", "sales_30d", "sales_90d"):
            finite(getattr(self, key), key, 0)
        if not self.sales_7d <= self.sales_30d <= self.sales_90d:
            raise MMSValidationError("Sales lookback totals are inconsistent")
        if self.revenue_90d is not None:
            finite(self.revenue_90d, "revenue_90d", 0)
        object.__setattr__(self, "features", MappingProxyType(dict(self.features or {})))
        if self.available_stock < 0:
            object.__setattr__(self, "eligible", False)
            object.__setattr__(self, "flags", tuple(sorted(set(self.flags) | {"negative_stock"})))

    @property
    def vel90(self):
        return self.sales_90d / 90

    @property
    def dos(self):
        return max(0, self.available_stock) / self.vel90 if self.vel90 else None


@dataclass(frozen=True)
class InventorySnapshot:
    analysis_date: date
    snapshot_version: str
    data_version: str
    rows: tuple[InventoryRow, ...]
    location_scope: str = "pharmacy_total"

    def __post_init__(self):
        object.__setattr__(self, "analysis_date", as_date(self.analysis_date))
        object.__setattr__(self, "rows", tuple(sorted(self.rows, key=lambda r: r.sku_id)))
        if not self.snapshot_version or not self.data_version:
            raise MMSValidationError("Snapshot and data versions are required")
        if self.location_scope != "pharmacy_total":
            raise MMSValidationError("Only verified pharmacy_total scope is supported")
        if len({r.sku_id for r in self.rows}) != len(self.rows):
            raise MMSValidationError("Duplicate SKU in snapshot")


PROFILES = ("RiskFirst", "LowStock", "DOS", "RevenueAtRisk")


@dataclass(frozen=True)
class ScenarioConfig:
    analysis_date: date
    profile: str = "RiskFirst"
    pstar: float = 0.3
    top_k: int = 50
    unit_budget_q: int | None = None
    coverage_tau_days: float = 14

    def __post_init__(self):
        object.__setattr__(self, "analysis_date", as_date(self.analysis_date))
        if self.profile not in PROFILES:
            raise MMSValidationError(f"profile must be one of {PROFILES}")
        if not 0 <= finite(self.pstar, "pstar") <= 1:
            raise MMSValidationError("pstar must be in [0,1]")
        if type(self.top_k) is not int or self.top_k <= 0:
            raise MMSValidationError("top_k must be a positive integer")
        if self.unit_budget_q is not None and (type(self.unit_budget_q) is not int or self.unit_budget_q < 0):
            raise MMSValidationError("unit_budget_q must be a nonnegative integer or null")
        if finite(self.coverage_tau_days, "coverage_tau_days") <= 0:
            raise MMSValidationError("coverage_tau_days must be positive")


@dataclass(frozen=True)
class ExecutionError:
    code: str
    message: str


@dataclass(frozen=True)
class ModelResult:
    model_id: str
    ok: bool
    items: tuple[dict, ...]
    metadata: dict
    error: ExecutionError | None = None


@dataclass(frozen=True)
class DecisionItem:
    sku_id: str
    rank: int
    risk_score: float
    available_stock: float
    stock_unit: str
    dos: float | None
    vel90: float
    suggested_q: int
    allocated_q: int
    eligible: bool
    flags: tuple[str, ...]
    explanation: str


@dataclass(frozen=True)
class ScenarioResult:
    config: ScenarioConfig
    review_list: tuple[DecisionItem, ...]
    order_proposal: tuple[DecisionItem, ...]
    summary: dict
    metadata: dict


@dataclass(frozen=True)
class ScenarioComparison:
    results: tuple[ScenarioResult, ...]
    overlap: tuple[dict, ...]
