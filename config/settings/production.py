from .base import *  # noqa
import environ

env = environ.Env()

# ── Security headers ──────────────────────────────────────────────────────────
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://unpkg.com https://cdnjs.cloudflare.com; "
    "style-src 'self' 'unsafe-inline' https://unpkg.com https://cdnjs.cloudflare.com; "
    "img-src 'self' data: blob: "
    "https://*.basemaps.cartocdn.com "
    "https://tile.openstreetmap.org https://*.tile.openstreetmap.org; "
    "connect-src 'self' https://api.weather.gov; "
    "font-src 'self' data:; "
    "frame-ancestors 'none';"
)

# Wire CSP + extra headers via middleware (insert after SecurityMiddleware)
MIDDLEWARE.insert(1, 'apps.core.middleware.SecurityHeadersMiddleware')  # noqa: F405

# ── Sentry ────────────────────────────────────────────────────────────────────
SENTRY_DSN = env('SENTRY_DSN', default='')
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
        environment='production',
    )
