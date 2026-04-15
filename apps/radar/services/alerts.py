"""
NWS alert service — fetches all active US alerts (no area filter).
API: https://api.weather.gov/alerts/active
No API key required. NWS_USER_AGENT header required.
"""
import logging
from datetime import datetime, timezone as dt_tz

import urllib.request
import json

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

NWS_ALERTS_URL = 'https://api.weather.gov/alerts/active'


def fetch_active_alerts():
    """
    Fetch all active US alerts from NWS API.
    Returns list of GeoJSON feature dicts.
    """
    req = urllib.request.Request(
        NWS_ALERTS_URL,
        headers={'User-Agent': settings.NWS_USER_AGENT, 'Accept': 'application/geo+json'},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read())
        return data.get('features', [])
    except Exception as exc:
        logger.error('fetch_active_alerts failed: %s', exc)
        return []


def parse_alert(feature):
    """
    Parse a NWS alert GeoJSON feature into a dict suitable for NWSAlert.update_or_create.
    GeoJSON coords are [longitude, latitude] — swap for Leaflet if needed in template.
    Returns dict or None if parse fails.
    """
    try:
        props = feature.get('properties', {})

        def parse_dt(s):
            if not s:
                return None
            try:
                return datetime.fromisoformat(s.replace('Z', '+00:00'))
            except Exception:
                return None

        return {
            'alert_id': props.get('id') or feature.get('id', ''),
            'event': props.get('event', ''),
            'severity': props.get('severity', ''),
            'headline': props.get('headline', '') or '',
            'description': props.get('description', '') or '',
            'instruction': props.get('instruction', '') or '',
            'area_desc': props.get('areaDesc', '') or '',
            'sent': parse_dt(props.get('sent')) or timezone.now(),
            'effective': parse_dt(props.get('effective')) or timezone.now(),
            'expires': parse_dt(props.get('expires')) or timezone.now(),
            'onset': parse_dt(props.get('onset')),
            'status': props.get('status', ''),
            'message_type': props.get('messageType', ''),
            'geojson': feature.get('geometry'),
            'nws_office': props.get('senderName', '')[:10] if props.get('senderName') else '',
        }
    except Exception as exc:
        logger.warning('parse_alert failed: %s', exc)
        return None


def upsert_alert(alert_dict):
    """
    Create or update a NWSAlert record from a parsed alert dict.
    Returns NWSAlert instance.
    """
    from apps.radar.models import NWSAlert
    alert_id = alert_dict.pop('alert_id')
    obj, _ = NWSAlert.objects.update_or_create(
        alert_id=alert_id,
        defaults=alert_dict,
    )
    return obj


def expire_old_alerts():
    """Delete NWSAlert records that have passed their expiry time. Returns count."""
    from apps.radar.models import NWSAlert
    expired = NWSAlert.objects.filter(expires__lt=timezone.now())
    count = expired.count()
    expired.delete()
    return count


def get_active_alerts_geojson():
    """
    Build a GeoJSON FeatureCollection of all currently active NWS alerts.
    Adds 'color' property for frontend rendering.
    Returns dict (JSON-serializable).
    """
    from apps.radar.models import NWSAlert, NWS_ALERT_COLORS
    alerts = NWSAlert.objects.filter(expires__gt=timezone.now())
    features = []
    for alert in alerts:
        if not alert.geojson:
            continue
        features.append({
            'type': 'Feature',
            'geometry': alert.geojson,
            'properties': {
                'event': alert.event,
                'severity': alert.severity,
                'headline': alert.headline,
                'description': alert.description,
                'instruction': alert.instruction,
                'area_desc': alert.area_desc,
                'expires': alert.expires.isoformat(),
                'color': NWS_ALERT_COLORS.get(alert.event, '#999999'),
                'nws_office': alert.nws_office,
                'alert_id': alert.alert_id,
            },
        })
    return {'type': 'FeatureCollection', 'features': features}
