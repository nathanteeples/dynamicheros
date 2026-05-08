from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.jobs import GenerationManager, ServiceLogStore
from app.models import AppSettings, PreviewRequest
from app.persistence import AppRepository
from app.rendering import HeroRenderer


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT_DIR / "data"))
CACHE_DIR = Path(os.getenv("CACHE_DIR", ROOT_DIR / "cache"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", ROOT_DIR / "output"))
APP_PORT = int(os.getenv("APP_PORT", "8080"))
DEFAULT_REGION = os.getenv("DEFAULT_REGION", "US")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BEARER_TOKEN = os.getenv("TMDB_BEARER_TOKEN")


def build_runtime() -> tuple[AppRepository, GenerationManager, Path]:
    repository = AppRepository(
        data_dir=DATA_DIR,
        cache_dir=CACHE_DIR,
        output_dir=OUTPUT_DIR,
        default_region=DEFAULT_REGION,
    )
    repository.ensure_directories()
    renderer = HeroRenderer(cache_dir=CACHE_DIR, output_dir=OUTPUT_DIR)
    log_store = ServiceLogStore(repository.logs_dir)
    manager = GenerationManager(
        repository=repository,
        renderer=renderer,
        log_store=log_store,
        env_api_key=TMDB_API_KEY,
        env_bearer_token=TMDB_BEARER_TOKEN,
    )
    return repository, manager, ROOT_DIR / "app" / "static"


repository, manager, static_dir = build_runtime()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await manager.start()
    try:
        yield
    finally:
        await manager.stop()


app = FastAPI(title="Dynamic Heroes", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/api/settings")
async def get_settings() -> dict:
    settings = repository.load_settings()
    return {"settings": settings.model_dump(mode="json")}


@app.put("/api/settings")
async def put_settings(settings: AppSettings) -> dict:
    repository.save_settings(settings)
    manager.reload_settings()
    return {"settings": settings.model_dump(mode="json")}


@app.get("/api/services")
@app.get("/api/heroes")
async def list_services() -> dict:
    return {"services": manager.list_services()}


@app.get("/api/services/{slug}")
@app.get("/api/heroes/{slug}")
async def get_service(slug: str) -> dict:
    try:
        return manager.get_service_details(slug)
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail="Unknown service") from exc


@app.post("/api/services/{slug}/regenerate")
async def regenerate_service(slug: str) -> dict:
    try:
        job = await manager.queue_regeneration(slug, reason="manual")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"job": job.model_dump(mode="json")}


@app.post("/api/services/{slug}/preview")
async def preview_service(slug: str, request: PreviewRequest) -> dict:
    try:
        return await asyncio.to_thread(manager.generate_preview_sync, slug, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/regenerate-all")
async def regenerate_all() -> dict:
    jobs = await manager.queue_all()
    return {"jobs": [job.model_dump(mode="json") for job in jobs]}


@app.get("/api/jobs")
async def list_jobs() -> dict:
    return {"jobs": [job.model_dump(mode="json") for job in manager.list_jobs()]}


@app.get("/api/logs")
async def get_logs(slug: str | None = None, limit: int = 100) -> dict:
    return {"logs": manager.log_store.tail(slug=slug, limit=max(1, min(limit, 500)))}


def _asset_file(slug: str, extension: str, asset_type: str) -> Path:
    service_slugs = {service.slug for service in repository.load_settings().services}
    if slug not in service_slugs:
        raise HTTPException(status_code=404, detail="Unknown service")
    if asset_type == "preview":
        return repository.previews_dir / f"{slug}.{extension}"
    return repository.heroes_dir / f"{slug}.{extension}"


@app.get("/heroes/{slug}.webm")
async def get_hero_video(slug: str) -> FileResponse:
    path = _asset_file(slug, "webm", "hero")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Hero video not generated yet")
    return FileResponse(path, media_type="video/webm", headers={"Cache-Control": "public, max-age=60, must-revalidate"})


@app.get("/heroes/{slug}.jpg")
async def get_hero_thumbnail(slug: str) -> FileResponse:
    path = _asset_file(slug, "jpg", "hero")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Hero thumbnail not generated yet")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=60, must-revalidate"})


@app.get("/previews/{slug}.webm")
async def get_preview_video(slug: str) -> FileResponse:
    path = _asset_file(slug, "webm", "preview")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Preview video not generated yet")
    return FileResponse(path, media_type="video/webm", headers={"Cache-Control": "no-cache, must-revalidate"})


@app.get("/previews/{slug}.jpg")
async def get_preview_thumbnail(slug: str) -> FileResponse:
    path = _asset_file(slug, "jpg", "preview")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Preview image not generated yet")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-cache, must-revalidate"})
