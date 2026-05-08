from __future__ import annotations

import math
import os
import random
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

from app.models import ServiceConfig


QUALITY_PRESET_TO_CRF = {
    "high": 30,
    "balanced": 34,
    "small": 38,
    "tiny": 42,
}


@dataclass(slots=True)
class RenderResult:
    output_path: Path
    thumbnail_path: Path
    file_size_bytes: int
    thumbnail_size_bytes: int
    duration_seconds: int
    frame_count: int
    seed_used: int
    ffmpeg_command: list[str]
    render_seconds: float


@dataclass(slots=True)
class RowLayer:
    band: Image.Image
    loop_width: int
    y: int


class HeroRenderer:
    def __init__(self, cache_dir: Path, output_dir: Path, ffmpeg_binary: str = "ffmpeg") -> None:
        self.cache_dir = cache_dir
        self.output_dir = output_dir / "heroes"
        self.preview_dir = output_dir / "previews"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.preview_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_binary = ffmpeg_binary

    def render(
        self,
        service: ServiceConfig,
        image_paths: list[Path],
        progress: Callable[[float, str], None],
        log: Callable[[str], None],
        seed_override: int | None = None,
    ) -> RenderResult:
        final_video_path = self.output_dir / f"{service.slug}.webm"
        final_thumbnail_path = self.output_dir / f"{service.slug}.jpg"
        return self._render_variant(
            service=service,
            image_paths=image_paths,
            progress=progress,
            log=log,
            final_video_path=final_video_path,
            final_thumbnail_path=final_thumbnail_path,
            minimum_output_size_bytes=32 * 1024,
            seed_override=seed_override,
        )

    def render_preview(
        self,
        service: ServiceConfig,
        image_paths: list[Path],
        progress: Callable[[float, str], None],
        log: Callable[[str], None],
        seed_override: int | None = None,
    ) -> RenderResult:
        preview_service = self._preview_service(service)
        preview_video_path = self.preview_dir / f"{service.slug}.webm"
        preview_thumbnail_path = self.preview_dir / f"{service.slug}.jpg"
        return self._render_variant(
            service=preview_service,
            image_paths=image_paths,
            progress=progress,
            log=log,
            final_video_path=preview_video_path,
            final_thumbnail_path=preview_thumbnail_path,
            minimum_output_size_bytes=8 * 1024,
            seed_override=seed_override,
        )

    def _render_variant(
        self,
        service: ServiceConfig,
        image_paths: list[Path],
        progress: Callable[[float, str], None],
        log: Callable[[str], None],
        final_video_path: Path,
        final_thumbnail_path: Path,
        minimum_output_size_bytes: int,
        seed_override: int | None = None,
    ) -> RenderResult:
        if len(image_paths) < service.minimum_usable_images:
            raise RuntimeError(
                f"Need at least {service.minimum_usable_images} usable images, found {len(image_paths)}"
            )

        started_at = time.perf_counter()
        card_width = service.card_width
        card_height = int(round(card_width * 9 / 16))
        seed_used = self._resolve_seed(service, seed_override)
        rng = random.Random(seed_used)

        tiles = self._prepare_tiles(image_paths, card_width, card_height, service.corner_radius)
        rng.shuffle(tiles)
        log(f"Prepared {len(tiles)} pre-scaled 16:9 tiles for rendering")

        scene_width, scene_height = self._scene_size(service, card_width, card_height)
        pitch = card_width + service.gap
        cards_per_row = max(8, min(14, math.ceil((service.output_width * 1.25) / pitch)))
        row_step = scene_height / service.row_count
        row_layers = self._build_row_layers(
            tiles=tiles,
            row_count=service.row_count,
            cards_per_row=cards_per_row,
            pitch=pitch,
            card_height=card_height,
            row_step=row_step,
            scene_width=scene_width,
        )
        phases = [rng.randrange(max(1, row.loop_width)) for row in row_layers]

        frame_count = service.loop_duration_seconds * service.fps
        if frame_count <= 0:
            raise RuntimeError("Frame count must be greater than 0")

        temp_dir = final_video_path.parent
        temp_video_path = temp_dir / f".{service.slug}.{uuid.uuid4().hex}.webm"
        temp_thumbnail_path = temp_dir / f".{service.slug}.{uuid.uuid4().hex}.jpg"

        crf = service.crf or QUALITY_PRESET_TO_CRF.get(service.quality_preset, 34)
        ffmpeg_command = self._ffmpeg_command(service, temp_video_path, crf)
        log(f"ffmpeg command: {' '.join(ffmpeg_command)}")

        process: subprocess.Popen[bytes] | None = None
        try:
            process = subprocess.Popen(
                ffmpeg_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            thumbnail_written = False
            for frame_index in range(frame_count):
                frame = self._render_frame(
                    service=service,
                    scene_width=scene_width,
                    scene_height=scene_height,
                    row_layers=row_layers,
                    phases=phases,
                    frame_index=frame_index,
                    frame_count=frame_count,
                )
                if not thumbnail_written:
                    frame.save(temp_thumbnail_path, format="JPEG", quality=90, optimize=True)
                    thumbnail_written = True
                if process.stdin is None:
                    raise RuntimeError("ffmpeg stdin unexpectedly unavailable")
                process.stdin.write(frame.tobytes())
                if frame_index % max(1, service.fps // 2) == 0:
                    progress(
                        55.0 + 40.0 * (frame_index / max(1, frame_count - 1)),
                        f"Encoded frame {frame_index + 1} of {frame_count}",
                    )
            if process.stdin:
                process.stdin.close()
            stderr_output = b""
            if process.stderr is not None:
                stderr_output = process.stderr.read()
            return_code = process.wait()

            if return_code != 0:
                raise RuntimeError(
                    f"ffmpeg failed with code {return_code}: {stderr_output.decode('utf-8', errors='replace')}"
                )

            if not temp_video_path.exists() or temp_video_path.stat().st_size < minimum_output_size_bytes:
                raise RuntimeError("Generated WebM is missing or unexpectedly small")

            os.replace(temp_video_path, final_video_path)
            if temp_thumbnail_path.exists():
                os.replace(temp_thumbnail_path, final_thumbnail_path)

            file_size = final_video_path.stat().st_size
            thumbnail_size = final_thumbnail_path.stat().st_size if final_thumbnail_path.exists() else 0
            progress(100.0, "Generation completed")
            log(f"Generated {final_video_path.name} ({file_size} bytes)")

            return RenderResult(
                output_path=final_video_path,
                thumbnail_path=final_thumbnail_path,
                file_size_bytes=file_size,
                thumbnail_size_bytes=thumbnail_size,
                duration_seconds=service.loop_duration_seconds,
                frame_count=frame_count,
                seed_used=seed_used,
                ffmpeg_command=ffmpeg_command,
                render_seconds=time.perf_counter() - started_at,
            )
        finally:
            if process and process.stdin:
                process.stdin.close()
            if temp_video_path.exists():
                temp_video_path.unlink(missing_ok=True)
            if temp_thumbnail_path.exists():
                temp_thumbnail_path.unlink(missing_ok=True)

    def _resolve_seed(self, service: ServiceConfig, seed_override: int | None) -> int:
        if seed_override is not None:
            return seed_override
        if service.seed is not None:
            return service.seed
        return int(time.time() * 1000) % 2_147_483_647

    def _preview_service(self, service: ServiceConfig) -> ServiceConfig:
        preview_width = min(service.output_width, 960)
        preview_height = max(1, int(round(preview_width * service.output_height / max(1, service.output_width))))
        scale = preview_width / max(1, service.output_width)
        preview_fps = max(12, min(18, service.fps))

        return service.model_copy(
            update={
                "output_width": preview_width,
                "output_height": preview_height,
                "loop_duration_seconds": service.loop_duration_seconds,
                "fps": preview_fps,
                "card_width": max(120, int(round(service.card_width * scale))),
                "gap": max(0, int(round(service.gap * scale))),
                "corner_radius": max(0, int(round(service.corner_radius * scale))),
                "cpu_used": min(8, max(service.cpu_used, 5)),
            }
        )

    def _prepare_tiles(
        self,
        image_paths: list[Path],
        card_width: int,
        card_height: int,
        corner_radius: int,
    ) -> list[Image.Image]:
        worker_count = max(1, min(len(image_paths), os.cpu_count() or 1))
        if worker_count == 1:
            return [self._prepare_tile(path, card_width, card_height, corner_radius) for path in image_paths]

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            return list(
                executor.map(
                    lambda path: self._prepare_tile(path, card_width, card_height, corner_radius),
                    image_paths,
                )
            )

    def _prepare_tile(self, image_path: Path, card_width: int, card_height: int, corner_radius: int) -> Image.Image:
        with Image.open(image_path) as image:
            source = image.convert("RGB")

        src_ratio = source.width / max(1, source.height)
        target_ratio = card_width / max(1, card_height)
        if src_ratio > target_ratio:
            new_height = source.height
            new_width = int(round(new_height * target_ratio))
            left = max(0, (source.width - new_width) // 2)
            top = 0
        else:
            new_width = source.width
            new_height = int(round(new_width / target_ratio))
            left = 0
            top = max(0, (source.height - new_height) // 2)

        cropped = source.crop((left, top, left + new_width, top + new_height))
        resized = cropped.resize((card_width, card_height), Image.Resampling.LANCZOS).convert("RGBA")
        if corner_radius <= 0:
            return resized

        mask = Image.new("L", (card_width, card_height), 0)
        drawer = ImageDraw.Draw(mask)
        drawer.rounded_rectangle(
            [(0, 0), (card_width - 1, card_height - 1)],
            radius=corner_radius,
            fill=255,
        )
        resized.putalpha(mask)
        return resized

    def _scene_size(self, service: ServiceConfig, card_width: int, card_height: int) -> tuple[int, int]:
        skew_x = abs(self._effective_skew_x(service))
        skew_y = abs(self._effective_skew_y(service))
        buffer_x = max(card_width * 2, int(service.output_width * 0.2 + service.output_height * skew_x + 120))
        buffer_y = max(card_height * 2, int(service.output_height * 0.2 + service.output_width * skew_y + 120))
        return service.output_width + (buffer_x * 2), service.output_height + (buffer_y * 2)

    def _build_row_layers(
        self,
        tiles: list[Image.Image],
        row_count: int,
        cards_per_row: int,
        pitch: int,
        card_height: int,
        row_step: float,
        scene_width: int,
    ) -> list[RowLayer]:
        row_layers: list[RowLayer] = []
        total_tiles = len(tiles)
        if total_tiles == 0:
            return row_layers

        for row_index in range(row_count):
            strip = Image.new("RGBA", (cards_per_row * pitch, card_height), (0, 0, 0, 0))
            row_offset = (row_index * cards_per_row) % total_tiles
            reverse_order = row_index % 2 == 1
            for card_index in range(cards_per_row):
                source_index = cards_per_row - 1 - card_index if reverse_order else card_index
                tile = tiles[(row_offset + source_index) % total_tiles]
                x = card_index * pitch
                strip.alpha_composite(tile, (x, 0))
            loop_width = strip.width
            repeat_count = math.ceil(scene_width / max(1, loop_width)) + 2
            band = Image.new("RGBA", (repeat_count * loop_width, card_height), (0, 0, 0, 0))
            for copy_index in range(repeat_count):
                band.alpha_composite(strip, (copy_index * loop_width, 0))
            y = int(round((row_step * row_index) + ((row_step - card_height) / 2)))
            row_layers.append(RowLayer(band=band, loop_width=loop_width, y=y))
        return row_layers

    def _render_frame(
        self,
        service: ServiceConfig,
        scene_width: int,
        scene_height: int,
        row_layers: list[RowLayer],
        phases: list[int],
        frame_index: int,
        frame_count: int,
    ) -> Image.Image:
        scene = Image.new("RGBA", (scene_width, scene_height), (0, 0, 0, 255))
        progress = frame_index / frame_count

        for row_index, row_layer in enumerate(row_layers):
            loop_width = row_layer.loop_width
            direction = 1 if row_index % 2 == 0 else -1
            pixel_shift = int(round(progress * loop_width))
            start_x = (phases[row_index] + (direction * pixel_shift)) % max(1, loop_width)
            row_view = row_layer.band.crop((start_x, 0, start_x + scene_width, row_layer.band.height))
            scene.paste(row_view, (0, row_layer.y), row_view)

        transformed = self._apply_global_transform(scene, service)
        left = max(0, (transformed.width - service.output_width) // 2)
        top = max(0, (transformed.height - service.output_height) // 2)
        cropped = transformed.crop((left, top, left + service.output_width, top + service.output_height))
        return cropped.convert("RGB")

    def _apply_global_transform(self, scene: Image.Image, service: ServiceConfig) -> Image.Image:
        transformed = scene

        if abs(service.zoom - 1.0) > 0.001:
            scaled_width = max(1, int(round(scene.width * service.zoom)))
            scaled_height = max(1, int(round(scene.height * service.zoom)))
            scaled = scene.resize((scaled_width, scaled_height), Image.Resampling.BICUBIC)
            canvas = Image.new("RGBA", scene.size, (0, 0, 0, 255))
            paste_x = (scene.width - scaled_width) // 2
            paste_y = (scene.height - scaled_height) // 2
            canvas.paste(scaled, (paste_x, paste_y), scaled)
            transformed = canvas

        skew_x = self._effective_skew_x(service)
        skew_y = self._effective_skew_y(service)
        if abs(skew_x) > 0.0001 or abs(skew_y) > 0.0001:
            center_x = transformed.width / 2
            center_y = transformed.height / 2
            transformed = transformed.transform(
                transformed.size,
                Image.Transform.AFFINE,
                (
                    1.0,
                    -skew_x,
                    skew_x * center_y,
                    -skew_y,
                    1.0,
                    skew_y * center_x,
                ),
                resample=Image.Resampling.BICUBIC,
                fillcolor=(0, 0, 0, 255),
            )

        if abs(service.rotate_z) > 0.0001:
            transformed = transformed.rotate(
                service.rotate_z,
                resample=Image.Resampling.BICUBIC,
                expand=False,
                fillcolor=(0, 0, 0, 255),
            )

        return transformed

    def _effective_skew_x(self, service: ServiceConfig) -> float:
        if abs(service.skew_x) > 0.0001:
            return service.skew_x
        return math.tan(math.radians(service.rotate_y)) * 0.18

    def _effective_skew_y(self, service: ServiceConfig) -> float:
        if abs(service.skew_y) > 0.0001:
            return service.skew_y
        return math.tan(math.radians(service.rotate_x)) * 0.08

    def _ffmpeg_command(self, service: ServiceConfig, output_path: Path, crf: int) -> list[str]:
        command = [
            self.ffmpeg_binary,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s:v",
            f"{service.output_width}x{service.output_height}",
            "-r",
            str(service.fps),
            "-i",
            "-",
            "-an",
        ]

        if service.codec == "vp8":
            bitrate = service.target_bitrate_kbps or 2000
            command.extend(
                [
                    "-c:v",
                    "libvpx",
                    "-threads",
                    str(max(1, os.cpu_count() or 1)),
                    "-pix_fmt",
                    "yuv420p",
                    "-crf",
                    str(max(4, min(63, crf))),
                    "-b:v",
                    f"{bitrate}k",
                ]
            )
        else:
            bitrate = service.target_bitrate_kbps or 0
            deadline = "good" if service.cpu_used <= 4 else "realtime"
            cpu_threads = max(1, os.cpu_count() or 1)
            tile_columns = 2 if cpu_threads >= 8 and service.output_width >= 1920 else 1 if cpu_threads >= 4 else 0
            command.extend(
                [
                    "-c:v",
                    "libvpx-vp9",
                    "-threads",
                    str(cpu_threads),
                    "-pix_fmt",
                    "yuv420p",
                    "-row-mt",
                    "1",
                    "-tile-columns",
                    str(tile_columns),
                    "-frame-parallel",
                    "1",
                    "-crf",
                    str(max(4, min(63, crf))),
                    "-b:v",
                    f"{bitrate}k" if bitrate else "0",
                    "-cpu-used",
                    str(service.cpu_used),
                    "-deadline",
                    deadline,
                    "-g",
                    "9999",
                ]
            )

        command.append(str(output_path))
        return command
