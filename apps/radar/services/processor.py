"""
Py-ART NEXRAD Level 2 processing: load, dealias velocity, grid to Cartesian.
"""
import logging

import pyart
import numpy as np

logger = logging.getLogger(__name__)


def load_nexrad(file_path):
    """
    Load a NEXRAD Level 2 archive file with Py-ART.
    Returns pyart.core.Radar object.
    """
    logger.debug('load_nexrad: reading %s', file_path)
    radar = pyart.io.read_nexrad_archive(file_path)
    return radar


def extract_reflectivity(radar):
    """
    Extract base reflectivity from a Py-ART Radar object.
    Returns (data_array, metadata) tuple.
    """
    ref_field = 'reflectivity'
    if ref_field not in radar.fields:
        # Try alternate field names
        for candidate in ['DBZ', 'REF', 'Reflectivity']:
            if candidate in radar.fields:
                ref_field = candidate
                break

    data = radar.fields[ref_field]['data']
    metadata = {
        'units': radar.fields[ref_field].get('units', 'dBZ'),
        'long_name': radar.fields[ref_field].get('long_name', 'Reflectivity'),
        'field_name': ref_field,
    }
    return data, metadata


def dealias_velocity(radar):
    """
    Apply region-based velocity dealiasing to a Py-ART Radar object.
    Returns the radar with dealiased velocity field added.
    """
    vel_field = None
    for candidate in ['velocity', 'VEL', 'radial_velocity']:
        if candidate in radar.fields:
            vel_field = candidate
            break

    if vel_field is None:
        logger.warning('dealias_velocity: no velocity field found, skipping dealiasing')
        return radar

    try:
        dealiased = pyart.correct.dealias_region_based(
            radar,
            vel_field=vel_field,
            skip_checks=True,
        )
        radar.add_field('dealiased_velocity', dealiased, replace_existing=True)
    except Exception as exc:
        logger.warning('dealias_velocity: dealiasing failed: %s', exc)

    return radar


def radar_to_grid(radar, fields=None):
    """
    Grid a Py-ART Radar object to Cartesian coordinates.
    Default grid: 500x500 km at 1 km resolution, 20 vertical levels.
    Returns pyart.core.Grid object.
    """
    if fields is None:
        fields = ['reflectivity']

    # Map requested field names to what's actually in the radar
    field_map = {
        'reflectivity': None,
        'velocity': None,
    }
    for candidate in ['reflectivity', 'DBZ', 'REF', 'Reflectivity']:
        if candidate in radar.fields:
            field_map['reflectivity'] = candidate
            break
    for candidate in ['dealiased_velocity', 'velocity', 'VEL']:
        if candidate in radar.fields:
            field_map['velocity'] = candidate
            break

    actual_fields = [field_map[f] for f in fields if field_map.get(f)]
    if not actual_fields:
        actual_fields = list(radar.fields.keys())[:2]

    grid = pyart.map.grid_from_radars(
        (radar,),
        grid_shape=(20, 500, 500),
        grid_limits=(
            (0, 20000),       # z: 0–20 km
            (-230000, 230000), # y: ±230 km
            (-230000, 230000), # x: ±230 km
        ),
        fields=actual_fields,
        gridding_algo='map_gates_to_grid',
        weighting_function='Barnes2',
    )
    return grid
