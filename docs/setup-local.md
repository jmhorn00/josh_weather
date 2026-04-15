# Local Development Setup (without Docker)

Use this guide if you prefer to run Django, Celery, and Redis natively on your machine instead of inside Docker.

## System Requirements

- Python 3.12+
- PostgreSQL 16 (or 14+)
- Redis 7
- C build tools + scientific libraries (for Py-ART, cfgrib, PyHail)

## 1. Install system dependencies

### macOS (Homebrew)

```bash
brew install python@3.12 postgresql@16 redis
brew install hdf5 netcdf eccodes proj geos
brew services start postgresql@16
brew services start redis
```

### Ubuntu / Debian

```bash
sudo apt-get update && sudo apt-get install -y \
    python3.12 python3.12-venv python3.12-dev \
    postgresql-16 redis-server \
    libhdf5-dev libnetcdf-dev libeccodes-dev \
    libgeos-dev libproj-dev \
    gcc g++
sudo systemctl start postgresql redis
```

## 2. Create PostgreSQL database

```bash
sudo -u postgres psql -c "CREATE USER wxradar WITH PASSWORD 'wxradar';"
sudo -u postgres psql -c "CREATE DATABASE wxradar OWNER wxradar;"
```

## 3. Clone and set up Python environment

```bash
git clone https://github.com/jmhorn00/josh_weather.git
cd josh_weather

python3.12 -m venv .venv
source .venv/bin/activate

pip install -r requirements/dev.txt
```

> Installing `pyart-mch`, `pyhail`, and `pysteps` can take several minutes — they pull in numpy, scipy, and matplotlib.

## 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
SECRET_KEY=dev-secret-key-change-in-prod
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_SETTINGS_MODULE=config.settings.development

DATABASE_URL=postgres://wxradar:wxradar@localhost:5432/wxradar
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1

AWS_NEXRAD_BUCKET=noaa-nexrad-level2
AWS_MRMS_BUCKET=noaa-mrms-pds
AWS_REGION=us-east-1

NWS_USER_AGENT=(wxradar, yourname@example.com)

TILE_OUTPUT_DIR=/tmp/wxradar/tiles
SCAN_CACHE_DIR=/tmp/wxradar/scans
MRMS_CACHE_DIR=/tmp/wxradar/mrms
```

Create the data directories:

```bash
mkdir -p /tmp/wxradar/{tiles,scans,mrms}
```

## 5. Run migrations and seed stations

```bash
python manage.py migrate
python manage.py seed_stations
```

## 6. Start the services

You need three terminal windows running simultaneously:

### Terminal 1 — Django dev server

```bash
source .venv/bin/activate
DJANGO_SETTINGS_MODULE=config.settings.development python manage.py runserver
```

### Terminal 2 — Celery worker

```bash
source .venv/bin/activate
DJANGO_SETTINGS_MODULE=config.settings.development \
    celery -A config worker -l DEBUG --concurrency 2
```

### Terminal 3 — Celery Beat

```bash
source .venv/bin/activate
DJANGO_SETTINGS_MODULE=config.settings.development \
    celery -A config beat -l DEBUG \
    --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

Visit `http://127.0.0.1:8000` — the map should load immediately. MRMS data will appear within ~2 minutes.

## 7. Verify the pipeline

Run the MRMS smoke test to confirm cfgrib + eccodes are working:

```bash
python manage.py test_mrms
```

Expected output:
```
Fetching latest MRMS reflectivity key...
Latest key: CONUS/MergedReflectivityQC_00.00/20240101/MergedReflectivityQC...grib2.gz
Downloading...
Downloaded to /tmp/wxradar/mrms/MergedReflectivityQC...grib2.gz
Parsing grib2...
Dataset variables: ['unknown']
Rendering tile to /tmp/wxradar/tiles/test_mrms.png...
Success! Tile: /tmp/wxradar/tiles/test_mrms.png
Bounds: {'north': 54.99, 'south': 20.00, 'east': -60.01, 'west': -130.00}
```

## 8. Select a radar station

With the app running, click any radar marker on the map (or use the search box). The backend will:

1. Create an `ActiveStation` record
2. Download the latest NEXRAD Level 2 scan (~20 MB from S3)
3. Process it with Py-ART (velocity dealiasing + Cartesian gridding)
4. Render reflectivity + velocity PNG tiles
5. Run PyHail MESH
6. Queue nowcast if 4+ scans are available

First tile typically appears in 30–60 seconds.

## Common Issues

See [troubleshooting.md](troubleshooting.md) for fixes.

| Symptom | Likely cause |
|---------|-------------|
| `ModuleNotFoundError: eccodes` | `libeccodes-dev` not installed or not found |
| `OSError: HDF5 library version mismatch` | Multiple HDF5 versions on system |
| `redis.exceptions.ConnectionError` | Redis not running |
| Map loads but no tiles appear | Beat not running, or Celery worker not consuming tasks |
| `ProgrammingError: relation does not exist` | Migrations not applied |
