"""
PNG tile rendering for all radar products.
All tiles use NWS standard color scales, transparent background, WGS84 bounds.
Leaflet ImageOverlay expects [[south, west], [north, east]] bounds.
"""
import logging

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

logger = logging.getLogger(__name__)

# NWS standard reflectivity color scale (dBZ)
REFLECTIVITY_LEVELS = [
    -30, 0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75
]
REFLECTIVITY_COLORS = [
    '#646464', '#04e9e7', '#019ff4', '#0300f4', '#02fd02',
    '#01c501', '#008e00', '#fdf802', '#e5bc00', '#fd9500',
    '#fd0000', '#d40000', '#bc0000', '#f800fd', '#9854c6', '#fdfdfd',
]

# Velocity diverging scale (m/s)
VELOCITY_LEVELS = [-50, -30, -20, -10, -5, -1, 0, 1, 5, 10, 20, 30, 50]
VELOCITY_COLORS = [
    '#006400', '#228B22', '#32CD32', '#90EE90', '#ADFF2F', '#808080',
    '#808080', '#FFB6C1', '#FF4500', '#DC143C', '#8B0000', '#4B0000',
]

# MESH hail color scale (mm)
MESH_LEVELS = [0, 5, 10, 15, 25, 38, 50, 76]
MESH_COLORS = ['#00000000', '#00cc00', '#ffff00', '#ff8800', '#ff0000', '#8b0000', '#800080']


def _make_cmap_norm(levels, colors):
    cmap = mcolors.ListedColormap(colors)
    norm = mcolors.BoundaryNorm(levels, cmap.N)
    return cmap, norm


def _grid_bounds(grid):
    """Extract WGS84 bounds from a Py-ART Grid object."""
    # grid.point_latitude/longitude are in degrees
    lats = grid.point_latitude['data']
    lons = grid.point_longitude['data']
    return {
        'north': float(lats.max()),
        'south': float(lats.min()),
        'east': float(lons.max()),
        'west': float(lons.min()),
    }


def _render_grid_png(data_2d, cmap, norm, output_path, bounds):
    """Render a 2D numpy array to a transparent-background PNG."""
    fig = plt.figure(figsize=(10, 10), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()

    masked = np.ma.masked_invalid(data_2d)
    ax.imshow(
        masked,
        cmap=cmap,
        norm=norm,
        origin='upper',
        aspect='auto',
        interpolation='nearest',
    )
    fig.savefig(output_path, transparent=True, bbox_inches='tight', pad_inches=0, dpi=100)
    plt.close(fig)
    return output_path, bounds


def render_reflectivity_tile(grid, output_path):
    """
    Render base reflectivity from a Py-ART Grid to a PNG tile.
    Returns (tile_path, bounds_dict).
    """
    cmap, norm = _make_cmap_norm(REFLECTIVITY_LEVELS, REFLECTIVITY_COLORS)
    bounds = _grid_bounds(grid)

    # Use lowest sweep (index 0 in z)
    ref_field = None
    for candidate in ['reflectivity', 'DBZ', 'REF']:
        if candidate in grid.fields:
            ref_field = candidate
            break
    if ref_field is None:
        ref_field = list(grid.fields.keys())[0]

    data = grid.fields[ref_field]['data'][0]  # first z level
    return _render_grid_png(data, cmap, norm, output_path, bounds)


def render_velocity_tile(grid, output_path):
    """
    Render dealiased velocity from a Py-ART Grid to a PNG tile.
    Returns (tile_path, bounds_dict).
    """
    cmap, norm = _make_cmap_norm(VELOCITY_LEVELS, VELOCITY_COLORS)
    bounds = _grid_bounds(grid)

    vel_field = None
    for candidate in ['dealiased_velocity', 'velocity', 'VEL']:
        if candidate in grid.fields:
            vel_field = candidate
            break
    if vel_field is None:
        logger.warning('render_velocity_tile: no velocity field in grid')
        # Render blank tile
        fig = plt.figure(figsize=(10, 10))
        plt.savefig(output_path, transparent=True)
        plt.close()
        return output_path, bounds

    data = grid.fields[vel_field]['data'][0]
    return _render_grid_png(data, cmap, norm, output_path, bounds)


def render_mesh_tile(mesh_data, output_path):
    """
    Render a MESH hail array to a PNG tile.
    mesh_data: dict with 'data' (2D array), 'lats', 'lons'
    Returns (tile_path, bounds_dict).
    """
    cmap, norm = _make_cmap_norm(MESH_LEVELS, MESH_COLORS)
    bounds = {
        'north': float(mesh_data['lats'].max()),
        'south': float(mesh_data['lats'].min()),
        'east': float(mesh_data['lons'].max()),
        'west': float(mesh_data['lons'].min()),
    }
    return _render_grid_png(mesh_data['data'], cmap, norm, output_path, bounds)


def render_nowcast_tile(array, output_path):
    """
    Render a pysteps nowcast array to a PNG tile.
    array: 2D numpy array of reflectivity values.
    Returns (tile_path, bounds_dict) — caller must supply bounds separately.
    """
    cmap, norm = _make_cmap_norm(REFLECTIVITY_LEVELS, REFLECTIVITY_COLORS)
    # Placeholder bounds — caller updates RadarTile.bounds_json from the scan's grid bounds
    bounds = {'north': 0, 'south': 0, 'east': 0, 'west': 0}

    fig = plt.figure(figsize=(10, 10), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    masked = np.ma.masked_invalid(array)
    ax.imshow(masked, cmap=cmap, norm=norm, origin='upper', aspect='auto', interpolation='nearest')
    fig.savefig(output_path, transparent=True, bbox_inches='tight', pad_inches=0, dpi=100)
    plt.close(fig)
    return output_path, bounds
