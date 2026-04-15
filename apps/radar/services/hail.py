"""
Hail detection using PyHail MESH algorithm.
"""
import logging
import numpy as np

logger = logging.getLogger(__name__)


def calculate_mesh(radar):
    """
    Run PyHail MESH algorithm on a Py-ART Radar object.
    Returns dict: {max_mm: float, geojson: GeoJSON FeatureCollection}
    """
    try:
        import pyhail
        mesh_ds = pyhail.mesh.process_single_file(radar)
        mesh_data = mesh_ds['MESH'].values

        max_mm = float(np.nanmax(mesh_data)) if mesh_data.size > 0 else 0.0

        # Build GeoJSON FeatureCollection from MESH grid
        features = []
        from django.conf import settings
        threshold = settings.HAIL_MESH_THRESHOLD

        lats = mesh_ds.latitude.values
        lons = mesh_ds.longitude.values

        for i in range(len(lats)):
            for j in range(len(lons)):
                val = mesh_data[i, j] if mesh_data.ndim == 2 else mesh_data[0, i, j]
                if not np.isnan(val) and val >= threshold:
                    features.append({
                        'type': 'Feature',
                        'geometry': {
                            'type': 'Point',
                            'coordinates': [float(lons[j]), float(lats[i])],
                        },
                        'properties': {
                            'mesh_mm': round(float(val), 1),
                            'hail_size': _mesh_to_hail_size(val),
                        },
                    })

        geojson = {'type': 'FeatureCollection', 'features': features}
        return {'max_mm': max_mm, 'geojson': geojson}

    except Exception as exc:
        logger.error('calculate_mesh failed: %s', exc)
        return {
            'max_mm': 0.0,
            'geojson': {'type': 'FeatureCollection', 'features': []},
        }


def _mesh_to_hail_size(mesh_mm):
    """Convert MESH value to approximate hail diameter description."""
    if mesh_mm < 6:
        return 'Pea (<0.25")'
    elif mesh_mm < 13:
        return 'Marble (0.5")'
    elif mesh_mm < 19:
        return 'Dime (0.75")'
    elif mesh_mm < 25:
        return 'Quarter (1")'
    elif mesh_mm < 38:
        return 'Golf Ball (1.5")'
    elif mesh_mm < 51:
        return 'Baseball (2")'
    else:
        return 'Softball (2"+)'
