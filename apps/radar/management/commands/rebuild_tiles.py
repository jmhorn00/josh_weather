"""
Management command: rebuild_tiles
Re-renders PNG tiles from already-cached scan files.
Useful after color scale changes.

Usage:
    python manage.py rebuild_tiles --station KTLX --hours 6
"""
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = 'Re-render PNG tiles from cached scan files for a given station'

    def add_arguments(self, parser):
        parser.add_argument('--station', required=True, help='Station code e.g. KTLX')
        parser.add_argument('--hours', type=int, default=6, help='Hours to rebuild (default 6)')

    def handle(self, *args, **options):
        code = options['station'].upper()
        hours = options['hours']

        from apps.radar.models import RadarStation, RadarScan
        try:
            station = RadarStation.objects.get(code=code)
        except RadarStation.DoesNotExist:
            raise CommandError(f'Station {code} not found.')

        cutoff = timezone.now() - timedelta(hours=hours)
        scans = RadarScan.objects.filter(
            station=station,
            scan_time__gte=cutoff,
            processed=True,
        ).exclude(local_path='')

        self.stdout.write(f'Found {scans.count()} cached scans for {code}')

        from apps.radar.services.processor import load_nexrad, dealias_velocity, radar_to_grid
        from apps.radar.services.tiles import render_reflectivity_tile, render_velocity_tile
        from apps.radar.models import RadarTile
        from django.conf import settings
        import os

        for scan in scans:
            if not os.path.exists(scan.local_path):
                self.stderr.write(f'  Missing file: {scan.local_path}')
                continue

            self.stdout.write(f'  Rebuilding tiles for scan {scan.id} ({scan.scan_time})')
            try:
                radar = load_nexrad(scan.local_path)
                radar = dealias_velocity(radar)
                grid = radar_to_grid(radar, fields=['reflectivity', 'velocity'])
                os.makedirs(os.path.join(settings.TILE_OUTPUT_DIR, code), exist_ok=True)

                ref_filename = f"{code}_ref_{scan.scan_time.strftime('%Y%m%d_%H%M%S')}.png"
                ref_path = os.path.join(settings.TILE_OUTPUT_DIR, code, ref_filename)
                _, ref_bounds = render_reflectivity_tile(grid, ref_path)
                RadarTile.objects.update_or_create(
                    scan=scan, product='reflectivity',
                    defaults={'valid_time': scan.scan_time,
                              'tile_path': os.path.join(code, ref_filename),
                              'bounds_json': ref_bounds},
                )

                vel_filename = f"{code}_vel_{scan.scan_time.strftime('%Y%m%d_%H%M%S')}.png"
                vel_path = os.path.join(settings.TILE_OUTPUT_DIR, code, vel_filename)
                _, vel_bounds = render_velocity_tile(grid, vel_path)
                RadarTile.objects.update_or_create(
                    scan=scan, product='velocity',
                    defaults={'valid_time': scan.scan_time,
                              'tile_path': os.path.join(code, vel_filename),
                              'bounds_json': vel_bounds},
                )
                self.stdout.write(f'    Done')
            except Exception as exc:
                self.stderr.write(f'    Error: {exc}')

        self.stdout.write(self.style.SUCCESS(f'Tile rebuild complete for {code}'))
