# Dynamic Heroes

Dynamic Heroes is a locally hosted Docker app that generates and serves seamless looping WebM hero backgrounds for streaming services using TMDB artwork. Each service keeps a stable URL such as `/heroes/netflix.webm`, while the file behind that URL is regenerated on a configurable schedule.

The web dashboard always previews the exact generated WebM file that is being hosted. Rendering and encoding happen server-side with Pillow and `ffmpeg`, not in the browser.

## Features

- Stable hosted WebM and thumbnail URLs per streaming service
- Server-side TMDB fetching, image caching, rendering, and WebM encoding
- Seamless horizontal row loops with pitch-based spacing math
- Per-service controls for provider ID, region, content mode, refresh interval, loop duration, codec, CRF, transforms, and render density
- Background scheduler with manual regenerate buttons and retry cooldowns
- Atomic output replacement so a failed render never removes the last working file
- JSON-backed settings and state with no heavyweight database required
- API endpoints for settings, services, jobs, logs, and hosted assets

## Stack

- Backend: FastAPI
- Rendering: Pillow
- Encoding: ffmpeg (`libvpx-vp9` by default, `libvpx` fallback)
- Persistence: JSON files under `/app/data`
- Caching: local filesystem under `/app/cache`
- Hosted output: local filesystem under `/app/output`

## Quick start

1. Create a `.env` file from `.env.example`.
2. Add either `TMDB_BEARER_TOKEN` or `TMDB_API_KEY`.
3. Start the app:

```bash
docker compose up -d
```

4. Open [http://localhost:8080](http://localhost:8080).
5. Review settings, then click `Regenerate` on a service.

## TMDB credentials

You can use either:

- A TMDB Bearer token
- A TMDB v3 API key

Environment variables are preferred because the dashboard stores settings locally in `data/settings.json`.

## Default services

The app ships with these service slugs and provider IDs:

- `apple-tv`: 350
- `netflix`: 8
- `disney`: 337
- `prime-video`: 9
- `max`: 1899
- `paramount`: 531
- `hulu`: 15
- `peacock`: 386

Provider IDs are editable in the dashboard because TMDB watch providers can vary by region.

## Output URLs

Once a service has generated successfully, these URLs are available:

- `/heroes/<slug>.webm`
- `/heroes/<slug>.jpg`

Examples:

- `/heroes/apple-tv.webm`
- `/heroes/netflix.webm`
- `/heroes/disney.webm`

The URL stays fixed while the app atomically swaps in a newly generated file after each successful refresh.

## Rendering notes

- The generator uses a black background.
- Cards are pre-scaled to 16:9 once per generation and reused across all frames.
- Every row is built as a repeated strip whose loop width is `card_count * (card_width + gap)`.
- Frame motion advances by exactly one strip width across one loop duration.
- The renderer does not duplicate the first frame at the end of the encoded video.
- Edge cards are intentionally allowed to cut off.
- `rotateX` and `rotateY` are approximated with affine skew for a lighter-weight server-side perspective effect.

## API

Metadata and control:

- `GET /api/settings`
- `PUT /api/settings`
- `GET /api/services`
- `GET /api/services/:slug`
- `POST /api/services/:slug/regenerate`
- `POST /api/regenerate-all`
- `GET /api/jobs`
- `GET /api/logs`

Compatibility aliases:

- `GET /api/heroes`
- `GET /api/heroes/:slug`

Hosted assets:

- `GET /heroes/:slug.webm`
- `GET /heroes/:slug.jpg`

## Files and persistence

The Docker Compose setup mounts these local directories:

- `./data` -> `/app/data`
- `./cache` -> `/app/cache`
- `./output` -> `/app/output`

Important files:

- `data/settings.json`: persisted dashboard settings
- `data/state.json`: generation metadata and last known status
- `data/logs/*.log`: per-service structured logs
- `config/settings.sample.json`: sample default configuration

## Quality guidance

Recommended defaults for 1080p backgrounds:

- Codec: VP9
- FPS: 24 or 30
- Loop duration: 90 seconds
- CRF: 34 for balanced output
- CRF: 38 for smaller files
- Lower motion density or fewer unique cards if output size is too large

## Local development without Docker

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## Limitations

- True 3D perspective is approximated with skew transforms instead of a full 3D renderer.
- VP9 WebM playback support is best in Chromium-based browsers and Firefox. Some browsers have more limited support.
- TMDB "title card" selection is heuristic and based primarily on backdrop language preference and backdrop availability.
