"""
Management command: test_mrms
Downloads the latest MRMS reflectivity file and renders one CONUS tile.
Smoke test for the MRMS + cfgrib pipeline.

Usage:
    python manage.py test_mrms
"""
import os

from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Download latest MRMS reflectivity and render one CONUS tile (smoke test)'

    def handle(self, *args, **options):
        from apps.radar.services.s3 import get_latest_mrms_key, download_mrms
        from apps.radar.services.mrms import parse_mrms_grib, render_mrms_reflectivity

        self.stdout.write('Fetching latest MRMS reflectivity key...')
        key = get_latest_mrms_key('reflectivity')
        if not key:
            self.stderr.write('No MRMS key found. Check S3 connectivity.')
            return

        self.stdout.write(f'Latest key: {key}')
        os.makedirs(settings.MRMS_CACHE_DIR, exist_ok=True)
        dest = os.path.join(settings.MRMS_CACHE_DIR, os.path.basename(key))

        self.stdout.write('Downloading...')
        local_path = download_mrms(key, dest)
        self.stdout.write(f'Downloaded to {local_path}')

        self.stdout.write('Parsing grib2...')
        ds = parse_mrms_grib(local_path)
        self.stdout.write(f'Dataset variables: {list(ds.data_vars)}')

        output_path = os.path.join(settings.TILE_OUTPUT_DIR, 'test_mrms.png')
        os.makedirs(settings.TILE_OUTPUT_DIR, exist_ok=True)
        self.stdout.write(f'Rendering tile to {output_path}...')
        tile_path, bounds = render_mrms_reflectivity(ds, output_path)

        self.stdout.write(self.style.SUCCESS(f'Success! Tile: {tile_path}'))
        self.stdout.write(f'Bounds: {bounds}')
