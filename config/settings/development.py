from .base import *  # noqa

DEBUG = True

try:
    import debug_toolbar  # noqa
    INSTALLED_APPS += ['debug_toolbar']  # noqa: F405
    MIDDLEWARE = ['debug_toolbar.middleware.DebugToolbarMiddleware'] + MIDDLEWARE  # noqa: F405
    INTERNAL_IPS = ['127.0.0.1']
except ImportError:
    pass

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False

# Local dev: in-memory cache so Redis is not required
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# Run Celery tasks inline (no broker or worker process needed locally)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
