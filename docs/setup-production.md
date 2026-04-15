# Production Deployment

This guide covers deploying WxRadar to a Linux server using Docker Compose, Traefik (with automatic TLS), and a domain name.

## Server Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB |
| Disk | 50 GB | 100 GB |
| OS | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |
| Open ports | 80, 443 | 80, 443 |

> **Disk note:** Each active station can consume ~5.7 GB/day of scan files. With 5 concurrent stations the data volume runs to ~30 GB/day before cleanup. The `cleanup_old_data` task (runs hourly) prunes files older than 24 hours.

## 1. Install Docker on the server

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

Verify:
```bash
docker --version   # Docker 24+
docker compose version  # v2+
```

## 2. Point your domain to the server

Create an A record:
```
yourdomain.com  →  <your server IP>
```

Wait for DNS to propagate before proceeding (Traefik needs port 80 available to complete ACME challenge).

## 3. Clone the repo

```bash
git clone https://github.com/jmhorn00/josh_weather.git
cd josh_weather
```

## 4. Create the production `.env`

```bash
cp .env.example .env
nano .env
```

Fill in all values:

```env
# Django
SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_urlsafe(50))">
DEBUG=False
ALLOWED_HOSTS=yourdomain.com
DJANGO_SETTINGS_MODULE=config.settings.production

# Database
DATABASE_URL=postgres://wxradar:${POSTGRES_PASSWORD}@db:5432/wxradar
POSTGRES_PASSWORD=<strong-random-password>

# Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1

# AWS (NOAA public buckets — no credentials needed)
AWS_NEXRAD_BUCKET=noaa-nexrad-level2
AWS_MRMS_BUCKET=noaa-mrms-pds
AWS_REGION=us-east-1

# MRMS
MRMS_POLL_INTERVAL=120

# NEXRAD
STATION_POLL_INTERVAL=90
STATION_SCAN_TTL=1800
NOWCAST_TIMESTEPS=12
HAIL_MESH_THRESHOLD=25

# NWS Alerts
NWS_ALERTS_POLL_INTERVAL=60
NWS_USER_AGENT=(wxradar, your-contact@email.com)

# Storage (inside container — mapped to Docker volumes)
TILE_OUTPUT_DIR=/app/data/tiles
SCAN_CACHE_DIR=/app/data/scans
MRMS_CACHE_DIR=/app/data/mrms
STATIC_ROOT=/app/staticfiles
MEDIA_ROOT=/app/media

# Traefik / TLS
DOMAIN=yourdomain.com
ACME_EMAIL=your-contact@email.com

# Sentry (optional — error tracking)
SENTRY_DSN=
```

## 5. Update `docker-compose.yml` with your domain

The domain is read from the `DOMAIN` env var. If you want to hardcode it:

```yaml
labels:
  - "traefik.http.routers.wxradar.rule=Host(`yourdomain.com`)"
```

## 6. Build and start

```bash
docker compose build
docker compose up -d
```

Check that all containers are healthy:

```bash
docker compose ps
```

Expected output:
```
NAME          STATUS          PORTS
wxradar-web   Up (healthy)
wxradar-worker Up
wxradar-beat  Up
wxradar-db    Up (healthy)
wxradar-redis Up (healthy)
wxradar-traefik Up            0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
```

## 7. Run first-time setup

```bash
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py seed_stations
docker compose run --rm web python manage.py createsuperuser
```

## 8. Verify TLS

```bash
curl -I https://yourdomain.com
# HTTP/2 200
```

Traefik auto-renews the Let's Encrypt certificate before it expires.

## 9. Verify MRMS pipeline

```bash
docker compose run --rm web python manage.py test_mrms
```

## Logs

```bash
# All services
docker compose logs -f

# Individual service
docker compose logs -f worker
docker compose logs -f beat
docker compose logs -f web
```

## Updating

```bash
git pull origin main
docker compose build
docker compose up -d
docker compose run --rm web python manage.py migrate
```

## Backups

### PostgreSQL

```bash
# Manual backup
docker compose exec db pg_dump -U wxradar wxradar > backup_$(date +%Y%m%d).sql

# Restore
docker compose exec -T db psql -U wxradar wxradar < backup_20240101.sql
```

### Volumes

Tile and scan data is ephemeral (auto-cleaned every 24h) and does not need backing up. Only the PostgreSQL volume (`pg_data`) contains persistent state.

## Scaling Workers

To handle more concurrent stations, increase Celery worker concurrency:

```bash
# In docker-compose.yml
command: celery -A config worker -l INFO --concurrency 8
```

Or scale to multiple worker containers:

```bash
docker compose up -d --scale worker=3
```

## Firewall

Only ports 80 and 443 should be exposed. Block everything else:

```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP (for ACME challenge + redirect)
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

## Security Checklist

- [ ] `DEBUG=False` in `.env`
- [ ] Strong `SECRET_KEY` (50+ chars, random)
- [ ] Strong `POSTGRES_PASSWORD`
- [ ] `.env` not committed to git (it's in `.gitignore`)
- [ ] `ALLOWED_HOSTS` set to your domain only
- [ ] Firewall configured (ports 80 + 443 only)
- [ ] Sentry DSN configured for error tracking
- [ ] Regular PostgreSQL backups scheduled
