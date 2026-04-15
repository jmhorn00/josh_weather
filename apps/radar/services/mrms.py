"""
MRMS grib2 parsing and CONUS tile rendering.
Files are gzip-compressed grib2, read with cfgrib engine via xarray.
Bounds are always read from grib2 metadata, never hardcoded.
"""
import gzip
import logging
import os
import shutil
import tempfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import xarray as xr

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

REF_CMAP = mcolors.ListedColormap(REFLECTIVITY_COLORS)
REF_NORM = mcolors.BoundaryNorm(REFLECTIVITY_LEVELS, REF_CMAP.N)


def _decompress_grib(file_path):
    """Decompress .grib2.gz to a temporary .grib2 file. Returns temp file path."""
    tmp = tempfile.NamedTemporaryFile(suffix='.grib2', delete=False)
    tmp.close()
    with gzip.open(file_path, 'rb') as f_in:
        with open(tmp.name, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    return tmp.name


def parse_mrms_grib(file_path):
    """
    Parse an MRMS grib2.gz file and return an xarray Dataset.
    Decompresses .gz if needed before opening with cfgrib.
    """
    if file_path.endswith('.gz'):
        tmp_path = _decompress_grib(file_path)
        try:
            ds = xr.open_dataset(
                tmp_path,
                engine='cfgrib',
                backend_kwargs={'indexpath': ''},
            )
        finally:
            os.unlink(tmp_path)
    else:
        ds = xr.open_dataset(
            file_path,
            engine='cfgrib',
            backend_kwargs={'indexpath': ''},
        )
    return ds


def _get_bounds(ds):
    """Extract geographic bounds from xarray dataset. Returns dict."""
    lats = ds['latitude'].values if 'latitude' in ds else ds['y'].values
    lons = ds['longitude'].values if 'longitude' in ds else ds['x'].values
    # MRMS longitudes are 0-360; convert to -180 to 180
    if lons.max() > 180:
        lons = np.where(lons > 180, lons - 360, lons)
    return {
        'north': float(lats.max()),
        'south': float(lats.min()),
        'east': float(lons.max()),
        'west': float(lons.min()),
    }


def _render_png(data_array, cmap, norm, output_path, bounds):
    """Render a 2D array as a transparent-background PNG."""
    fig = plt.figure(figsize=(20, 10), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()

    # Mask no-data values
    masked = np.ma.masked_less(data_array, -30)

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


def render_mrms_reflectivity(ds, output_path):
    """
    Render MRMS reflectivity grib2 dataset to a PNG tile.
    Returns (tile_path, bounds_dict).
    """
    bounds = _get_bounds(ds)

    # The main variable name varies — find the first data variable
    var_name = list(ds.data_vars)[0]
    data = ds[var_name].values

    # Handle 3D arrays (time, lat, lon) by taking first slice
    if data.ndim == 3:
        data = data[0]

    return _render_png(data, REF_CMAP, REF_NORM, output_path, bounds)


def render_mrms_precip_type(ds, output_path):
    """Render MRMS precipitation type tile. Returns (tile_path, bounds_dict)."""
    bounds = _get_bounds(ds)
    var_name = list(ds.data_vars)[0]
    data = ds[var_name].values
    if data.ndim == 3:
        data = data[0]

    cmap = plt.cm.get_cmap('tab20', 20)
    norm = mcolors.BoundaryNorm(range(21), cmap.N)
    return _render_png(data, cmap, norm, output_path, bounds)


def render_mrms_mesh(ds, output_path):
    """Render MRMS MESH hail tile. Returns (tile_path, bounds_dict)."""
    bounds = _get_bounds(ds)
    var_name = list(ds.data_vars)[0]
    data = ds[var_name].values
    if data.ndim == 3:
        data = data[0]

    cmap = mcolors.LinearSegmentedColormap.from_list(
        'mesh', ['#00000000', '#00ff00', '#ffff00', '#ff8800', '#ff0000', '#8b0000'], N=256
    )
    norm = mcolors.Normalize(vmin=0, vmax=100)
    return _render_png(data, cmap, norm, output_path, bounds)
