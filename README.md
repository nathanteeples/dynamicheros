# Dynamic Heroes

Dynamic Heroes is a locally hosted Docker app that generates and serves seamless looping WebM hero backgrounds for streaming services using TMDB artwork. Each service keeps a stable URL such as `/heroes/netflix.webm`, while the file behind that URL can be regenerated on demand or on a configurable schedule.

The web dashboard is manual-first by default. You can generate a lighter draft preview clip before you commit to a full hosted WebM render, and automatic refresh stays off until you explicitly enable it. Preview timing matches the final render so motion speed is reflected accurately.

The renderer auto-detects the CPUs and memory visible inside the container and splits them between frame compositing and ffmpeg encoding. The Compose file intentionally does not cap CPU or memory, so the app uses the full resource budget Docker exposes to it.

## Features

- Stable hosted WebM and thumbnail URLs per streaming service
- Draft preview clips served from `/previews/<slug>.webm` before final render
- Server-side TMDB fetching, image caching, rendering, and WebM encoding
- Seamless horizontal row loops with pitch-based spacing math
- Per-service controls for provider ID, region, content mode, refresh interval, loop duration, codec, CRF, transforms, and render density
- Background scheduler with opt-in global enable plus per-service auto-refresh toggles
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
5. Review settings, click `Preview current settings`, and then click `Save + render final` when the look is right.

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

Preview assets are also available while you are tuning the look:

- `/previews/<slug>.webm`
- `/previews/<slug>.jpg`

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
- `POST /api/services/:slug/preview`
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
- `GET /previews/:slug.webm`
- `GET /previews/:slug.jpg`

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

Recommended defaults for faster hero backgrounds:

- Codec: VP9
- Resolution: 1280x720
- FPS: 30
- Loop duration: 90 seconds
- CRF: 34 for balanced output
- CRF: 38 for smaller files
- Lower motion density or fewer unique cards if output size is too large

## Docker resources

- `docker-compose.yml` does not set CPU or memory limits, so the container can use everything Docker makes available.
- The app auto-detects visible CPUs and cgroup memory and uses that to size render workers, ffmpeg threads, and the effective job concurrency.
- The dashboard's max concurrent jobs setting is treated as an upper bound, and the runtime may choose a lower number when that will finish renders faster on the detected machine.
- On Docker Desktop, the Docker Desktop resource settings are still the outer ceiling. If Docker is limited to 4 CPUs there, the container can only use those 4.

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
