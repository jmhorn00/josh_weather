"""
Management command: backfill_scans
Downloads and processes the last N hours of NEXRAD scans for a given station.

Usage:
    python manage.py backfill_scans --station KTLX --hours 6
"""
from datetime import datetime, timedelta, timezone as dt_tz

from django.core.management.base import BaseCommand, CommandError

from apps.radar.models import RadarStation


class Command(BaseCommand):
    help = 'Download and process last N hours of NEXRAD scans for one station'

    def add_arguments(self, parser):
        parser.add_argument('--station', required=True, help='Station code e.g. KTLX')
        parser.add_argument('--hours', type=int, default=6, help='Hours to backfill (default 6)')

    def handle(self, *args, **options):
        code = options['station'].upper()
        hours = options['hours']

        try:
            station = RadarStation.objects.get(code=code)
        except RadarStation.DoesNotExist:
            raise CommandError(f'Station {code} not found. Run seed_stations first.')

        from apps.radar.services.s3 import list_nexrad_scans
        from apps.radar.tasks import process_nexrad_scan

        self.stdout.write(f'Backfilling last {hours}h of scans for {code}...')

        now = datetime.now(dt_tz.utc)
        keys = []
        for day_offset in range(2):  # today + yesterday
            day = now - timedelta(days=day_offset)
            day_keys = list_nexrad_scans(code, day)
            # Filter to last N hours
            cutoff = now - timedelta(hours=hours)
            for key in day_keys:
                import re
                m = re.search(r'(\d{8})_(\d{6})', key)
                if m:
                    scan_time = datetime.strptime(
                        m.group(1) + m.group(2), '%Y%m%d%H%M%S'
                    ).replace(tzinfo=dt_tz.utc)
                    if scan_time >= cutoff:
                        keys.append(key)

        keys = sorted(set(keys))
        self.stdout.write(f'Found {len(keys)} scans to process')

        for key in keys:
            self.stdout.write(f'  Queuing {key}')
            process_nexrad_scan.delay(code, key)

        self.stdout.write(self.style.SUCCESS(f'Queued {len(keys)} scans for {code}'))
