"""
Celery tasks for radar data ingestion.
All tasks are idempotent — safe to re-run on duplicate keys.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


# ── MRMS National Mosaic ──────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3)
def poll_mrms_mosaic(self):
    """
    Runs every 120s via Beat.
    Lists latest files in s3://noaa-mrms-pds/CONUS/MergedReflectivityQC_00.00/
    Downloads newest grib2.gz not yet in MRMSTile table.
    Renders CONUS PNG tile. Creates MRMSTile record.
    Keeps last 60 minutes of tiles (30 frames). Deletes older records + files.
    """
    try:
        from .services.s3 import get_latest_mrms_key, download_mrms
        from .services.mrms import parse_mrms_grib, render_mrms_reflectivity
        from .models import MRMSTile
        import os

        s3_key = get_latest_mrms_key('reflectivity')
        if not s3_key:
            logger.warning('poll_mrms_mosaic: no MRMS key found')
            return

        if MRMSTile.objects.filter(s3_key=s3_key).exists():
            logger.debug('poll_mrms_mosaic: already processed %s', s3_key)
            return

        from django.conf import settings
        dest = os.path.join(settings.MRMS_CACHE_DIR, os.path.basename(s3_key))
        os.makedirs(settings.MRMS_CACHE_DIR, exist_ok=True)
        local_path = download_mrms(s3_key, dest)

        ds = parse_mrms_grib(local_path)

        # Parse valid time from key: ...YYYYMMDD-HHMMSS.grib2.gz
        import re
        from datetime import datetime, timezone as dt_tz
        m = re.search(r'(\d{8})-(\d{6})', s3_key)
        if m:
            valid_time = datetime.strptime(
                m.group(1) + m.group(2), '%Y%m%d%H%M%S'
            ).replace(tzinfo=dt_tz.utc)
        else:
            valid_time = timezone.now()

        tile_filename = f"mrms_reflectivity_{valid_time.strftime('%Y%m%d_%H%M%S')}.png"
        tile_path = os.path.join(settings.TILE_OUTPUT_DIR, 'mrms', tile_filename)
        os.makedirs(os.path.dirname(tile_path), exist_ok=True)

        _, bounds = render_mrms_reflectivity(ds, tile_path)

        tile = MRMSTile.objects.create(
            product='reflectivity',
            valid_time=valid_time,
            s3_key=s3_key,
            tile_path=os.path.join('mrms', tile_filename),
            bounds_json=bounds,
            processed=True,
        )
        logger.info('poll_mrms_mosaic: created tile %s', tile.id)

        # Prune tiles older than 60 minutes
        cutoff = timezone.now() - timedelta(minutes=60)
        old_tiles = MRMSTile.objects.filter(product='reflectivity', valid_time__lt=cutoff)
        for old in old_tiles:
            full = os.path.join(settings.TILE_OUTPUT_DIR, old.tile_path)
            if os.path.exists(full):
                os.remove(full)
        old_tiles.delete()

    except Exception as exc:
        logger.error('poll_mrms_mosaic failed: %s', exc)
        raise self.retry(exc=exc, countdown=30)


# ── On-demand per-station NEXRAD ──────────────────────────────────────────────

@shared_task(bind=True, max_retries=3)
def poll_active_stations(self):
    """
    Runs every 90s via Beat.
    Queries ActiveStation records that haven't expired.
    Queues check_station_for_new_scans for each active station.
    Deletes expired ActiveStation records.
    """
    from .models import ActiveStation
    now = timezone.now()
    active = ActiveStation.objects.filter(expires_at__gt=now).select_related('station')
    for active_station in active:
        check_station_for_new_scans.delay(active_station.station.code)
        logger.debug('poll_active_stations: queued scan check for %s', active_station.station.code)

    expired = ActiveStation.objects.filter(expires_at__lte=now)
    count = expired.count()
    if count:
        logger.info('poll_active_stations: deleting %d expired active stations', count)
        expired.delete()


@shared_task(bind=True, max_retries=3)
def check_station_for_new_scans(self, station_code):
    """
    Lists latest S3 keys for station. Finds keys not yet in RadarScan table.
    Queues process_nexrad_scan() for each new key found.
    """
    try:
        from .services.s3 import list_nexrad_scans
        from .models import RadarStation, RadarScan
        from datetime import datetime, timezone as dt_tz

        station = RadarStation.objects.get(code=station_code)
        today = datetime.now(dt_tz.utc)
        keys = list_nexrad_scans(station_code, today)
        if not keys:
            # Also check yesterday in case of UTC rollover
            yesterday = today - timedelta(days=1)
            keys = list_nexrad_scans(station_code, yesterday)

        existing_keys = set(
            RadarScan.objects.filter(station=station, s3_key__in=keys)
            .values_list('s3_key', flat=True)
        )
        new_keys = [k for k in keys if k not in existing_keys]
        # Process only the last 5 new scans to avoid backlog
        for key in new_keys[-5:]:
            process_nexrad_scan.delay(station_code, key)
            logger.info('check_station_for_new_scans: queued %s', key)

    except Exception as exc:
        logger.error('check_station_for_new_scans(%s) failed: %s', station_code, exc)
        raise self.retry(exc=exc, countdown=30)


@shared_task(bind=True, max_retries=3)
def process_nexrad_scan(self, station_code, s3_key):
    """
    Full pipeline for one NEXRAD Level 2 scan:
    1. Download from S3
    2. Create RadarScan record (idempotent on s3_key)
    3. Parse with Py-ART, dealias velocity, grid to Cartesian
    4. Render reflectivity + velocity PNG tiles
    5. Run PyHail MESH → HailReport
    6. If 4+ processed scans → queue generate_nowcast
    7. Mark scan.processed = True, update station.last_scan_time
    """
    from .models import RadarStation, RadarScan, RadarTile, HailReport
    from django.conf import settings
    import os

    try:
        station = RadarStation.objects.get(code=station_code)

        # Idempotency check
        scan, created = RadarScan.objects.get_or_create(
            s3_key=s3_key,
            defaults={'station': station, 'scan_time': timezone.now()},
        )
        if not created and scan.processed:
            logger.debug('process_nexrad_scan: already processed %s', s3_key)
            return

        # Download
        from .services.s3 import download_nexrad
        os.makedirs(settings.SCAN_CACHE_DIR, exist_ok=True)
        dest = os.path.join(settings.SCAN_CACHE_DIR, os.path.basename(s3_key))
        local_path = download_nexrad(s3_key, dest)
        scan.local_path = local_path
        scan.save(update_fields=['local_path'])

        # Parse scan time from filename: KXXX20240101_120000_V06
        import re
        from datetime import datetime, timezone as dt_tz
        m = re.search(r'(\d{8})_(\d{6})', os.path.basename(s3_key))
        if m:
            scan.scan_time = datetime.strptime(
                m.group(1) + m.group(2), '%Y%m%d%H%M%S'
            ).replace(tzinfo=dt_tz.utc)
            scan.save(update_fields=['scan_time'])

        # Py-ART processing
        from .services.processor import load_nexrad, dealias_velocity, radar_to_grid
        radar = load_nexrad(local_path)
        radar = dealias_velocity(radar)
        grid = radar_to_grid(radar, fields=['reflectivity', 'velocity'])

        # Render tiles
        from .services.tiles import render_reflectivity_tile, render_velocity_tile
        os.makedirs(os.path.join(settings.TILE_OUTPUT_DIR, station_code), exist_ok=True)

        ref_filename = f"{station_code}_ref_{scan.scan_time.strftime('%Y%m%d_%H%M%S')}.png"
        ref_path = os.path.join(settings.TILE_OUTPUT_DIR, station_code, ref_filename)
        _, ref_bounds = render_reflectivity_tile(grid, ref_path)
        RadarTile.objects.update_or_create(
            scan=scan, product='reflectivity',
            defaults={
                'valid_time': scan.scan_time,
                'tile_path': os.path.join(station_code, ref_filename),
                'bounds_json': ref_bounds,
            },
        )

        vel_filename = f"{station_code}_vel_{scan.scan_time.strftime('%Y%m%d_%H%M%S')}.png"
        vel_path = os.path.join(settings.TILE_OUTPUT_DIR, station_code, vel_filename)
        _, vel_bounds = render_velocity_tile(grid, vel_path)
        RadarTile.objects.update_or_create(
            scan=scan, product='velocity',
            defaults={
                'valid_time': scan.scan_time,
                'tile_path': os.path.join(station_code, vel_filename),
                'bounds_json': vel_bounds,
            },
        )

        # Hail detection
        from .services.hail import calculate_mesh
        hail_result = calculate_mesh(radar)
        HailReport.objects.update_or_create(
            scan=scan,
            defaults={
                'valid_time': scan.scan_time,
                'max_mesh_mm': hail_result['max_mm'],
                'geojson': hail_result['geojson'],
            },
        )

        # Mark processed
        scan.processed = True
        scan.save(update_fields=['processed'])
        station.last_scan_time = scan.scan_time
        station.save(update_fields=['last_scan_time'])

        # Nowcast if enough scans
        processed_count = RadarScan.objects.filter(
            station=station, processed=True
        ).count()
        if processed_count >= 4:
            generate_nowcast.delay(station_code)

        logger.info('process_nexrad_scan: done %s', s3_key)

    except Exception as exc:
        logger.error('process_nexrad_scan(%s, %s) failed: %s', station_code, s3_key, exc)
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True)
def generate_nowcast(self, station_code):
    """
    Loads last 4 reflectivity grids for station.
    Runs pysteps STEPS (NOWCAST_TIMESTEPS timesteps).
    Renders nowcast PNG tiles → RadarTile records.
    """
    from .models import RadarStation, RadarScan, RadarTile
    from .services.processor import load_nexrad, radar_to_grid
    from .services.nowcast import build_precip_stack, run_nowcast
    from .services.tiles import render_nowcast_tile
    from django.conf import settings
    import os
    import numpy as np

    try:
        station = RadarStation.objects.get(code=station_code)
        scans = RadarScan.objects.filter(
            station=station, processed=True
        ).order_by('-scan_time')[:4]
        scans = list(reversed(scans))

        if len(scans) < 4:
            logger.warning('generate_nowcast: not enough scans for %s', station_code)
            return

        grids = []
        for scan in scans:
            radar = load_nexrad(scan.local_path)
            grid = radar_to_grid(radar, fields=['reflectivity'])
            grids.append(grid)

        precip_stack = build_precip_stack(grids)
        forecast_arrays = run_nowcast(precip_stack)

        timestep_labels = ['00', '05', '10', '15', '20', '25', '30', '35', '40', '45', '50', '55', '60']
        latest_scan = scans[-1]
        os.makedirs(os.path.join(settings.TILE_OUTPUT_DIR, station_code), exist_ok=True)

        for i, arr in enumerate(forecast_arrays):
            minutes = (i + 1) * 5
            label = f"{minutes:02d}"
            # Map to product name buckets (00, 15, 30, 45, 60)
            bucket = min([0, 15, 30, 45, 60], key=lambda b: abs(b - minutes))
            product = f"nowcast_{bucket:02d}"

            from datetime import timedelta
            valid_time = latest_scan.scan_time + timedelta(minutes=minutes)
            filename = f"{station_code}_nc{label}_{latest_scan.scan_time.strftime('%Y%m%d_%H%M%S')}.png"
            tile_path_full = os.path.join(settings.TILE_OUTPUT_DIR, station_code, filename)

            _, bounds = render_nowcast_tile(arr, tile_path_full)
            RadarTile.objects.update_or_create(
                scan=latest_scan, product=product,
                defaults={
                    'valid_time': valid_time,
                    'tile_path': os.path.join(station_code, filename),
                    'bounds_json': bounds,
                },
            )

        logger.info('generate_nowcast: done %s', station_code)
    except Exception as exc:
        logger.error('generate_nowcast(%s) failed: %s', station_code, exc)


# ── Station Activation ────────────────────────────────────────────────────────

@shared_task
def activate_station(station_code):
    """
    Creates/refreshes ActiveStation. Immediately queues scan check.
    """
    from .models import RadarStation, ActiveStation
    from django.conf import settings

    try:
        station = RadarStation.objects.get(code=station_code)
        expires_at = timezone.now() + timedelta(seconds=settings.STATION_SCAN_TTL)
        ActiveStation.objects.update_or_create(
            station=station,
            defaults={'expires_at': expires_at},
        )
        check_station_for_new_scans.delay(station_code)
        logger.info('activate_station: activated %s', station_code)
    except RadarStation.DoesNotExist:
        logger.error('activate_station: station %s not found', station_code)


# ── NWS Alerts ────────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3)
def poll_nws_alerts(self):
    """
    GET https://api.weather.gov/alerts/active (no area filter = all US).
    Upserts NWSAlert records. Deletes expired alerts. Runs every 60s.
    """
    try:
        from .services.alerts import fetch_active_alerts, parse_alert, upsert_alert, expire_old_alerts
        alerts = fetch_active_alerts()
        count = 0
        for feature in alerts:
            alert_dict = parse_alert(feature)
            if alert_dict:
                upsert_alert(alert_dict)
                count += 1
        deleted = expire_old_alerts()
        logger.info('poll_nws_alerts: upserted %d alerts, deleted %d expired', count, deleted)
    except Exception as exc:
        logger.error('poll_nws_alerts failed: %s', exc)
        raise self.retry(exc=exc, countdown=30)


# ── Cleanup ───────────────────────────────────────────────────────────────────

@shared_task
def cleanup_old_data():
    """
    Runs hourly. Deletes old tiles, scans, reports, and expired alerts.
    """
    import os
    from django.conf import settings
    from .models import MRMSTile, RadarScan, RadarTile, HailReport, NWSAlert, ActiveStation

    now = timezone.now()

    # MRMS tiles older than 2 hours
    old_mrms = MRMSTile.objects.filter(valid_time__lt=now - timedelta(hours=2))
    for t in old_mrms:
        p = os.path.join(settings.TILE_OUTPUT_DIR, t.tile_path)
        if os.path.exists(p):
            os.remove(p)
    mrms_count = old_mrms.count()
    old_mrms.delete()

    # RadarScan + files older than 24h for inactive stations
    active_station_ids = ActiveStation.objects.filter(
        expires_at__gt=now
    ).values_list('station_id', flat=True)
    old_scans = RadarScan.objects.filter(
        fetched_at__lt=now - timedelta(hours=24)
    ).exclude(station_id__in=active_station_ids)
    for scan in old_scans:
        if scan.local_path and os.path.exists(scan.local_path):
            os.remove(scan.local_path)
    scan_count = old_scans.count()
    old_scans.delete()

    # RadarTile records older than 24h
    old_radar_tiles = RadarTile.objects.filter(valid_time__lt=now - timedelta(hours=24))
    tile_count = old_radar_tiles.count()
    old_radar_tiles.delete()

    # HailReport records older than 24h
    old_hail = HailReport.objects.filter(valid_time__lt=now - timedelta(hours=24))
    hail_count = old_hail.count()
    old_hail.delete()

    # Expired NWS alerts
    expired_alerts = NWSAlert.objects.filter(expires__lt=now)
    alert_count = expired_alerts.count()
    expired_alerts.delete()

    logger.info(
        'cleanup_old_data: mrms=%d scans=%d tiles=%d hail=%d alerts=%d',
        mrms_count, scan_count, tile_count, hail_count, alert_count
    )
