import json
import ipaddress
import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = PROJECT_ROOT / "backend"
DEFAULT_STORAGE_ROOT = PROJECT_ROOT / "storage"
HOSTNAME_RE = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)"
    r"(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*\Z"
)


class Settings(BaseSettings):
    app_name: str = "HSK Mock Test Platform"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = True
    database_backend: Literal["mysql", "turso"] = "mysql"
    turso_database_url: str | None = Field(
        default=None, validation_alias=AliasChoices("TURSO_DATABASE_URL", "HSK_TURSO_DATABASE_URL")
    )
    turso_auth_token: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("TURSO_AUTH_TOKEN", "HSK_TURSO_AUTH_TOKEN")
    )
    database_url: str = (
        "mysql+pymysql://root:change_me@127.0.0.1:3306/"
        "hsk_mock_tester?charset=utf8mb4"
    )
    jwt_secret: str = "development-only-change-me"
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_minutes: int = Field(default=120, ge=5, le=1440)
    clerk_secret_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("CLERK_SECRET_KEY", "HSK_CLERK_SECRET_KEY"),
    )
    clerk_jwt_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("CLERK_JWT_KEY", "HSK_CLERK_JWT_KEY"),
    )
    frontend_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    force_https: bool | None = None
    rate_limit_enabled: bool = True
    rate_limit_max_clients: int = Field(default=10_000, ge=100, le=100_000)
    rate_limit_api_per_minute: int = Field(default=300, ge=10, le=10_000)
    rate_limit_auth_per_minute: int = Field(default=30, ge=5, le=1_000)
    rate_limit_material_per_minute: int = Field(default=60, ge=5, le=5_000)
    rate_limit_admin_per_minute: int = Field(default=60, ge=5, le=1_000)
    max_json_body_kb: int = Field(default=64, ge=8, le=1024)
    source_bundle_root: Path = PROJECT_ROOT / "HSK_mock_test_bundles_exam_answers_audio_file"
    storage_root: Path = DEFAULT_STORAGE_ROOT
    materials_root: Path = PROJECT_ROOT / "HSK_Materials"
    materials_storage_root: Path = DEFAULT_STORAGE_ROOT / "materials"
    materials_manifest_path: Path = DEFAULT_STORAGE_ROOT / "materials" / "manifest.json"
    material_access_secret: SecretStr | None = None
    # Signed PDF/audio URLs must remain valid long enough for browser range
    # requests during a normal study session.
    material_access_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    material_zip_max_files: int = Field(default=5000, ge=1, le=20_000)
    material_zip_max_uncompressed_mb: int = Field(default=1024, ge=1, le=10_240)
    material_zip_max_ratio: int = Field(default=200, ge=1, le=1000)
    max_upload_mb: int = Field(default=300, ge=1, le=1024)
    upload_zip_max_files: int = Field(default=2000, ge=1, le=10_000)
    upload_zip_max_ratio: int = Field(default=100, ge=1, le=1000)
    malware_scan_command: str | None = None
    malware_scan_timeout_seconds: int = Field(default=60, ge=1, le=600)
    b2_enabled: bool = False
    b2_bucket_name: str = "HSKMOCKTEST"
    b2_endpoint_url: str = "https://s3.us-east-005.backblazeb2.com"
    b2_region: str = "us-east-005"
    b2_key_id: SecretStr | None = None
    b2_application_key: SecretStr | None = None
    b2_signed_url_ttl_seconds: int = Field(default=3600, ge=60, le=86400)

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        env_prefix="HSK_",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            raw = value.strip()
            if raw.startswith("["):
                try:
                    value = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        "HSK_FRONTEND_ORIGINS must be a JSON array or comma-separated origins"
                    ) from exc
            else:
                value = [item.strip() for item in raw.split(",") if item.strip()]
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError("At least one frontend origin is required")

        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("Every frontend origin must be a URL string")
            origin = item.strip().rstrip("/")
            parsed = urlsplit(origin)
            try:
                port = parsed.port
            except ValueError as exc:
                raise ValueError(
                    "Frontend origins must contain only scheme, hostname, and optional port"
                ) from exc
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or origin == "null"
            ):
                raise ValueError(
                    "Frontend origins must contain only scheme, hostname, and optional port"
                )
            hostname = parsed.hostname.lower()
            try:
                address = ipaddress.ip_address(hostname)
            except ValueError:
                try:
                    hostname = hostname.encode("idna").decode("ascii")
                except UnicodeError as exc:
                    raise ValueError(
                        "Frontend origins must contain only scheme, hostname, and optional port"
                    ) from exc
                if not HOSTNAME_RE.fullmatch(hostname):
                    raise ValueError(
                        "Frontend origins must contain only scheme, hostname, and optional port"
                    )
            else:
                hostname = address.compressed
                if address.version == 6:
                    hostname = f"[{hostname}]"
            authority = hostname if port is None else f"{hostname}:{port}"
            canonical = f"{parsed.scheme.lower()}://{authority}"
            if canonical not in normalized:
                normalized.append(canonical)
        return normalized

    @field_validator(
        "source_bundle_root",
        "storage_root",
        "materials_root",
        "materials_storage_root",
        "materials_manifest_path",
        mode="before",
    )
    @classmethod
    def resolve_project_path(cls, value: object) -> Path:
        path = Path(str(value))
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        return path.resolve()

    @model_validator(mode="after")
    def derive_material_paths(self):
        if "materials_storage_root" not in self.model_fields_set:
            self.materials_storage_root = (self.storage_root / "materials").resolve()
        if "materials_manifest_path" not in self.model_fields_set:
            self.materials_manifest_path = self.materials_storage_root / "manifest.json"
        return self

    @model_validator(mode="after")
    def validate_production_security(self):
        if self.force_https is None:
            self.force_https = self.environment == "production"
        if self.environment != "production":
            return self

        problems: list[str] = []
        if self.debug:
            problems.append("HSK_DEBUG must be false")
        if not self.force_https:
            problems.append("HSK_FORCE_HTTPS must be true")
        if any(origin.startswith("http://") for origin in self.frontend_origins):
            problems.append("HSK_FRONTEND_ORIGINS must use HTTPS in production")
        if len(self.jwt_secret) < 32 or self.jwt_secret == "development-only-change-me":
            problems.append("HSK_JWT_SECRET must be an unpredictable value of at least 32 characters")
        if self.material_access_secret is None:
            problems.append("HSK_MATERIAL_ACCESS_SECRET must be configured separately")
        elif len(self.material_access_secret.get_secret_value()) < 32:
            problems.append("HSK_MATERIAL_ACCESS_SECRET must contain at least 32 characters")
        elif self.material_access_secret.get_secret_value() == self.jwt_secret:
            problems.append("HSK_MATERIAL_ACCESS_SECRET must differ from HSK_JWT_SECRET")
        if self.clerk_secret_key is None:
            problems.append("CLERK_SECRET_KEY is required")
        if self.database_backend == "turso" and (
            not self.turso_database_url or self.turso_auth_token is None
        ):
            problems.append("TURSO_DATABASE_URL and TURSO_AUTH_TOKEN are required")
        if self.database_backend == "mysql":
            database = urlsplit(self.database_url)
            if (database.username or "").lower() in {"root", "admin", "administrator"}:
                problems.append("HSK_DATABASE_URL must use a least-privilege application user")
            if not database.password or database.password == "change_me":
                problems.append("HSK_DATABASE_URL must include a non-default password")
        if self.b2_enabled and (
            self.b2_key_id is None or self.b2_application_key is None
        ):
            problems.append("HSK_B2_KEY_ID and HSK_B2_APPLICATION_KEY are required")
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self

    @property
    def material_signing_secret(self) -> str:
        if self.material_access_secret is not None:
            return self.material_access_secret.get_secret_value()
        return self.jwt_secret

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
