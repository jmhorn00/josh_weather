# WxRadar

Live national weather radar for the United States. Station-centric UX built on Django.

- **National view** — MRMS composite mosaic (all 159 radars merged, 2-min updates)
- **Station view** — NEXRAD Level 2 reflectivity, dealiased velocity, MESH hail, 60-min nowcast
- **NWS alerts** — active watches/warnings/advisories nationwide, always on top

## Quick Start

```bash
git clone https://github.com/jmhorn00/josh_weather.git && cd josh_weather
cp .env.example .env          # fill in SECRET_KEY, DATABASE_URL, REDIS_URL
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
# in a second terminal:
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py seed_stations
```

Open `http://localhost:8000`.

## Stack

| Layer | Technology |
|-------|-----------|
| Framework | Django 5.x |
| Task queue | Celery 5 + Redis |
| Database | PostgreSQL 16 |
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
requirements/    base / dev / prod pip requirements
Dockerfile       Multi-stage build
docker-compose.yml          Production stack
docker-compose.dev.yml      Dev overrides (hot reload, debug)
Makefile         Common shortcuts
```

## Make Targets

```bash
make up           # Start dev stack
make migrate      # Apply migrations
make seed         # Seed 159 radar stations from NWS API
make test-mrms    # Smoke test MRMS → cfgrib pipeline
make logs         # Tail all service logs
make shell        # Django shell
make down         # Stop everything
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
