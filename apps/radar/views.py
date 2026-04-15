import json
import logging
import math
import os
from datetime import timedelta

from django.conf import settings
from django.http import JsonResponse, FileResponse, Http404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import (
    RadarStation, ActiveStation, MRMSTile, RadarScan, RadarTile,
    HailReport, NWSAlert,
)

logger = logging.getLogger(__name__)


# ── Station Selector ──────────────────────────────────────────────────────────

def stations_list(request):
    stations = RadarStation.objects.filter(is_active=True).values(
        'code', 'name', 'state', 'latitude', 'longitude', 'region'
    )
    return JsonResponse(list(stations), safe=False)


def stations_search(request):
    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse([], safe=False)

    from django.db.models import Q
    qs = RadarStation.objects.filter(is_active=True).filter(
        Q(code__icontains=q) | Q(name__icontains=q) | Q(state__icontains=q)
    ).values('code', 'name', 'state', 'latitude', 'longitude', 'region')[:10]
    return JsonResponse(list(qs), safe=False)


def stations_nearest(request):
    try:
        lat = float(request.GET['lat'])
        lon = float(request.GET['lon'])
    except (KeyError, ValueError):
        return JsonResponse({'error': 'lat and lon are required'}, status=400)

    stations = list(RadarStation.objects.filter(is_active=True).values(
        'code', 'name', 'state', 'latitude', 'longitude', 'region'
    ))

    def haversine(s):
        R = 6371.0
        lat1, lon1 = math.radians(lat), math.radians(lon)
        lat2, lon2 = math.radians(s['latitude']), math.radians(s['longitude'])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 2 * R * math.asin(math.sqrt(a))

    for s in stations:
        s['distance_km'] = round(haversine(s), 1)

    stations.sort(key=lambda s: s['distance_km'])
    return JsonResponse(stations[:3], safe=False)


@require_http_methods(['POST'])
def station_activate(request, code):
    try:
        station = RadarStation.objects.get(code=code.upper(), is_active=True)
    except RadarStation.DoesNotExist:
        return JsonResponse({'error': 'Station not found'}, status=404)

    ttl = settings.STATION_SCAN_TTL
    expires_at = timezone.now() + timedelta(seconds=ttl)
    ActiveStation.objects.update_or_create(
        station=station,
        defaults={'expires_at': expires_at},
    )

    from .tasks import check_station_for_new_scans
    check_station_for_new_scans.delay(station.code)

    return JsonResponse({
        'status': 'activated',
        'station': {
            'code': station.code,
            'name': station.name,
            'state': station.state,
            'latitude': station.latitude,
            'longitude': station.longitude,
        },
        'eta_seconds': 30,
    })


def station_status(request, code):
    try:
        station = RadarStation.objects.get(code=code.upper())
    except RadarStation.DoesNotExist:
        return JsonResponse({'error': 'Station not found'}, status=404)

    is_active = ActiveStation.objects.filter(
        station=station, expires_at__gt=timezone.now()
    ).exists()

    one_hour_ago = timezone.now() - timedelta(hours=1)
    scan_count = RadarScan.objects.filter(
        station=station, scan_time__gte=one_hour_ago
    ).count()

    processing = RadarScan.objects.filter(station=station, processed=False).exists()

    return JsonResponse({
        'is_active': is_active,
        'last_scan_time': station.last_scan_time.isoformat() if station.last_scan_time else None,
        'scan_count_last_hour': scan_count,
        'processing': processing,
    })


# ── MRMS National Mosaic ──────────────────────────────────────────────────────

def national_latest(request):
    product = request.GET.get('product', 'reflectivity')
    tile = MRMSTile.objects.filter(product=product, processed=True).first()
    if not tile:
        return JsonResponse({'error': 'No tiles available'}, status=404)
    return JsonResponse({
        'valid_time': tile.valid_time.isoformat(),
        'tile_url': f'/api/radar/tiles/{tile.tile_path}',
        'bounds': tile.bounds_json,
    })


def national_frames(request):
    product = request.GET.get('product', 'reflectivity')
    minutes = int(request.GET.get('minutes', 60))
    since = timezone.now() - timedelta(minutes=minutes)
    tiles = MRMSTile.objects.filter(
        product=product, processed=True, valid_time__gte=since
    ).order_by('valid_time')
    data = [
        {
            'valid_time': t.valid_time.isoformat(),
            'tile_url': f'/api/radar/tiles/{t.tile_path}',
            'bounds': t.bounds_json,
        }
        for t in tiles
    ]
    return JsonResponse(data, safe=False)


# ── Station-Level NEXRAD ──────────────────────────────────────────────────────

def station_latest(request, code):
    product = request.GET.get('product', 'reflectivity')
    try:
        station = RadarStation.objects.get(code=code.upper())
    except RadarStation.DoesNotExist:
        return JsonResponse({'error': 'Station not found'}, status=404)

    tile = RadarTile.objects.filter(
        scan__station=station, product=product
    ).order_by('-valid_time').first()
    if not tile:
        return JsonResponse({'error': 'No tiles available'}, status=404)

    return JsonResponse({
        'valid_time': tile.valid_time.isoformat(),
        'tile_url': f'/api/radar/tiles/{tile.tile_path}',
        'bounds': tile.bounds_json,
    })


def station_frames(request, code):
    product = request.GET.get('product', 'reflectivity')
    minutes = int(request.GET.get('minutes', 60))
    try:
        station = RadarStation.objects.get(code=code.upper())
    except RadarStation.DoesNotExist:
        return JsonResponse({'error': 'Station not found'}, status=404)

    since = timezone.now() - timedelta(minutes=minutes)
    tiles = RadarTile.objects.filter(
        scan__station=station, product=product, valid_time__gte=since
    ).order_by('valid_time')
    data = [
        {
            'valid_time': t.valid_time.isoformat(),
            'tile_url': f'/api/radar/tiles/{t.tile_path}',
            'bounds': t.bounds_json,
        }
        for t in tiles
    ]
    return JsonResponse(data, safe=False)


def station_hail(request, code):
    try:
        station = RadarStation.objects.get(code=code.upper())
    except RadarStation.DoesNotExist:
        return JsonResponse({'error': 'Station not found'}, status=404)

    report = HailReport.objects.filter(
        scan__station=station
    ).order_by('-valid_time').first()
    if not report:
        return JsonResponse({'type': 'FeatureCollection', 'features': []})

    return JsonResponse(report.geojson)


def station_nowcast(request, code):
    try:
        station = RadarStation.objects.get(code=code.upper())
    except RadarStation.DoesNotExist:
        return JsonResponse({'error': 'Station not found'}, status=404)

    nowcast_products = [p for p, _ in RadarTile.PRODUCT_CHOICES if p.startswith('nowcast_')]
    latest_scan = RadarScan.objects.filter(
        station=station, processed=True
    ).order_by('-scan_time').first()
    if not latest_scan:
        return JsonResponse([], safe=False)

    tiles = RadarTile.objects.filter(
        scan=latest_scan, product__startswith='nowcast_'
    ).order_by('product')
    data = [
        {
            'valid_time': t.valid_time.isoformat(),
            'tile_url': f'/api/radar/tiles/{t.tile_path}',
            'bounds': t.bounds_json,
        }
        for t in tiles
    ]
    return JsonResponse(data, safe=False)


# ── NWS Alerts ────────────────────────────────────────────────────────────────

def alerts_geojson(request):
    from .services.alerts import get_active_alerts_geojson
    return JsonResponse(get_active_alerts_geojson())


# ── Tile Serving ──────────────────────────────────────────────────────────────

def serve_tile(request, tile_path):
    full_path = os.path.join(settings.TILE_OUTPUT_DIR, tile_path)
    if not os.path.exists(full_path):
        raise Http404('Tile not found')
    # Security: prevent path traversal
    real_path = os.path.realpath(full_path)
    real_base = os.path.realpath(settings.TILE_OUTPUT_DIR)
    if not real_path.startswith(real_base + os.sep):
        raise Http404('Invalid tile path')
    return FileResponse(open(real_path, 'rb'), content_type='image/png')
