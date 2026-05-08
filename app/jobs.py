from __future__ import annotations

import asyncio
import json
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from app.models import AppSettings, AppState, JobState, ServiceConfig, ServiceState
from app.persistence import AppRepository
from app.rendering import HeroRenderer
from app.tmdb import TmdbClient


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


class ServiceLogStore:
    def __init__(self, logs_dir: Path) -> None:
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, slug: str, level: str, message: str, **context: Any) -> None:
        payload = {
            "timestamp": utc_now().isoformat(),
            "slug": slug,
            "level": level,
            "message": message,
            "context": context,
        }
        path = self.logs_dir / f"{slug}.log"
        with self._lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload) + "\n")

    def tail(self, slug: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if slug:
            paths = [self.logs_dir / f"{slug}.log"]
        else:
            paths = sorted(self.logs_dir.glob("*.log"))

        entries: list[dict[str, Any]] = []
        for path in paths:
            if not path.exists():
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            for line in lines[-limit:]:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        entries.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
        return entries[:limit]


class GenerationManager:
    def __init__(
        self,
        repository: AppRepository,
        renderer: HeroRenderer,
        log_store: ServiceLogStore,
        env_api_key: str | None,
        env_bearer_token: str | None,
    ) -> None:
        self.repository = repository
        self.renderer = renderer
        self.log_store = log_store
        self.env_api_key = env_api_key.strip() if env_api_key else None
        self.env_bearer_token = env_bearer_token.strip() if env_bearer_token else None
        self.state = self.repository.load_state()
        self.jobs: dict[str, JobState] = {}
        self._job_lock = threading.RLock()
        self._queue: asyncio.Queue[tuple[str, str, str]] = asyncio.Queue()
        self._inflight_slugs: set[str] = set()
        self._worker_tasks: list[asyncio.Task[None]] = []
        self._scheduler_task: asyncio.Task[None] | None = None
        self._stopping = False
        self.settings = self.repository.load_settings()

    async def start(self) -> None:
        self.settings = self.repository.load_settings()
        self.state = self.repository.load_state()
        self._stopping = False
        self._hydrate_existing_outputs()

        worker_count = self.settings.global_settings.max_concurrent_jobs
        self._worker_tasks = [asyncio.create_task(self._worker_loop()) for _ in range(worker_count)]
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())

        await self._queue_startup_jobs()

    async def stop(self) -> None:
        self._stopping = True
        if self._scheduler_task:
            self._scheduler_task.cancel()
        for task in self._worker_tasks:
            task.cancel()
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        if self._scheduler_task:
            await asyncio.gather(self._scheduler_task, return_exceptions=True)

    def reload_settings(self) -> AppSettings:
        self.settings = self.repository.load_settings()
        return self.settings

    async def _queue_startup_jobs(self) -> None:
        for service in self.settings.services:
            if not service.enabled:
                continue
            output_path = self.repository.heroes_dir / f"{service.slug}.webm"
            if not output_path.exists():
                await self.queue_regeneration(service.slug, reason="startup-missing")
                continue
            if self._service_due(service):
                await self.queue_regeneration(service.slug, reason="startup-due")

    def _service_due(self, service: ServiceConfig) -> bool:
        service_state = self.state.services.get(service.slug)
        if service_state is None:
            output_path = self.repository.heroes_dir / f"{service.slug}.webm"
            return not output_path.exists()

        now = utc_now()
        if service_state.retry_after_at and service_state.retry_after_at > now:
            return False
        if service_state.last_generated_at is None:
            output_path = self.repository.heroes_dir / f"{service.slug}.webm"
            return not output_path.exists()
        return now >= service_state.last_generated_at + timedelta(minutes=service.refresh_interval_minutes)

    def _hydrate_existing_outputs(self) -> None:
        changed = False
        for service in self.settings.services:
            output_path = self.repository.heroes_dir / f"{service.slug}.webm"
            thumbnail_path = self.repository.heroes_dir / f"{service.slug}.jpg"
            if not output_path.exists():
                continue

            state = self._ensure_service_state(service.slug)
            modified_at = datetime.fromtimestamp(output_path.stat().st_mtime, tz=UTC)
            if state.last_generated_at is None:
                state.last_generated_at = modified_at
                state.next_scheduled_at = modified_at + timedelta(minutes=service.refresh_interval_minutes)
                state.file_size_bytes = output_path.stat().st_size
                state.duration_seconds = service.loop_duration_seconds
                state.output_width = service.output_width
                state.output_height = service.output_height
                state.provider_id = service.provider_id
                state.region = service.region
                state.output_path = str(output_path)
                state.thumbnail_path = str(thumbnail_path) if thumbnail_path.exists() else None
                state.thumbnail_size_bytes = thumbnail_path.stat().st_size if thumbnail_path.exists() else None
                state.updated_at = modified_at
                if state.status not in {"running", "queued"}:
                    state.status = "succeeded"
                changed = True
        if changed:
            self.repository.save_state(self.state)

    async def _scheduler_loop(self) -> None:
        while not self._stopping:
            self.reload_settings()
            for service in self.settings.services:
                if not service.enabled:
                    continue
                if service.slug in self._inflight_slugs:
                    continue
                output_path = self.repository.heroes_dir / f"{service.slug}.webm"
                if not output_path.exists() or self._service_due(service):
                    await self.queue_regeneration(service.slug, reason="scheduled")
            await asyncio.sleep(self.settings.global_settings.scheduler_poll_seconds)

    async def queue_regeneration(self, slug: str, reason: str = "manual") -> JobState:
        self.reload_settings()
        if slug not in {service.slug for service in self.settings.services}:
            raise KeyError(f"Unknown service slug: {slug}")

        with self._job_lock:
            if slug in self._inflight_slugs:
                return next(job for job in self.jobs.values() if job.slug == slug and job.status in {"queued", "running"})

            job_id = uuid.uuid4().hex
            now = utc_now()
            job = JobState(
                id=job_id,
                slug=slug,
                reason=reason,
                status="queued",
                progress=0.0,
                message="Queued",
                queued_at=now,
                updated_at=now,
            )
            self.jobs[job_id] = job
            self._inflight_slugs.add(slug)
            state = self._ensure_service_state(slug)
            state.status = "queued"
            state.last_job_id = job_id
            state.updated_at = now
            self.repository.save_state(self.state)

        await self._queue.put((job_id, slug, reason))
        self.log_store.append(slug, "info", "Queued generation job", reason=reason, job_id=job_id)
        return job

    async def queue_all(self) -> list[JobState]:
        jobs: list[JobState] = []
        for service in self.reload_settings().services:
            if not service.enabled:
                continue
            jobs.append(await self.queue_regeneration(service.slug, reason="manual-all"))
        return jobs

    async def _worker_loop(self) -> None:
        while True:
            job_id, slug, reason = await self._queue.get()
            try:
                await asyncio.to_thread(self._run_job_sync, job_id, slug, reason)
            finally:
                self._queue.task_done()

    def _run_job_sync(self, job_id: str, slug: str, reason: str) -> None:
        service = next(service for service in self.reload_settings().services if service.slug == slug)
        job = self.jobs[job_id]
        service_state = self._ensure_service_state(slug)
        now = utc_now()
        job.status = "running"
        job.started_at = now
        job.updated_at = now
        job.message = "Starting generation"
        service_state.status = "running"
        service_state.last_attempt_at = now
        service_state.last_job_id = job_id
        service_state.provider_id = service.provider_id
        service_state.region = service.region
        self.repository.save_state(self.state)
        self.log_store.append(slug, "info", "Starting generation", job_id=job_id, reason=reason)

        def progress(percent: float, message: str) -> None:
            bounded = max(0.0, min(100.0, percent))
            with self._job_lock:
                job.progress = bounded
                job.message = message
                job.updated_at = utc_now()
                service_state.status = "running"
                service_state.updated_at = utc_now()

        def log(message: str, level: str = "info", **context: Any) -> None:
            self.log_store.append(slug, level, message, **context)

        tmdb_client: TmdbClient | None = None

        try:
            api_key, bearer_token = self._resolved_tmdb_credentials()
            tmdb_client = TmdbClient(
                api_key=api_key,
                bearer_token=bearer_token,
                cache_dir=self.repository.cache_dir / "api",
                image_cache_dir=self.repository.cache_dir / "images",
                global_settings=self.settings.global_settings,
            )
            titles, artworks = tmdb_client.collect_artworks(service, progress, log)
            if len(artworks) < service.minimum_usable_images:
                raise RuntimeError(
                    f"Only {len(artworks)} artwork images found; minimum required is {service.minimum_usable_images}"
                )

            image_paths = tmdb_client.download_artworks(artworks, progress, log)
            render_result = self.renderer.render(service, image_paths, progress, log)
            completed_at = utc_now()

            service_state.status = "succeeded"
            service_state.last_generated_at = completed_at
            service_state.last_failure_at = None
            service_state.retry_after_at = None
            service_state.next_scheduled_at = completed_at + timedelta(minutes=service.refresh_interval_minutes)
            service_state.file_size_bytes = render_result.file_size_bytes
            service_state.thumbnail_size_bytes = render_result.thumbnail_size_bytes
            service_state.duration_seconds = render_result.duration_seconds
            service_state.title_count = len(titles)
            service_state.image_count = len(image_paths)
            service_state.output_width = service.output_width
            service_state.output_height = service.output_height
            service_state.seed_used = render_result.seed_used
            service_state.output_path = str(render_result.output_path)
            service_state.thumbnail_path = str(render_result.thumbnail_path)
            service_state.last_error = None
            service_state.settings_snapshot = service.model_dump(mode="json")
            service_state.encoding_stats = {
                "codec": service.codec,
                "crf": service.crf,
                "cpu_used": service.cpu_used,
                "frame_count": render_result.frame_count,
                "ffmpeg_command": render_result.ffmpeg_command,
                "render_seconds": round(render_result.render_seconds, 3),
            }
            service_state.updated_at = completed_at

            job.status = "succeeded"
            job.progress = 100.0
            job.message = "Generation finished"
            job.finished_at = completed_at
            job.updated_at = completed_at
            self.log_store.append(
                slug,
                "info",
                "Generation finished",
                output_path=str(render_result.output_path),
                file_size_bytes=render_result.file_size_bytes,
                render_seconds=render_result.render_seconds,
            )
        except Exception as exc:
            failed_at = utc_now()
            service_state.status = "failed"
            service_state.last_failure_at = failed_at
            service_state.retry_after_at = failed_at + timedelta(
                minutes=self.settings.global_settings.failure_retry_minutes
            )
            service_state.last_error = str(exc)
            service_state.updated_at = failed_at

            job.status = "failed"
            job.message = str(exc)
            job.finished_at = failed_at
            job.updated_at = failed_at
            self.log_store.append(slug, "error", "Generation failed", error=str(exc))
        finally:
            if tmdb_client is not None:
                tmdb_client.close()
            with self._job_lock:
                self._inflight_slugs.discard(slug)
            self.repository.save_state(self.state)

    def _ensure_service_state(self, slug: str) -> ServiceState:
        state = self.state.services.get(slug)
        if state is None:
            state = ServiceState(slug=slug)
            self.state.services[slug] = state
        return state

    def _resolved_tmdb_credentials(self) -> tuple[str | None, str | None]:
        api_key = self.env_api_key or self.settings.global_settings.tmdb_api_key
        bearer_token = self.env_bearer_token or self.settings.global_settings.tmdb_bearer_token
        return api_key, bearer_token

    def list_jobs(self) -> list[JobState]:
        return sorted(self.jobs.values(), key=lambda job: job.queued_at, reverse=True)

    def get_service_details(self, slug: str) -> dict[str, Any]:
        service = next(service for service in self.reload_settings().services if service.slug == slug)
        service_state = self.state.services.get(slug)
        return self._service_payload(service, service_state)

    def list_services(self) -> list[dict[str, Any]]:
        self.reload_settings()
        return [
            self._service_payload(service, self.state.services.get(service.slug))
            for service in sorted(self.settings.services, key=lambda item: item.name.lower())
        ]

    def _service_payload(self, service: ServiceConfig, state: ServiceState | None) -> dict[str, Any]:
        output_path = self.repository.heroes_dir / f"{service.slug}.webm"
        thumbnail_path = self.repository.heroes_dir / f"{service.slug}.jpg"
        return {
            "slug": service.slug,
            "name": service.name,
            "settings": service.model_dump(mode="json"),
            "state": None if state is None else state.model_dump(mode="json"),
            "urls": {
                "hero": f"/heroes/{service.slug}.webm",
                "thumbnail": f"/heroes/{service.slug}.jpg",
            },
            "file_exists": output_path.exists(),
            "thumbnail_exists": thumbnail_path.exists(),
        }
