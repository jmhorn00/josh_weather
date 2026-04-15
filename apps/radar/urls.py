from django.urls import path, re_path
from . import views

urlpatterns = [
    # Station selector
    path('stations/', views.stations_list, name='stations-list'),
    path('stations/search/', views.stations_search, name='stations-search'),
    path('stations/nearest/', views.stations_nearest, name='stations-nearest'),
    path('stations/<str:code>/activate/', views.station_activate, name='station-activate'),
    path('stations/<str:code>/status/', views.station_status, name='station-status'),

    # MRMS national mosaic
    path('national/latest/', views.national_latest, name='national-latest'),
    path('national/frames/', views.national_frames, name='national-frames'),

    # Station-level NEXRAD
    path('station/<str:code>/latest/', views.station_latest, name='station-latest'),
    path('station/<str:code>/frames/', views.station_frames, name='station-frames'),
    path('station/<str:code>/hail/', views.station_hail, name='station-hail'),
    path('station/<str:code>/nowcast/', views.station_nowcast, name='station-nowcast'),

    # NWS alerts
    path('alerts/', views.alerts_geojson, name='alerts-geojson'),

    # Tile serving
    re_path(r'^tiles/(?P<tile_path>.+)$', views.serve_tile, name='serve-tile'),
]
