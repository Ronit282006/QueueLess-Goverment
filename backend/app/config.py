"""Environment-driven application settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Look for .env in the current working directory AND at the project root, so
# `uvicorn`/`alembic` behave the same no matter where they are launched from.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILES = (Path(".env"), _PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES, env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "QueueLess Government Office API"
    environment: str = "development"

    database_url: str = "sqlite:///./queueless.db"
    redis_url: str = "redis://127.0.0.1:6379/0"
    cors_origins: str = "http://localhost:5173"

    jwt_secret: str = "dev-only-secret-change-me"
    jwt_expires_min: int = 720
    jwt_algorithm: str = "HS256"

    email_mode: str = "log"  # log | smtp
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "queueless@demo.local"
    smtp_use_starttls: bool = True
    smtp_use_ssl: bool = False
    frontend_base_url: str = "http://localhost:5173"
    otp_expiry_min: int = 5
    otp_resend_cooldown_sec: int = 60
    otp_max_sends_per_hour: int = 5
    otp_max_verify_attempts: int = 5
    arrival_buffer_min: int = 15
    incident_response_min: int = 30

    service_duration_min: float = 6.2
    no_show_grace_min: int = 3
    eta_alert_threshold_min: int = 10
    sla_target_wait_min: int = 20
    rate_limit_enabled: bool = True
    background_workers_enabled: bool = True
    sweeper_interval_sec: int = 15
    email_poll_sec: float = 1.5

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
