from .base import *  # noqa

DEBUG = True

try:
    import debug_toolbar  # noqa
    INSTALLED_APPS += ['debug_toolbar']  # noqa: F405
    MIDDLEWARE = ['debug_toolbar.middleware.DebugToolbarMiddleware'] + MIDDLEWARE  # noqa: F405
    INTERNAL_IPS = ['127.0.0.1']
except ImportError:
    pass

# Use console email backend in development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Relax security for local dev
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False
