from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx

from app.models import GlobalSettings, ServiceConfig


API_BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE_URL = "https://image.tmdb.org/t/p"


@dataclass(slots=True)
class TmdbTitle:
    media_type: str
    id: int
    title: str
    popularity: float
    vote_average: float
    backdrop_path: str | None
    poster_path: str | None


@dataclass(slots=True)
class ArtworkCandidate:
    media_type: str
    id: int
    title: str
    file_path: str
    source: str
    language: str | None
    width: int | None
    height: int | None


class JsonTtlCache:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def get(self, key: str) -> Any | None:
        path = self._cache_path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        if float(payload.get("expires_at", 0)) < time.time():
            return None
        return payload.get("data")

    def set(self, key: str, data: Any, ttl_seconds: int) -> None:
        path = self._cache_path(key)
        payload = {"expires_at": time.time() + ttl_seconds, "data": data}
        path.write_text(json.dumps(payload), encoding="utf-8")


class TmdbClient:
    def __init__(
        self,
        api_key: str | None,
        bearer_token: str | None,
        cache_dir: Path,
        image_cache_dir: Path,
        global_settings: GlobalSettings,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not api_key and not bearer_token:
            raise ValueError("TMDB_API_KEY or TMDB_BEARER_TOKEN must be configured")

        headers: dict[str, str] = {"Accept": "application/json"}
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"

        self.api_key = api_key
        self.image_size = global_settings.image_size
        self.global_settings = global_settings
        self.client = httpx.Client(
            base_url=API_BASE_URL,
            headers=headers,
            timeout=timeout_seconds,
            follow_redirects=True,
        )
        self.api_cache = JsonTtlCache(cache_dir)
        self.image_cache_dir = image_cache_dir
        self.image_cache_dir.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        self.client.close()

    def _request_json(self, path: str, params: dict[str, Any], cache_ttl_minutes: int) -> dict[str, Any]:
        request_params = dict(params)
        if self.api_key:
            request_params["api_key"] = self.api_key
        cache_key = f"{path}?{json.dumps(request_params, sort_keys=True, default=str)}"
        cached = self.api_cache.get(cache_key)
        if cached is not None:
            return cached

        response = self.client.get(path, params=request_params)
        response.raise_for_status()
        payload = response.json()
        self.api_cache.set(cache_key, payload, cache_ttl_minutes * 60)
        return payload

    def discover_titles(self, service: ServiceConfig, progress: Callable[[float, str], None]) -> list[TmdbTitle]:
        media_types = ["movie", "tv"]
        if service.content_mode == "movie":
            media_types = ["movie"]
        elif service.content_mode == "tv":
            media_types = ["tv"]

        discovered: list[TmdbTitle] = []
        seen_keys: set[str] = set()
        total_requests = max(1, len(media_types) * self.global_settings.pages_per_media_type)
        completed_requests = 0

        for media_type in media_types:
            for page in range(1, self.global_settings.pages_per_media_type + 1):
                payload = self._request_json(
                    f"/discover/{media_type}",
                    {
                        "with_watch_providers": service.provider_id,
                        "watch_region": service.region,
                        "with_watch_monetization_types": "flatrate",
                        "sort_by": "popularity.desc",
                        "include_adult": "false",
                        "language": self.global_settings.tmdb_language,
                        "page": page,
                    },
                    cache_ttl_minutes=self.global_settings.api_cache_ttl_minutes,
                )

                for item in payload.get("results", []):
                    title_id = int(item["id"])
                    key = f"{media_type}:{title_id}"
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    discovered.append(
                        TmdbTitle(
                            media_type=media_type,
                            id=title_id,
                            title=item.get("title") or item.get("name") or f"{media_type}:{title_id}",
                            popularity=float(item.get("popularity") or 0),
                            vote_average=float(item.get("vote_average") or 0),
                            backdrop_path=item.get("backdrop_path"),
                            poster_path=item.get("poster_path"),
                        )
                    )
                completed_requests += 1
                progress(
                    5.0 + 10.0 * (completed_requests / total_requests),
                    f"Fetched TMDB discover page {page} for {media_type}",
                )

        discovered.sort(key=lambda item: (item.popularity, item.vote_average), reverse=True)
        return discovered[: service.max_titles]

    def get_images(self, media_type: str, item_id: int) -> list[dict[str, Any]]:
        payload = self._request_json(
            f"/{media_type}/{item_id}/images",
            {"include_image_language": "en,null"},
            cache_ttl_minutes=self.global_settings.api_cache_ttl_minutes,
        )
        return list(payload.get("backdrops", []))

    def select_artwork(self, service: ServiceConfig, title: TmdbTitle) -> ArtworkCandidate | None:
        backdrops = self.get_images(title.media_type, title.id)
        chosen = self._pick_backdrop(service.artwork_mode, backdrops)
        if chosen:
            return ArtworkCandidate(
                media_type=title.media_type,
                id=title.id,
                title=title.title,
                file_path=str(chosen["file_path"]),
                source="images.backdrops",
                language=chosen.get("iso_639_1"),
                width=chosen.get("width"),
                height=chosen.get("height"),
            )
        if title.backdrop_path:
            return ArtworkCandidate(
                media_type=title.media_type,
                id=title.id,
                title=title.title,
                file_path=title.backdrop_path,
                source="item.backdrop_path",
                language=None,
                width=None,
                height=None,
            )
        if title.poster_path:
            return ArtworkCandidate(
                media_type=title.media_type,
                id=title.id,
                title=title.title,
                file_path=title.poster_path,
                source="item.poster_path",
                language=None,
                width=None,
                height=None,
            )
        return None

    def collect_artworks(
        self,
        service: ServiceConfig,
        progress: Callable[[float, str], None],
        log: Callable[[str], None],
    ) -> tuple[list[TmdbTitle], list[ArtworkCandidate]]:
        titles = self.discover_titles(service, progress)
        if not titles:
            raise RuntimeError(f"No TMDB titles found for {service.name} ({service.region})")

        log(f"Discovered {len(titles)} titles for provider {service.provider_id} in region {service.region}")
        selected: list[ArtworkCandidate] = []
        seen_paths: set[str] = set()

        for index, title in enumerate(titles, start=1):
            artwork = self.select_artwork(service, title)
            if artwork and artwork.file_path not in seen_paths:
                selected.append(artwork)
                seen_paths.add(artwork.file_path)
            progress(
                15.0 + 20.0 * (index / len(titles)),
                f"Selected artwork for {index} of {len(titles)} titles",
            )
            if len(selected) >= service.max_artwork_images:
                break

        log(f"Selected {len(selected)} usable artwork images")
        return titles, selected

    def _pick_backdrop(self, artwork_mode: str, backdrops: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not backdrops:
            return None

        def ranking(backdrop: dict[str, Any]) -> tuple[int, int, float, float]:
            language = backdrop.get("iso_639_1")
            width = int(backdrop.get("width") or 0)
            vote = float(backdrop.get("vote_average") or 0)
            aspect_ratio = float(backdrop.get("aspect_ratio") or 1.7777)
            aspect_penalty = abs(aspect_ratio - 1.7777)

            if artwork_mode == "clean_backdrops":
                language_rank = 0 if language is None else 1 if language == "en" else 2
            else:
                language_rank = 0 if language == "en" else 1 if language is not None else 2

            return (
                language_rank,
                0 if aspect_penalty <= 0.2 else 1,
                -width,
                -vote,
            )

        return sorted(backdrops, key=ranking)[0]

    def download_artworks(
        self,
        artworks: list[ArtworkCandidate],
        progress: Callable[[float, str], None],
        log: Callable[[str], None],
    ) -> list[Path]:
        paths: list[Path] = []
        total = max(1, len(artworks))
        for index, artwork in enumerate(artworks, start=1):
            cached_path = self.download_image(artwork.file_path)
            paths.append(cached_path)
            progress(
                35.0 + 20.0 * (index / total),
                f"Downloaded {index} of {total} artwork files",
            )
        log(f"Downloaded or reused {len(paths)} cached image files")
        return paths

    def download_image(self, file_path: str) -> Path:
        safe_path = file_path.lstrip("/")
        destination = self.image_cache_dir / self.image_size / safe_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and destination.stat().st_size > 0:
            return destination

        image_url = f"{IMAGE_BASE_URL}/{self.image_size}/{safe_path}"
        response = self.client.get(image_url)
        response.raise_for_status()
        destination.write_bytes(response.content)
        return destination
