"""Shared production/demo configuration for Streamlit, CLI and team applications."""
from contextlib import closing
from dataclasses import dataclass, field
import os

from .core.schemas import MMSValidationError
from .data.clickhouse_adapter import ClickHouseDataProvider, identifier
from .data.duckdb_adapter import DuckDBDataProvider
from .demo import build_demo_service, demo_outcomes
from .evaluation.backtesting import OutcomeProvider
from .models.histgb import HistGBRiskModel
from .service import MMSService


@dataclass(frozen=True)
class SourceSettings:
    source: str = "demo"
    duckdb_path: str = ""
    artifact_path: str = ""
    manifest_path: str = ""
    host: str = "localhost"
    port: int = 8123
    database: str = "inventory_dw"
    username: str = "dbt"
    password: str = field(default="dbt_local", repr=False)
    secure: bool = False
    release_id: str = ""

    @classmethod
    def from_env(cls, environ=None):
        env = os.environ if environ is None else environ
        source = env.get("MMS_DATA_SOURCE") or ("duckdb" if env.get("MMS_DUCKDB_PATH") else "demo")
        if source == "demo" and not env.get("MMS_DATA_SOURCE") and any(env.get(k) for k in ("MMS_ARTIFACT_PATH", "MMS_MANIFEST_PATH", "MMS_RELEASE_ID")):
            raise MMSValidationError("Production inputs require MMS_DATA_SOURCE or MMS_DUCKDB_PATH; demo fallback refused")
        try:
            port = int(env.get("CLICKHOUSE_HTTP_PORT", "8123"))
            if not 1 <= port <= 65535:
                raise ValueError()
        except (ValueError, TypeError):
            raise MMSValidationError("CLICKHOUSE_HTTP_PORT must be a valid port") from None
        secure = env.get("CLICKHOUSE_SECURE", "false").lower()
        if secure not in {"true", "false", "1", "0"}:
            raise MMSValidationError("CLICKHOUSE_SECURE must be true/false or 1/0")
        settings = cls(source=source, duckdb_path=env.get("MMS_DUCKDB_PATH", ""),
            artifact_path=env.get("MMS_ARTIFACT_PATH", ""), manifest_path=env.get("MMS_MANIFEST_PATH", ""),
            host=env.get("CLICKHOUSE_HOST", "localhost"), port=port,
            database=env.get("CLICKHOUSE_DB", "inventory_dw"), username=env.get("CLICKHOUSE_USER", "dbt"),
            password=env.get("CLICKHOUSE_PASSWORD", "dbt_local"), secure=secure in {"true", "1"},
            release_id=env.get("MMS_RELEASE_ID", ""))
        if source not in {"demo", "duckdb", "clickhouse"}:
            raise MMSValidationError("MMS_DATA_SOURCE must be demo, duckdb or clickhouse")
        return settings

    def connect_clickhouse(self):
        import clickhouse_connect
        from clickhouse_connect.driver.exceptions import ClickHouseError
        identifier(self.database)
        try:
            return clickhouse_connect.get_client(host=self.host, port=self.port, username=self.username,
                password=self.password, database=self.database, secure=self.secure,
                connect_timeout=3, send_receive_timeout=10, autogenerate_session_id=False)
        except (ClickHouseError, OSError) as exc:
            raise MMSValidationError(f"ClickHouse connection unavailable ({type(exc).__name__}); check server and read credentials") from exc


class ManagedClickHouseProvider:
    """One short-lived client per read; no shared sessions across Streamlit users."""
    def __init__(self, settings):
        self.settings = settings

    def get_snapshot(self, analysis_date, filters=None):
        with closing(self.settings.connect_clickhouse()) as client:
            return ClickHouseDataProvider(client, self.settings.database, self.settings.release_id).get_snapshot(analysis_date, filters)

    def snapshot_dates(self):
        with closing(self.settings.connect_clickhouse()) as client:
            return ClickHouseDataProvider(client, self.settings.database, self.settings.release_id).snapshot_dates()

    def get_outcomes(self):
        with closing(self.settings.connect_clickhouse()) as client:
            return ClickHouseDataProvider(client, self.settings.database, self.settings.release_id).get_outcomes()


def build_provider(settings):
    if settings.source == "duckdb":
        if not settings.duckdb_path:
            raise MMSValidationError("DuckDB source requires MMS_DUCKDB_PATH")
        return DuckDBDataProvider(settings.duckdb_path)
    if settings.source == "clickhouse":
        identifier(settings.database)
        if not settings.release_id:
            raise MMSValidationError("ClickHouse source requires MMS_RELEASE_ID")
        return ManagedClickHouseProvider(settings)
    if settings.source == "demo":
        return build_demo_service().provider
    raise MMSValidationError("Unknown MMS source")


@dataclass
class MMSRuntime:
    service: MMSService
    settings: SourceSettings = field(repr=False)

    @property
    def is_demo(self):
        model = self.service.executor.risk_model
        return self.settings.source == "demo" or getattr(model, "manifest", {}).get("data_kind") == "synthetic"

    def load_outcomes(self):
        if self.settings.source == "demo":
            return demo_outcomes()
        if self.settings.source == "clickhouse":
            return self.service.provider.get_outcomes()
        import duckdb
        try:
            with duckdb.connect(self.settings.duckdb_path, read_only=True) as connection:
                return OutcomeProvider.from_duckdb(connection)
        except duckdb.Error as exc:
            raise MMSValidationError(f"Cannot read DuckDB outcome export ({type(exc).__name__})") from exc


def build_runtime(settings=None):
    settings = settings or SourceSettings.from_env()
    provider = build_provider(settings)
    if settings.source == "demo":
        return MMSRuntime(build_demo_service(), settings)
    if not settings.artifact_path or not settings.manifest_path:
        raise MMSValidationError("Production inference requires MMS_ARTIFACT_PATH and MMS_MANIFEST_PATH")
    risk = HistGBRiskModel.load(settings.artifact_path, settings.manifest_path)
    return MMSRuntime(MMSService(provider, risk), settings)
