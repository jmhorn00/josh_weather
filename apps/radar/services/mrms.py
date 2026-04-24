"""
MRMS grib2 parsing and CONUS tile rendering.
Files are gzip-compressed grib2, read with cfgrib engine via xarray.
Bounds are always read from grib2 metadata, never hardcoded.

cfgrib / eccodes have no Windows wheels. On Windows, install
requirements/windows-dev.txt and run MRMS tasks inside Docker.
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

try:
    import xarray as xr
    import cfgrib  # noqa: F401 — verify cfgrib backend is present
    _XARRAY_CFGRIB_OK = True
except ImportError as _xr_err:  # pragma: no cover
    xr = None  # type: ignore[assignment]
    _XARRAY_CFGRIB_OK = False
    logging.getLogger(__name__).warning(
        'cfgrib/xarray not available (%s). MRMS parsing unavailable on this platform.',
        _xr_err,
    )

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
    # Use delete=False so the temp file can be reopened on Windows.
    # Caller is responsible for unlinking after use.
    fd, tmp_path = tempfile.mkstemp(suffix='.grib2')
    try:
        with os.fdopen(fd, 'wb') as f_out:
            with gzip.open(file_path, 'rb') as f_in:
                shutil.copyfileobj(f_in, f_out)
    except Exception:
        os.unlink(tmp_path)
        raise
    return tmp_path


def parse_mrms_grib(file_path):
    """
    Parse an MRMS grib2.gz file and return an xarray Dataset.
    Decompresses .gz if needed before opening with cfgrib.
    Data is eagerly loaded into memory so the underlying file handle is
    released before the temp file is deleted — required on Windows.
    """
    if file_path.endswith('.gz'):
        tmp_path = _decompress_grib(file_path)
        try:
            with xr.open_dataset(
                tmp_path,
                engine='cfgrib',
                backend_kwargs={'indexpath': ''},
            ) as raw_ds:
                ds = raw_ds.load()  # pull all data into RAM; releases file lock
        finally:
            try:
                os.unlink(tmp_path)
            except OSError as exc:
                logger.warning('Could not delete temp grib2 file %s: %s', tmp_path, exc)
    else:
        with xr.open_dataset(
            file_path,
            engine='cfgrib',
            backend_kwargs={'indexpath': ''},
        ) as raw_ds:
            ds = raw_ds.load()
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

    # plt.cm.get_cmap() removed in matplotlib 3.9 — use colormaps registry
    cmap = matplotlib.colormaps.get_cmap('tab20').resampled(20)
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
