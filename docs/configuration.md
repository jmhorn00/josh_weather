# Configuration Reference

All configuration is via environment variables using `django-environ`. Copy `.env.example` to `.env` and fill in the values. **Never commit `.env` to git.**

## Django Core

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | Yes | — | Django secret key. Generate with `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DEBUG` | No | `False` | Enable Django debug mode. **Must be `False` in production.** |
| `ALLOWED_HOSTS` | Yes | `localhost,127.0.0.1` | Comma-separated list of allowed hostnames |
| `DJANGO_SETTINGS_MODULE` | No | `config.settings.production` | Settings module to use |

## Database

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | `sqlite:///db.sqlite3` | Database connection URL. Format: `postgres://user:pass@host:port/dbname` |

Supported URL schemes: `postgres://`, `postgresql://`, `sqlite:///`.

## Redis

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `REDIS_URL` | No | `redis://localhost:6379/0` | Redis URL for Django cache and Celery result backend |
| `CELERY_BROKER_URL` | No | `redis://localhost:6379/1` | Redis URL for Celery task broker. Use a separate DB index from `REDIS_URL` |

## AWS / NOAA S3

All NOAA radar buckets are public and require no credentials. The boto3 client uses `UNSIGNED` config automatically.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AWS_NEXRAD_BUCKET` | No | `noaa-nexrad-level2` | NEXRAD Level 2 S3 bucket name |
| `AWS_MRMS_BUCKET` | No | `noaa-mrms-pds` | MRMS S3 bucket name |
| `AWS_REGION` | No | `us-east-1` | AWS region for boto3 client (always `us-east-1` for NOAA buckets) |

## MRMS National Mosaic

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MRMS_POLL_INTERVAL` | No | `120` | Seconds between MRMS S3 checks. MRMS updates every ~2 min so 120s is optimal |

## NEXRAD Per-Station

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `STATION_POLL_INTERVAL` | No | `90` | Seconds between active station scan checks |
| `STATION_SCAN_TTL` | No | `1800` | Seconds to keep polling after last user activity (30 min). Frontend re-POSTs activate every `TTL/3` seconds |
| `NOWCAST_TIMESTEPS` | No | `12` | Number of 5-minute nowcast forecast steps (12 = 60 min) |
| `HAIL_MESH_THRESHOLD` | No | `25.0` | MESH threshold in mm above which hail is considered significant and included in GeoJSON output |

## NWS Alerts

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NWS_ALERTS_POLL_INTERVAL` | No | `60` | Seconds between NWS alert API polls |
| `NWS_USER_AGENT` | Yes | `(wxradar, contact@youremail.com)` | User-Agent header sent to `api.weather.gov`. NWS requires a contact email. Change this to your own. |

## Storage Paths

All paths are inside the container. These directories are mapped to Docker named volumes in production.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TILE_OUTPUT_DIR` | No | `/app/data/tiles` | Where rendered PNG tiles are written. Shared between `web` and `worker` containers |
| `SCAN_CACHE_DIR` | No | `/app/data/scans` | Where downloaded NEXRAD Level 2 files are cached |
| `MRMS_CACHE_DIR` | No | `/app/data/mrms` | Where downloaded MRMS grib2 files are cached |
| `STATIC_ROOT` | No | `<BASE_DIR>/staticfiles` | Where `collectstatic` writes files for Whitenoise |
| `MEDIA_ROOT` | No | `<BASE_DIR>/media` | Django media root (not used for tiles) |

## Production Only

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SENTRY_DSN` | No | `""` | Sentry DSN for error tracking. Leave blank to disable. |
| `POSTGRES_PASSWORD` | Yes (prod) | `changeme` | PostgreSQL password, referenced by `DATABASE_URL` and Docker Compose `db` service |
| `DOMAIN` | No | `localhost` | Domain name, used in Traefik Docker labels |
| `ACME_EMAIL` | No | `admin@example.com` | Email for Let's Encrypt certificate notifications |

## Example `.env` Files

### Minimal development

```env
SECRET_KEY=dev-only-not-for-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgres://wxradar:wxradar@localhost:5432/wxradar
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
NWS_USER_AGENT=(wxradar, dev@example.com)
TILE_OUTPUT_DIR=/tmp/wxradar/tiles
SCAN_CACHE_DIR=/tmp/wxradar/scans
MRMS_CACHE_DIR=/tmp/wxradar/mrms
```

### Full production

```env
SECRET_KEY=<50-char-random-string>
DEBUG=False
ALLOWED_HOSTS=radar.yourdomain.com
DJANGO_SETTINGS_MODULE=config.settings.production
DATABASE_URL=postgres://wxradar:strongpass@db:5432/wxradar
POSTGRES_PASSWORD=strongpass
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
AWS_NEXRAD_BUCKET=noaa-nexrad-level2
AWS_MRMS_BUCKET=noaa-mrms-pds
AWS_REGION=us-east-1
MRMS_POLL_INTERVAL=120
STATION_POLL_INTERVAL=90
STATION_SCAN_TTL=1800
NOWCAST_TIMESTEPS=12
HAIL_MESH_THRESHOLD=25
NWS_ALERTS_POLL_INTERVAL=60
NWS_USER_AGENT=(wxradar, your-contact@yourdomain.com)
TILE_OUTPUT_DIR=/app/data/tiles
SCAN_CACHE_DIR=/app/data/scans
MRMS_CACHE_DIR=/app/data/mrms
STATIC_ROOT=/app/staticfiles
MEDIA_ROOT=/app/media
DOMAIN=radar.yourdomain.com
ACME_EMAIL=your-contact@yourdomain.com
SENTRY_DSN=https://abc123@sentry.io/456
```
