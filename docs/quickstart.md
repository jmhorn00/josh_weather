# Quickstart

Get WxRadar running locally in about 5 minutes using Docker Compose.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) 24+
- [Docker Compose](https://docs.docker.com/compose/) v2+
- Git

## Steps

### 1. Clone the repo

```bash
git clone https://github.com/jmhorn00/josh_weather.git
cd josh_weather
```

### 2. Create your `.env` file

```bash
cp .env.example .env
```

Open `.env` and set at minimum:

```env
SECRET_KEY=any-long-random-string-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgres://wxradar:changeme@db:5432/wxradar
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
POSTGRES_PASSWORD=changeme
```

All other variables have safe defaults for local development.

### 3. Build and start

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

This starts:
- `web` — Django dev server on port 8000
- `worker` — Celery worker (2 concurrent tasks)
- `beat` — Celery Beat scheduler
- `db` — PostgreSQL 16
- `redis` — Redis 7

### 4. Run migrations and seed stations

In a second terminal:

```bash
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py seed_stations
```

`seed_stations` fetches all 159 WSR-88D radar sites from the NWS API and populates the database. It takes about 10 seconds and is safe to re-run.

### 5. Create a superuser (optional, for admin access)

```bash
docker compose run --rm web python manage.py createsuperuser
```

Admin UI is at `http://localhost:8000/admin/`.

### 6. Open the app

Visit `http://localhost:8000` — you should see the national radar map.

The MRMS mosaic will appear within ~2 minutes once `beat` triggers `poll_mrms_mosaic` for the first time. You can trigger it immediately:

```bash
docker compose run --rm web python manage.py test_mrms
```

## Makefile Shortcuts

```bash
make up           # Start dev stack
make migrate      # Run migrations
make seed         # Seed 159 radar stations
make shell        # Django shell
make logs         # Tail all logs
make test-mrms    # Smoke test MRMS pipeline
make down         # Stop all services
```

## Next Steps

- [Full local setup without Docker](setup-local.md)
- [Production deployment](setup-production.md)
- [Configuration reference](configuration.md)
