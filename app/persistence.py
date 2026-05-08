from __future__ import annotations

import json
import threading
from pathlib import Path

from app.models import AppSettings, AppState, GlobalSettings, RenderDefaults, ServiceConfig
from app.runtime_resources import recommended_parallel_jobs, recommended_vp9_cpu_used
from app.service_catalog import DEFAULT_SERVICE_DEFINITIONS


class AppRepository:
    def __init__(self, data_dir: Path, cache_dir: Path, output_dir: Path, default_region: str) -> None:
        self.data_dir = data_dir
        self.cache_dir = cache_dir
        self.output_dir = output_dir
        self.heroes_dir = output_dir / "heroes"
        self.previews_dir = output_dir / "previews"
        self.logs_dir = data_dir / "logs"
        self.settings_path = data_dir / "settings.json"
        self.state_path = data_dir / "state.json"
        self.default_region = default_region.upper()
        self._lock = threading.RLock()

    def ensure_directories(self) -> None:
        for path in (
            self.data_dir,
            self.cache_dir,
            self.output_dir,
            self.heroes_dir,
            self.previews_dir,
            self.logs_dir,
            self.cache_dir / "api",
            self.cache_dir / "images",
            self.cache_dir / "work",
        ):
            path.mkdir(parents=True, exist_ok=True)

    def build_default_settings(self) -> AppSettings:
        global_settings = GlobalSettings(
            default_region=self.default_region,
            max_concurrent_jobs=recommended_parallel_jobs(),
            global_defaults=RenderDefaults(cpu_used=recommended_vp9_cpu_used()),
        )
        defaults = global_settings.global_defaults
        services = [
            ServiceConfig(
                slug=str(entry["slug"]),
                name=str(entry["name"]),
                provider_id=int(entry["provider_id"]),
                region=self.default_region,
                auto_refresh_enabled=False,
                output_width=defaults.output_width,
                output_height=defaults.output_height,
                loop_duration_seconds=defaults.loop_duration_seconds,
                fps=defaults.fps,
                card_width=defaults.card_width,
                gap=defaults.gap,
                row_count=defaults.row_count,
                corner_radius=defaults.corner_radius,
                rotate_x=defaults.rotate_x,
                rotate_y=defaults.rotate_y,
                rotate_z=defaults.rotate_z,
                zoom=defaults.zoom,
                skew_x=defaults.skew_x,
                skew_y=defaults.skew_y,
                codec=defaults.codec,
                quality_preset=defaults.quality_preset,
                crf=defaults.crf,
                cpu_used=defaults.cpu_used,
                target_bitrate_kbps=defaults.target_bitrate_kbps,
                max_titles=defaults.max_titles,
                max_artwork_images=defaults.max_artwork_images,
                minimum_usable_images=defaults.minimum_usable_images,
                seed=defaults.seed,
            )
            for entry in DEFAULT_SERVICE_DEFINITIONS
        ]
        return AppSettings(global_settings=global_settings, services=services)

    def load_settings(self) -> AppSettings:
        with self._lock:
            if not self.settings_path.exists():
                settings = self.build_default_settings()
                self.save_settings(settings)
                return settings

            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            settings = AppSettings.model_validate(data)
            changed = self._apply_runtime_default_migrations(settings)

            existing = {service.slug: service for service in settings.services}
            for entry in DEFAULT_SERVICE_DEFINITIONS:
                slug = str(entry["slug"])
                if slug in existing:
                    continue
                settings.services.append(
                    ServiceConfig(
                        slug=slug,
                        name=str(entry["name"]),
                        provider_id=int(entry["provider_id"]),
                        region=settings.global_settings.default_region,
                        auto_refresh_enabled=False,
                    )
                )
            settings.services.sort(key=lambda service: service.name.lower())
            if changed:
                self.save_settings(settings)
            return settings

    def save_settings(self, settings: AppSettings) -> None:
        with self._lock:
            self.settings_path.write_text(
                json.dumps(settings.model_dump(mode="json"), indent=2),
                encoding="utf-8",
            )

    def load_state(self) -> AppState:
        with self._lock:
            if not self.state_path.exists():
                state = AppState()
                self.save_state(state)
                return state
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            return AppState.model_validate(data)

    def save_state(self, state: AppState) -> None:
        with self._lock:
            self.state_path.write_text(
                json.dumps(state.model_dump(mode="json"), indent=2),
                encoding="utf-8",
            )

    def _apply_runtime_default_migrations(self, settings: AppSettings) -> bool:
        changed = False
        recommended_cpu_used = recommended_vp9_cpu_used()

        defaults = settings.global_settings.global_defaults
        if self._matches_legacy_render_defaults(defaults):
            self._apply_render_speed_defaults(defaults, recommended_cpu_used)
            changed = True
        elif self._matches_current_stock_defaults(defaults) and defaults.cpu_used != recommended_cpu_used:
            defaults.cpu_used = recommended_cpu_used
            changed = True

        for service in settings.services:
            if self._matches_legacy_render_defaults(service):
                self._apply_render_speed_defaults(service, recommended_cpu_used)
                changed = True
                continue
            if self._matches_current_stock_defaults(service) and service.cpu_used != recommended_cpu_used:
                service.cpu_used = recommended_cpu_used
                changed = True

        return changed

    def _matches_legacy_render_defaults(self, item: RenderDefaults) -> bool:
        return (
            item.output_width == 1920
            and item.output_height == 1080
            and item.fps == 30
            and item.card_width == 360
            and item.gap == 14
            and item.row_count == 6
            and item.corner_radius == 12
            and item.rotate_z == -6.0
            and item.zoom == 1.0
            and item.crf == 34
            and item.cpu_used == 4
        )

    def _matches_current_stock_defaults(self, item: RenderDefaults) -> bool:
        return (
            item.output_width == 1280
            and item.output_height == 720
            and item.fps == 30
            and item.card_width == 300
            and item.gap == 14
            and item.row_count == 6
            and item.corner_radius == 12
            and item.rotate_z == -6.0
            and item.zoom == 1.0
            and item.crf == 34
            and item.cpu_used in {6, 7, 8}
        )

    def _apply_render_speed_defaults(self, item: RenderDefaults, cpu_used: int) -> None:
        item.output_width = 1280
        item.output_height = 720
        item.fps = 30
        item.card_width = 300
        item.cpu_used = cpu_used
