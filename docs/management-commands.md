# Management Commands

Run all commands with:
```bash
# Docker
docker compose run --rm web python manage.py <command>

# Local
DJANGO_SETTINGS_MODULE=config.settings.development python manage.py <command>
```

---

## `seed_stations`

Fetches all WSR-88D radar stations from the NWS API and populates the `RadarStation` table.

```bash
python manage.py seed_stations
```

**What it does:**
1. `GET https://api.weather.gov/radar/stations`
2. Filters to `stationType == 'WSR-88D'`
3. Parses `stationIdentifier`, `name`, coordinates (GeoJSON: `[lon, lat]`), elevation
4. `RadarStation.objects.update_or_create(code=...)` — safe to re-run

**Output:**
```
Fetching radar stations from NWS API...
Received 164 features from NWS API
Done. Created: 159, Updated: 0, Skipped (non-WSR-88D): 5
```

**When to run:** Once after initial migration. Re-run after adding new stations or fixing data.

---

## `backfill_scans`

Downloads and processes the last N hours of NEXRAD Level 2 scans for a station. Useful for recovering after downtime or loading historical data for testing.

```bash
python manage.py backfill_scans --station KTLX --hours 6
```

**Arguments:**

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--station` | Yes | — | Station code (e.g. `KTLX`) |
| `--hours` | No | `6` | How many hours back to fetch |

**What it does:**
1. Lists NEXRAD S3 keys for the station over the last N hours
2. Filters to only keys within the time window
3. Queues `process_nexrad_scan.delay(code, key)` for each

The actual processing happens asynchronously in Celery workers. Monitor progress with:
```bash
docker compose logs -f worker
```

**When to run:**
- After the worker was down and you missed scans
- When testing the NEXRAD processing pipeline for the first time
- When you want data for a specific past event

---

## `rebuild_tiles`

Re-renders PNG tiles from already-cached scan files. Run this after changing color scales or rendering code.

```bash
python manage.py rebuild_tiles --station KTLX --hours 6
```

**Arguments:**

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--station` | Yes | — | Station code |
| `--hours` | No | `6` | How many hours of cached scans to rebuild |

**What it does:**
1. Queries `RadarScan` records with `processed=True` and `local_path` set
2. For each: runs full Py-ART processing → `render_reflectivity_tile` + `render_velocity_tile`
3. Updates `RadarTile` records

**Note:** Only works if scan files still exist locally (`SCAN_CACHE_DIR`). Files are cleaned up after 24 hours.

---

## `test_mrms`

Downloads the latest MRMS reflectivity grib2 file and renders one CONUS PNG tile. Smoke test for the full MRMS → cfgrib → matplotlib pipeline.

```bash
python manage.py test_mrms
```

**Expected output:**
```
Fetching latest MRMS reflectivity key...
Latest key: CONUS/MergedReflectivityQC_00.00/20240115/MergedReflectivityQC_00.00_20240115-184200.grib2.gz
Downloading...
Downloaded to /app/data/mrms/MergedReflectivityQC_00.00_20240115-184200.grib2.gz
Parsing grib2...
Dataset variables: ['unknown']
Rendering tile to /app/data/tiles/test_mrms.png...
Success! Tile: /app/data/tiles/test_mrms.png
Bounds: {'north': 54.99, 'south': 20.00, 'east': -60.01, 'west': -130.00}
```

**If it fails:**
- `No MRMS key found` → S3 connectivity issue or boto3 not installed
- `ModuleNotFoundError: cfgrib` → `pip install cfgrib` or check Docker build
- `eccodes not found` → `libeccodes2` not installed (or `libeccodes-dev` in builder)

---

## Standard Django Commands

These work as normal:

```bash
# Apply migrations
python manage.py migrate

# Create superuser (for /admin/)
python manage.py createsuperuser

# Collect static files (done automatically in Docker build)
python manage.py collectstatic --noinput

# Django shell
python manage.py shell

# Check configuration
python manage.py check

# Show all available commands
python manage.py help
```
