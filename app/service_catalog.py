from __future__ import annotations

from typing import Final


DEFAULT_SERVICE_DEFINITIONS: Final[list[dict[str, int | str]]] = [
    {"slug": "apple-tv", "name": "Apple TV+", "provider_id": 350},
    {"slug": "netflix", "name": "Netflix", "provider_id": 8},
    {"slug": "disney", "name": "Disney+", "provider_id": 337},
    {"slug": "prime-video", "name": "Prime Video", "provider_id": 9},
    {"slug": "max", "name": "Max", "provider_id": 1899},
    {"slug": "paramount", "name": "Paramount+", "provider_id": 531},
    {"slug": "hulu", "name": "Hulu", "provider_id": 15},
    {"slug": "peacock", "name": "Peacock", "provider_id": 386},
]
