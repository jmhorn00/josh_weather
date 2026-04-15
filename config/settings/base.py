import environ
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / '.env')

SECRET_KEY = env('SECRET_KEY')
DEBUG = env.bool('DEBUG', default=False)
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    'django_celery_beat',
    'apps.core',
    'apps.radar',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DATABASES = {'default': env.db('DATABASE_URL', default='sqlite:///db.sqlite3')}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': env('REDIS_URL', default='redis://localhost:6379/0'),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = env('STATIC_ROOT', default=str(BASE_DIR / 'staticfiles'))
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = env('MEDIA_ROOT', default=str(BASE_DIR / 'media'))

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Celery ──────────────────────────────────────────────────────────────────
CELERY_BROKER_URL = env('CELERY_BROKER_URL', default='redis://localhost:6379/1')
CELERY_RESULT_BACKEND = env('REDIS_URL', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# ── Radar / Data directories ─────────────────────────────────────────────────
TILE_OUTPUT_DIR = env('TILE_OUTPUT_DIR', default=str(BASE_DIR / 'data' / 'tiles'))
SCAN_CACHE_DIR = env('SCAN_CACHE_DIR', default=str(BASE_DIR / 'data' / 'scans'))
MRMS_CACHE_DIR = env('MRMS_CACHE_DIR', default=str(BASE_DIR / 'data' / 'mrms'))

# ── AWS (NOAA public buckets — no credentials) ───────────────────────────────
AWS_NEXRAD_BUCKET = env('AWS_NEXRAD_BUCKET', default='noaa-nexrad-level2')
AWS_MRMS_BUCKET = env('AWS_MRMS_BUCKET', default='noaa-mrms-pds')
AWS_REGION = env('AWS_REGION', default='us-east-1')

# ── Task poll intervals ──────────────────────────────────────────────────────
MRMS_POLL_INTERVAL = env.int('MRMS_POLL_INTERVAL', default=120)
STATION_POLL_INTERVAL = env.int('STATION_POLL_INTERVAL', default=90)
STATION_SCAN_TTL = env.int('STATION_SCAN_TTL', default=1800)
NOWCAST_TIMESTEPS = env.int('NOWCAST_TIMESTEPS', default=12)
HAIL_MESH_THRESHOLD = env.float('HAIL_MESH_THRESHOLD', default=25.0)

# ── NWS Alerts ───────────────────────────────────────────────────────────────
NWS_ALERTS_POLL_INTERVAL = env.int('NWS_ALERTS_POLL_INTERVAL', default=60)
NWS_USER_AGENT = env('NWS_USER_AGENT', default='(wxradar, contact@youremail.com)')

# ── Logging (Factor XI — stdout only) ────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {
        'apps.radar': {'level': 'DEBUG', 'handlers': ['console'], 'propagate': False},
        'apps.core': {'level': 'INFO', 'handlers': ['console'], 'propagate': False},
        'celery': {'level': 'INFO', 'handlers': ['console'], 'propagate': False},
    },
}
