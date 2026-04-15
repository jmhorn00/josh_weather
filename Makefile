.PHONY: help up down build migrate seed collectstatic shell worker beat logs test clean

help:
	@echo "WxRadar — available make targets:"
	@echo "  up            Start all services (dev mode)"
	@echo "  down          Stop all services"
	@echo "  build         Build Docker images"
	@echo "  migrate       Run database migrations"
	@echo "  seed          Seed radar stations from NWS API"
	@echo "  collectstatic Collect static files"
	@echo "  shell         Open Django shell"
	@echo "  worker        Start Celery worker (foreground)"
	@echo "  beat          Start Celery beat (foreground)"
	@echo "  logs          Tail all service logs"
	@echo "  test          Run test suite"
	@echo "  test-mrms     Smoke test MRMS pipeline"
	@echo "  clean         Remove __pycache__ and .pyc files"

up:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up

up-prod:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

migrate:
	docker compose run --rm web python manage.py migrate

seed:
	docker compose run --rm web python manage.py seed_stations

collectstatic:
	docker compose run --rm web python manage.py collectstatic --noinput

shell:
	docker compose run --rm web python manage.py shell

worker:
	DJANGO_SETTINGS_MODULE=config.settings.development \
	celery -A config worker -l DEBUG --concurrency 2

beat:
	DJANGO_SETTINGS_MODULE=config.settings.development \
	celery -A config beat -l DEBUG --scheduler django_celery_beat.schedulers:DatabaseScheduler

logs:
	docker compose logs -f

test:
	docker compose run --rm web python -m pytest apps/

test-mrms:
	docker compose run --rm web python manage.py test_mrms

clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
