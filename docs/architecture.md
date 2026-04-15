# Architecture

## Overview

WxRadar is a 12-factor Django application that provides live national weather radar. It combines two NOAA data sources to give users both a seamless national view and high-resolution per-station data.

```
Browser
  │
  ▼
Traefik (TLS termination, reverse proxy)
  │
  ├── GET /           → Gunicorn → Django → Leaflet map page
  ├── GET /api/...    → Gunicorn → Django → JSON/GeoJSON API
  └── GET /api/radar/tiles/... → Gunicorn → Django → PNG tile files
                                                         ▲
                                              Docker volume (shared)
                                                         │
Redis (broker) ──→ Celery Worker ──→ NOAA S3 (unsigned)
                        │                 ├── s3://noaa-mrms-pds/
                        │                 └── s3://noaa-nexrad-level2/
                        │
                        └──→ PostgreSQL (state)
```

## Services

| Service | Role |
|---------|------|
| `web` | Gunicorn + Django — serves HTML, API, and tile files |
| `worker` | Celery worker — runs radar processing tasks |
| `beat` | Celery Beat — triggers periodic tasks on schedule |
| `db` | PostgreSQL 16 — stores station, scan, tile, alert metadata |
| `redis` | Redis 7 — Celery broker, result backend, Django cache |
| `traefik` | Reverse proxy — TLS termination, routing |

## Data Sources

### MRMS (always on)

**Multi-Radar/Multi-Sensor** — CONUS composite mosaic from all 159 radars merged into a single ~50 MB grib2 file updated every 2 minutes.

- Bucket: `s3://noaa-mrms-pds/` (public, unsigned access)
- Path: `CONUS/MergedReflectivityQC_00.00/YYYYMMDD/<filename>.grib2.gz`
- Format: gzip-compressed GRIB2, parsed with `cfgrib` via `xarray`
- Rendered to a single full-CONUS PNG tile
- `poll_mrms_mosaic` runs every 120 seconds via Beat
- Keeps last 30 frames (60 minutes) in the database

### NEXRAD Level 2 (on-demand)

**Individual station data** from WSR-88D radars. Only downloaded for stations the user has actively selected.

- Bucket: `s3://noaa-nexrad-level2/` (public, unsigned access)
- Path: `YYYY/MM/DD/KXXX/<filename>_V06`
- Format: NEXRAD Level 2 archive, parsed with `Py-ART`
- `poll_active_stations` runs every 90 seconds, only fetches data for stations in `ActiveStation` table
- Processed scans produce: reflectivity tile, velocity tile, MESH hail report, nowcast tiles

### NWS Alerts (always on)

- Endpoint: `https://api.weather.gov/alerts/active` (no key required)
- Returns all active US watches/warnings/advisories as GeoJSON
- `poll_nws_alerts` runs every 60 seconds
- Stored in `NWSAlert` table, expired records deleted automatically

## User Flow

```
1. Page load
   └── Fetch /api/radar/stations/ → plot 159 markers
   └── Load latest MRMS tile → display national mosaic
   └── Poll /api/radar/alerts/ → draw alert polygons

2. User selects station (click / search / geolocation)
   └── POST /api/radar/stations/<code>/activate/
       └── Creates ActiveStation record (TTL = 30 min)
       └── Immediately queues check_station_for_new_scans
   └── Frontend polls /api/radar/stations/<code>/status/ every 3s
   └── When scan arrives → load tiles → zoom map → draw range ring

3. While station is active (every 90s)
   └── Beat → poll_active_stations
       └── Queues check_station_for_new_scans for each active station
           └── Downloads new NEXRAD files not yet in DB
           └── process_nexrad_scan: Py-ART → tiles → MESH → nowcast

4. Frontend keep-alive
   └── Every 10 min: POST activate again to reset TTL
   └── Every 90s: check for newer tiles

5. Station deactivation
   └── ActiveStation.expires_at passes → poll_active_stations deletes it
   └── cleanup_old_data (hourly) removes scan files + tiles
```

## Processing Pipeline (per NEXRAD scan)

```
S3 key
  │
  ▼
download_nexrad() → local file (~20 MB)
  │
  ▼
pyart.io.read_nexrad_archive() → Radar object
  │
  ├── dealias_region_based() → dealiased velocity field
  │
  ▼
grid_from_radars() → Cartesian Grid (500×500 km, 1 km resolution)
  │
  ├── render_reflectivity_tile() → PNG + bounds → RadarTile
  ├── render_velocity_tile()    → PNG + bounds → RadarTile
  │
  └── calculate_mesh()          → GeoJSON + max_mm → HailReport
          │
          └── (if 4+ scans) generate_nowcast()
                  │
                  └── pysteps STEPS → 12 × 5-min forecast arrays
                          └── render_nowcast_tile() × 12 → RadarTile
```

## Directory Structure

```
josh_weather/
├── config/                    # Django project config
│   ├── settings/
│   │   ├── base.py            # Shared settings (12-factor)
│   │   ├── development.py     # Dev overrides
│   │   └── production.py      # Prod overrides (security, Sentry)
│   ├── urls.py
│   ├── celery.py              # Celery app + Beat schedule
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── core/                  # Index view only
│   └── radar/
│       ├── models.py          # All 7 database models
│       ├── views.py           # All API views
│       ├── urls.py            # All URL routes
│       ├── tasks.py           # All Celery tasks
│       ├── admin.py           # Admin registrations
│       ├── services/          # Business logic (no Django deps)
│       │   ├── s3.py          # NOAA S3 access
│       │   ├── mrms.py        # MRMS grib2 parse + render
│       │   ├── processor.py   # Py-ART NEXRAD processing
│       │   ├── tiles.py       # PNG tile rendering
│       │   ├── hail.py        # PyHail MESH
│       │   ├── nowcast.py     # pysteps STEPS
│       │   └── alerts.py      # NWS alerts fetch + parse
│       └── management/
│           └── commands/      # seed_stations, backfill_scans, etc.
├── templates/
│   ├── base.html
│   └── core/map.html
├── static/
│   ├── css/map.css
│   └── js/
│       ├── radar_map.js       # Core map logic
│       ├── station_selector.js
│       ├── alerts.js
│       └── radar_animate.js
├── docs/                      # This documentation
├── requirements/
│   ├── base.txt
│   ├── dev.txt
│   └── prod.txt
├── Dockerfile
├── docker-compose.yml
├── docker-compose.dev.yml
└── Makefile
```

## Technology Choices

| Choice | Reason |
|--------|--------|
| **MRMS for national view** | Single file covers all CONUS — no stitching needed |
| **NEXRAD Level 2 on-demand** | 159 stations × 24h polling = ~500 GB/day; on-demand keeps it lean |
| **Py-ART** | De facto standard for NEXRAD Level 2 parsing in Python |
| **cfgrib + xarray** | Best GRIB2 support in Python ecosystem |
| **pysteps STEPS** | Open-source nowcasting with ensemble support |
| **PyHail** | Pure-Python MESH implementation, no dependencies on WSR-88D-specific libs |
| **Leaflet** | Lightweight, no API key, excellent ImageOverlay + GeoJSON support |
| **Redis** | Dual role: Celery broker + Django cache (two DB indexes) |
| **Traefik** | Auto TLS from Let's Encrypt via Docker labels — zero config |
