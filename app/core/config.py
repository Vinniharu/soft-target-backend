"""Environment-driven application settings.

All configuration is loaded from environment variables (or a local `.env`
file in development) through a single :class:`Settings` instance. Pydantic
validation runs at import time so the process refuses to start when a
required value is missing or malformed.
"""

from __future__ import annotations

import base64
import ipaddress
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["development", "production", "test"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: AppEnv = "development"
    http_host: str = "0.0.0.0"  # noqa: S104 — bind address is a config choice
    http_port: int = 8000

    database_url: str

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    storage_dir: Path

    cors_allowed_origins: str = ""

    log_level: str = "info"
    enable_docs: bool = False

    login_rate_limit_max_attempts: int = 5
    login_rate_limit_window_minutes: int = 15

    trusted_proxies: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origins(self) -> list[str]:
        if not self.cors_allowed_origins.strip():
            return []
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def trusted_proxy_networks(
        self,
    ) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        if not self.trusted_proxies.strip():
            return []
        return [
            ipaddress.ip_network(entry.strip(), strict=False)
            for entry in self.trusted_proxies.split(",")
            if entry.strip()
        ]

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_long_enough(cls, value: str) -> str:
        if not value:
            raise ValueError("JWT_SECRET must be set")
        raw_len = len(value.encode("utf-8"))
        decoded_len = 0
        try:
            decoded_len = len(base64.b64decode(value, validate=True))
        except (ValueError, base64.binascii.Error):
            decoded_len = 0
        if max(raw_len, decoded_len) < 32:
            raise ValueError("JWT_SECRET must decode to at least 32 bytes of entropy")
        return value

    @field_validator("storage_dir")
    @classmethod
    def _storage_dir_absolute(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @field_validator("cors_allowed_origins")
    @classmethod
    def _no_wildcard_in_prod(cls, value: str, info: object) -> str:
        # Wildcard rejection happens at app boot in main.py where we know the
        # environment; we keep this field validator permissive to allow tests
        # to construct a Settings without CORS configured.
        return value

    @field_validator("trusted_proxies")
    @classmethod
    def _trusted_proxies_parseable(cls, value: str) -> str:
        if not value.strip():
            return value
        for entry in value.split(","):
            entry = entry.strip()
            if not entry:
                continue
            try:
                ipaddress.ip_network(entry, strict=False)
            except ValueError as exc:
                raise ValueError(
                    f"TRUSTED_PROXIES entry {entry!r} is not a valid IP or CIDR"
                ) from exc
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
