from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = PROJECT_ROOT / "backend"
DEFAULT_STORAGE_ROOT = PROJECT_ROOT / "storage"


class Settings(BaseSettings):
    app_name: str = "HSK Mock Test Platform"
    environment: str = "development"
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
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 720
    clerk_secret_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("CLERK_SECRET_KEY", "HSK_CLERK_SECRET_KEY"),
    )
    clerk_jwt_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("CLERK_JWT_KEY", "HSK_CLERK_JWT_KEY"),
    )
    frontend_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    source_bundle_root: Path = PROJECT_ROOT / "HSK_mock_test_bundles_exam_answers_audio_file"
    storage_root: Path = DEFAULT_STORAGE_ROOT
    materials_root: Path = PROJECT_ROOT / "HSK_Materials"
    materials_storage_root: Path = DEFAULT_STORAGE_ROOT / "materials"
    materials_manifest_path: Path = DEFAULT_STORAGE_ROOT / "materials" / "manifest.json"
    material_access_secret: SecretStr | None = None
    # Signed PDF/audio URLs must remain valid long enough for browser range
    # requests during a normal study session.
    material_access_ttl_seconds: int = 3600
    material_zip_max_files: int = 5000
    material_zip_max_uncompressed_mb: int = 1024
    material_zip_max_ratio: int = 200
    max_upload_mb: int = 300
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
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

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

    @property
    def material_signing_secret(self) -> str:
        if self.material_access_secret is not None:
            return self.material_access_secret.get_secret_value()
        return self.jwt_secret


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
