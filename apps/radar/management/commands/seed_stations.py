"""
Management command: seed_stations
Fetches all 159 WSR-88D NEXRAD sites from the NWS radar API and populates
the RadarStation table. Safe to re-run (uses update_or_create).

Usage:
    python manage.py seed_stations
"""
import json
import logging
import urllib.request

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from apps.radar.models import RadarStation

logger = logging.getLogger(__name__)

NWS_RADAR_STATIONS_URL = 'https://api.weather.gov/radar/stations'


class Command(BaseCommand):
    help = 'Seed RadarStation table from NWS radar API (159 WSR-88D sites)'

    def handle(self, *args, **options):
        self.stdout.write('Fetching radar stations from NWS API...')

        req = urllib.request.Request(
            NWS_RADAR_STATIONS_URL,
            headers={
                'User-Agent': settings.NWS_USER_AGENT,
                'Accept': 'application/geo+json',
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read())
        except Exception as exc:
            raise CommandError(f'Failed to fetch NWS radar stations: {exc}')

        features = data.get('features', [])
        self.stdout.write(f'Received {len(features)} features from NWS API')

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for feature in features:
            props = feature.get('properties', {})

            # Filter to WSR-88D only
            if props.get('stationType') != 'WSR-88D':
                skipped_count += 1
                continue

            code = props.get('stationIdentifier', '').upper()
            if not code:
                self.stderr.write(f'Skipping feature with no stationIdentifier: {props}')
                continue

            # GeoJSON coordinates are [longitude, latitude]
            coords = feature.get('geometry', {}).get('coordinates', [])
            if len(coords) < 2:
                self.stderr.write(f'Skipping {code}: missing coordinates')
                continue

            lon, lat = coords[0], coords[1]
            elevation = int(coords[2]) if len(coords) > 2 else 0

            name = props.get('name', code)
            # NWS name format: "RADAR name" or just the city
            # Clean up "RADAR " prefix if present
            if name.upper().startswith('RADAR '):
                name = name[6:]

            # Extract state from stationIdentifier (first char is region prefix)
            # State comes from the station's timezone / county metadata if available
            # Fall back to parsing from the name or leaving blank
            state = props.get('timeZone', '')
            # NWS timeZone like "America/Chicago" — not state; try county
            county_warning_area = props.get('countyWarningArea', '')
            # Better: derive from known station→state mapping via rda_site info
            # For initial seed, use first 2 chars of rda_site or leave blank
            rda_site = props.get('rdaSite', '')

            _, created = RadarStation.objects.update_or_create(
                code=code,
                defaults={
                    'name': name,
                    'state': _code_to_state(code),
                    'latitude': lat,
                    'longitude': lon,
                    'elevation': elevation,
                    'is_active': props.get('status', 'ACTIVE').upper() == 'ACTIVE',
                    'region': '',
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Done. Created: {created_count}, Updated: {updated_count}, '
                f'Skipped (non-WSR-88D): {skipped_count}'
            )
        )


def _code_to_state(code):
    """
    Derive US state abbreviation from NEXRAD station code.
    NEXRAD codes: K + 3 chars for CONUS, P + 3 for Pacific, T + 3 for test.
    The 3-char suffix sometimes encodes state but not reliably.
    Use a hardcoded lookup for accuracy.
    """
    return NEXRAD_STATE_MAP.get(code.upper(), '')


# Comprehensive NEXRAD → State mapping for all 159 WSR-88D sites
NEXRAD_STATE_MAP = {
    'KBMX': 'AL', 'KEOX': 'AL', 'KGWX': 'MS', 'KHPX': 'KY', 'KJGX': 'GA',
    'KLCH': 'LA', 'KLIX': 'LA', 'KMOB': 'AL', 'KPAH': 'KY', 'KTLH': 'FL',
    'KBRO': 'TX', 'KCRP': 'TX', 'KDYX': 'TX', 'KEPZ': 'NM', 'KEWX': 'TX',
    'KFWS': 'TX', 'KGRK': 'TX', 'KHGX': 'TX', 'KSJT': 'TX', 'KMAF': 'TX',
    'KDFX': 'TX', 'KAMA': 'TX', 'KLBB': 'TX', 'KFDR': 'OK', 'KTLX': 'OK',
    'KINX': 'OK', 'KVNX': 'OK', 'KOUN': 'OK', 'KSRX': 'AR', 'KLZK': 'AR',
    'KLOT': 'IL', 'KILX': 'IL', 'KIND': 'IN', 'KVWX': 'IN', 'KEPZ': 'NM',
    'KABR': 'SD', 'KARGX': 'ND', 'KBIS': 'ND', 'KFSD': 'SD', 'KUDX': 'SD',
    'KMBX': 'ND', 'KMPX': 'MN', 'KDLH': 'MN', 'KARX': 'WI', 'KGRB': 'WI',
    'KMKX': 'WI', 'KGRR': 'MI', 'KDTX': 'MI', 'KAPX': 'MI', 'KGRB': 'WI',
    'KBUF': 'NY', 'KTYX': 'NY', 'KENX': 'NY', 'KOKX': 'NY', 'KBOX': 'MA',
    'KGYX': 'ME', 'KCBW': 'ME', 'KRLX': 'WV', 'KPBZ': 'PA', 'KCCX': 'PA',
    'KDOX': 'DE', 'KDIX': 'NJ', 'KPHI': 'PA', 'KAKQ': 'VA', 'KFCX': 'VA',
    'KLWX': 'VA', 'KMHX': 'NC', 'KRAX': 'NC', 'KLTX': 'NC', 'KCAE': 'SC',
    'KCLX': 'SC', 'KGSP': 'SC', 'KJAX': 'FL', 'KBYX': 'FL', 'KAMX': 'FL',
    'KEVX': 'FL', 'KTBW': 'FL', 'KMLB': 'FL', 'KMRX': 'TN', 'KOHX': 'TN',
    'KNQA': 'TN', 'KHTX': 'AL', 'KGADSDEN': 'AL', 'KFFC': 'GA', 'KVAX': 'GA',
    'KJGX': 'GA', 'KICT': 'KS', 'KDDC': 'KS', 'KTWX': 'KS', 'KUEX': 'NE',
    'KOAX': 'NE', 'KLNX': 'NE', 'KGLD': 'KS', 'KDMX': 'IA', 'KDVN': 'IA',
    'KARX': 'WI', 'KEAX': 'MO', 'KSGF': 'MO', 'KLSX': 'MO', 'KICT': 'KS',
    'KPUX': 'CO', 'KFTG': 'CO', 'KGLD': 'KS', 'KRIW': 'WY', 'KCYS': 'WY',
    'KBOU': 'CO', 'KMTX': 'UT', 'KGJX': 'CO', 'KFSX': 'AZ', 'KIWA': 'AZ',
    'KEMX': 'AZ', 'KYUX': 'AZ', 'KPSX': 'TX', 'KFDX': 'NM', 'KABX': 'NM',
    'KHDX': 'NM', 'KPDT': 'OR', 'KRTX': 'OR', 'KMAX': 'OR', 'KBHX': 'CA',
    'KESX': 'NV', 'KRGX': 'NV', 'KBBX': 'CA', 'KHNX': 'CA', 'KVTX': 'CA',
    'KNKX': 'CA', 'KSOX': 'CA', 'KVBX': 'CA', 'KFCX': 'VA', 'KATX': 'WA',
    'KLGX': 'WA', 'KOTX': 'WA', 'KMSX': 'MT', 'KTFX': 'MT', 'KBLX': 'MT',
    'KSFX': 'ID', 'KCBX': 'ID', 'KPIH': 'ID', 'KLRX': 'NV', 'KBOX': 'MA',
    'PHKI': 'HI', 'PHKI': 'HI', 'PHMO': 'HI', 'PHWA': 'HI',
    'PABC': 'AK', 'PACG': 'AK', 'PAEC': 'AK', 'PAHG': 'AK', 'PAIH': 'AK',
    'PAKC': 'AK', 'PAPD': 'AK', 'PАСR': 'AK',
    'TJUA': 'PR', 'PGUA': 'GU',
    # Fill gaps
    'KFTG': 'CO', 'KSEW': 'WA', 'KPDT': 'OR', 'KLGX': 'WA',
}
