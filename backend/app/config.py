from decimal import Decimal
from urllib.parse import quote_plus

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://jmi:jmi_dev_password@localhost:5432/jmi_trading"

    # AWS (infra/ecs.tf) injects the DB password from Secrets Manager as its
    # own env var rather than a full connection string, since Terraform
    # never sees the RDS-managed plaintext password. When database_host is
    # set, it takes precedence and database_url is assembled from these.
    database_host: str | None = None
    database_port: int = 5432
    database_name: str = "jmi_trading"
    database_user: str = "jmi"
    database_password: str | None = None

    jwt_secret: str = "dev-only-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 12

    cors_origins: list[str] = ["*"]

    # Top-of-book depth levels pushed to WS clients / REST snapshots.
    book_depth_levels: int = 10

    # Risk & Exposure view (app/risk). Only these usernames may call
    # /risk/* or subscribe to the risk WS channel -- enforced server-side;
    # the UI merely hides the tab. Override via RISK_VIEWER_USERNAMES='["a","b"]'.
    risk_viewer_usernames: list[str] = ["market_maker"]
    # An account holding more than this % of a symbol's platform-wide
    # inventory raises a CRITICAL concentration alert.
    risk_concentration_limit_pct: Decimal = Decimal("70")
    # reserved_usd / usd_balance at or above this % raises a WARNING.
    risk_utilization_warn_pct: Decimal = Decimal("80")

    @model_validator(mode="after")
    def _assemble_database_url_from_parts(self) -> "Settings":
        if self.database_host:
            password = quote_plus(self.database_password or "")
            self.database_url = (
                f"postgresql+asyncpg://{self.database_user}:{password}"
                f"@{self.database_host}:{self.database_port}/{self.database_name}"
            )
        return self


settings = Settings()
