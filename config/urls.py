from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from apps.radar.admin import admin_site

urlpatterns = [
    path('admin/', admin_site.urls),
    path('', include('apps.core.urls')),
    path('api/radar/', include('apps.radar.urls')),
]

if settings.DEBUG:
    try:
        import debug_toolbar
        urlpatterns = [path('__debug__/', include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass
