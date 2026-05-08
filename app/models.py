from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ContentMode = Literal["mixed", "movie", "tv"]
ArtworkMode = Literal["title_cards", "clean_backdrops"]
VideoCodec = Literal["vp9", "vp8"]
QualityPreset = Literal["high", "balanced", "small", "tiny"]
JobStatus = Literal["idle", "queued", "running", "succeeded", "failed"]


class RenderDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_width: int = 1280
    output_height: int = 720
    loop_duration_seconds: int = 90
    fps: int = 30
    card_width: int = 300
    gap: int = 14
    row_count: int = 6
    corner_radius: int = 12
    rotate_x: float = 0.0
    rotate_y: float = 0.0
    rotate_z: float = -6.0
    zoom: float = 1.0
    skew_x: float = 0.0
    skew_y: float = 0.0
    codec: VideoCodec = "vp9"
    quality_preset: QualityPreset = "balanced"
    crf: int = 34
    cpu_used: int = 6
    target_bitrate_kbps: int | None = None
    max_titles: int = 120
    max_artwork_images: int = 72
    minimum_usable_images: int = 24
    seed: int | None = None

    @field_validator(
        "output_width",
        "output_height",
        "loop_duration_seconds",
        "fps",
        "card_width",
        "row_count",
        "max_titles",
        "max_artwork_images",
        "minimum_usable_images",
    )
    @classmethod
    def validate_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("value must be greater than 0")
        return value

    @field_validator("gap", "corner_radius", "cpu_used", "crf")
    @classmethod
    def validate_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("value must be 0 or greater")
        return value

    @field_validator("zoom")
    @classmethod
    def validate_zoom(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("zoom must be greater than 0")
        return value


class ServiceConfig(RenderDefaults):
    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str
    enabled: bool = True
    auto_refresh_enabled: bool = False
    provider_id: int
    region: str = "US"
    content_mode: ContentMode = "mixed"
    artwork_mode: ArtworkMode = "title_cards"
    refresh_interval_minutes: int = 24 * 60

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name is required")
        return value

    @field_validator("provider_id", "refresh_interval_minutes")
    @classmethod
    def validate_positive_service_ints(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("value must be greater than 0")
        return value

    @field_validator("region")
    @classmethod
    def validate_region(cls, value: str) -> str:
        value = value.strip().upper()
        if len(value) != 2:
            raise ValueError("region must be a 2-letter code")
        return value


class GlobalSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tmdb_api_key: str | None = None
    tmdb_bearer_token: str | None = None
    default_region: str = "US"
    tmdb_language: str = "en-US"
    scheduler_enabled: bool = False
    pages_per_media_type: int = 4
    api_cache_ttl_minutes: int = 360
    image_size: str = "w1280"
    scheduler_poll_seconds: int = 60
    max_concurrent_jobs: int = 2
    failure_retry_minutes: int = 30
    global_defaults: RenderDefaults = Field(default_factory=RenderDefaults)

    @field_validator("default_region")
    @classmethod
    def validate_default_region(cls, value: str) -> str:
        value = value.strip().upper()
        if len(value) != 2:
            raise ValueError("default_region must be a 2-letter code")
        return value

    @field_validator(
        "pages_per_media_type",
        "api_cache_ttl_minutes",
        "scheduler_poll_seconds",
        "max_concurrent_jobs",
        "failure_retry_minutes",
    )
    @classmethod
    def validate_positive_global_ints(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("value must be greater than 0")
        return value

    @field_validator("tmdb_api_key", "tmdb_bearer_token")
    @classmethod
    def normalize_optional_secrets(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    global_settings: GlobalSettings = Field(default_factory=GlobalSettings)
    services: list[ServiceConfig] = Field(default_factory=list)


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    global_settings: GlobalSettings
    service: ServiceConfig


class JobState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    slug: str
    reason: str
    status: JobStatus = "queued"
    progress: float = 0.0
    message: str = "Queued"
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime


class ServiceState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    slug: str
    status: JobStatus = "idle"
    preview_status: JobStatus = "idle"
    preview_progress: float = 0.0
    preview_message: str | None = None
    last_generated_at: datetime | None = None
    last_attempt_at: datetime | None = None
    last_failure_at: datetime | None = None
    preview_generated_at: datetime | None = None
    next_scheduled_at: datetime | None = None
    retry_after_at: datetime | None = None
    file_size_bytes: int | None = None
    preview_file_size_bytes: int | None = None
    thumbnail_size_bytes: int | None = None
    preview_thumbnail_size_bytes: int | None = None
    duration_seconds: int | None = None
    preview_duration_seconds: int | None = None
    title_count: int | None = None
    preview_title_count: int | None = None
    image_count: int | None = None
    preview_image_count: int | None = None
    provider_id: int | None = None
    region: str | None = None
    output_width: int | None = None
    output_height: int | None = None
    seed_used: int | None = None
    preview_seed_used: int | None = None
    output_path: str | None = None
    thumbnail_path: str | None = None
    preview_output_path: str | None = None
    preview_thumbnail_path: str | None = None
    settings_snapshot: dict[str, Any] = Field(default_factory=dict)
    preview_settings_snapshot: dict[str, Any] = Field(default_factory=dict)
    encoding_stats: dict[str, Any] = Field(default_factory=dict)
    last_error: str | None = None
    preview_last_error: str | None = None
    preview_settings_hash: str | None = None
    last_job_id: str | None = None
    updated_at: datetime | None = None
    preview_updated_at: datetime | None = None


class AppState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    services: dict[str, ServiceState] = Field(default_factory=dict)
