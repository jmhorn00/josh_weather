# WxRadar

Live national weather radar for the United States. Station-centric UX built on Django.

- **National view** — MRMS composite mosaic (all 159 radars merged, 2-min updates)
- **Station view** — NEXRAD Level 2 reflectivity, dealiased velocity, MESH hail, 60-min nowcast
- **NWS alerts** — active watches/warnings/advisories nationwide, always on top

## Local Development (Windows or macOS)

No Docker, no Redis, no Celery worker needed for basic development.

```bash
git clone https://github.com/jmhorn00/josh_weather.git
cd josh_weather

# Create and activate a virtual environment
python -m venv .venv

# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# Install dependencies (platform markers handle Windows vs macOS automatically)
pip install -r requirements/local.txt

# Configure environment
copy .env.example .env        # Windows
cp .env.example .env          # macOS / Linux
# Edit .env and set a SECRET_KEY (anything works for local dev)

# Set up the database and seed stations
python manage.py migrate
python manage.py seed_stations

# Start the dev server
python manage.py runserver
```

Open `http://127.0.0.1:8000`.

> **Windows note:** Radar processing tasks (NEXRAD Level 2, hail detection, nowcasting)
> require packages with no Windows wheels. Those features log a warning and return
> empty results on Windows. All other features work normally. Run the Docker stack
> for the full pipeline.

## Production (Docker)

```bash
cp .env.example .env   # fill in all production values
docker compose up -d
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py seed_stations
docker compose run --rm web python manage.py collectstatic --noinput
```

## Common Commands

| Task | Command |
|------|---------|
| Run dev server | `python manage.py runserver` |
| Apply migrations | `python manage.py migrate` |
| Seed radar stations | `python manage.py seed_stations` |
| Open Django shell | `python manage.py shell` |
| Run tests | `python -m pytest apps/` |
| Smoke test MRMS | `python manage.py test_mrms` |
| Backfill scans | `python manage.py backfill_scans` |
| Rebuild tiles | `python manage.py rebuild_tiles` |
| Collect static files | `python manage.py collectstatic` |
| Start Celery worker (Linux/macOS) | `celery -A config worker -l DEBUG` |
| Start Celery worker (Windows) | `celery -A config worker -l DEBUG -P solo` |
| Start Celery beat | `celery -A config beat -l DEBUG` |

## Stack

| Layer | Technology |
|-------|-----------|
| Framework | Django 5.x |
| Task queue | Celery 5 + Redis |
| Database | PostgreSQL 16 (SQLite for local dev) |
| National mosaic | MRMS — `s3://noaa-mrms-pds/` |
| Station radar | NEXRAD Level 2 — `s3://noaa-nexrad-level2/` |
| Radar processing | Py-ART, MetPy, xarray, cfgrib |
| Hail detection | PyHail (MESH) |
| Nowcasting | pysteps STEPS |
| Frontend map | Leaflet.js |
| Static files | Whitenoise |
| Reverse proxy | Traefik v3 (auto TLS) |
| Containers | Docker + Compose |

## Documentation

Full docs live in the [`docs/`](docs/) folder:

| Doc | Description |
|-----|-------------|
| [Quickstart](docs/quickstart.md) | Docker-based 5-minute setup |
| [Architecture](docs/architecture.md) | System design and data flow |
| [Local setup](docs/setup-local.md) | Dev setup without Docker |
| [Production deploy](docs/setup-production.md) | Docker + Traefik + TLS |
| [Configuration](docs/configuration.md) | All environment variables |
| [Data pipeline](docs/data-pipeline.md) | MRMS, NEXRAD, hail, nowcast details |
| [API reference](docs/api.md) | All REST endpoints |
| [Celery tasks](docs/celery-tasks.md) | Background task reference |
| [Management commands](docs/management-commands.md) | `seed_stations`, `backfill_scans`, etc. |
| [Frontend](docs/frontend.md) | JS architecture, Leaflet map guide |
| [Troubleshooting](docs/troubleshooting.md) | Common problems and fixes |

## Project Layout

```
config/          Django project (settings, URLs, Celery, WSGI)
apps/core/       Index view
apps/radar/      Models, views, tasks, services, admin, management commands
templates/       Django templates (map + admin dashboard)
static/          CSS + JS (no build step)
docs/            Documentation
requirements/    local / base / prod pip requirements
Dockerfile       Multi-stage build
docker-compose.yml          Production stack
docker-compose.dev.yml      Dev overrides (hot reload, debug)
```

## Data Sources

Both NOAA buckets are **public** — no AWS credentials needed.

| Source | Bucket | Update rate | Use |
|--------|--------|-------------|-----|
| MRMS | `s3://noaa-mrms-pds/` | 2 min | National mosaic |
| NEXRAD Level 2 | `s3://noaa-nexrad-level2/` | ~5 min | Per-station on-demand |
| NWS Alerts | `api.weather.gov/alerts/active` | 60 s | National alert polygons |

## License

MIT
