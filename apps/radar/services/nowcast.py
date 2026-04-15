"""
Nowcasting using pysteps STEPS ensemble.
Generates 0–60 minute forecasts from the last N radar scans.
"""
import logging
import numpy as np

logger = logging.getLogger(__name__)

# Grid resolution (km) and timestep (min)
GRID_RESOLUTION_KM = 1.0
TIMESTEP_MIN = 5


def build_precip_stack(grids):
    """
    Build a (N, H, W) numpy array from a list of Py-ART Grid objects.
    Extracts reflectivity from the lowest grid level.
    Returns numpy array with NaN for missing data.
    """
    frames = []
    for grid in grids:
        ref_field = None
        for candidate in ['reflectivity', 'DBZ', 'REF']:
            if candidate in grid.fields:
                ref_field = candidate
                break
        if ref_field is None:
            ref_field = list(grid.fields.keys())[0]

        data = grid.fields[ref_field]['data'][0].filled(np.nan)
        frames.append(data)

    return np.stack(frames, axis=0)


def run_nowcast(precip_stack):
    """
    Run pysteps STEPS nowcast on a (N, H, W) reflectivity stack.
    Returns list of 12 forecast arrays (5-min intervals, 60 min total).
    """
    from django.conf import settings

    n_timesteps = getattr(settings, 'NOWCAST_TIMESTEPS', 12)

    try:
        import pysteps
        from pysteps import nowcasts
        from pysteps.utils import conversion, transformation

        # Convert dBZ to rain rate (mm/h)
        R_stack = _dbz_to_rainrate(precip_stack)

        # Apply log transformation for STEPS
        R_log, metadata = transformation.dB_transform(
            R_stack,
            metadata={'unit': 'mm/h', 'transform': None, 'accutime': TIMESTEP_MIN,
                      'zerovalue': 0.0, 'threshold': 0.1},
            threshold=0.1,
            zerovalue=-15.0,
        )

        # Run STEPS
        nowcast_method = nowcasts.get_method('steps')
        R_forecast = nowcast_method(
            R_log[-3:],  # STEPS needs last 3 frames
            metadata,
            n_timesteps=n_timesteps,
            n_ens_members=1,
            kmperpixel=GRID_RESOLUTION_KM,
            timestep=TIMESTEP_MIN,
        )

        # Convert back to dBZ for tile rendering
        R_det = R_forecast[0] if R_forecast.ndim == 4 else R_forecast
        result = []
        for i in range(R_det.shape[0]):
            dbz = _rainrate_to_dbz(R_det[i])
            result.append(dbz)
        return result

    except Exception as exc:
        logger.error('run_nowcast failed: %s', exc)
        # Return copies of the last frame as a fallback
        last = precip_stack[-1]
        return [last.copy() for _ in range(n_timesteps)]


def _dbz_to_rainrate(dbz, a=300.0, b=1.4):
    """Convert reflectivity (dBZ) to rain rate (mm/h) using Z-R relationship."""
    Z = 10.0 ** (dbz / 10.0)
    R = (Z / a) ** (1.0 / b)
    R[np.isnan(dbz)] = np.nan
    return R


def _rainrate_to_dbz(R, a=300.0, b=1.4):
    """Convert rain rate (mm/h) back to reflectivity (dBZ)."""
    R_clipped = np.maximum(R, 0.001)
    Z = a * (R_clipped ** b)
    dbz = 10.0 * np.log10(Z)
    dbz[np.isnan(R)] = np.nan
    return dbz
