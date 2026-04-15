# Data Pipeline

## MRMS National Mosaic

### What is MRMS?

Multi-Radar/Multi-Sensor (MRMS) is a NOAA system that merges data from all 159 WSR-88D radars into a single seamless CONUS mosaic, updated every 2 minutes. It's the national view in WxRadar.

### S3 Access

```
Bucket: s3://noaa-mrms-pds (public, no credentials)
Path:   CONUS/MergedReflectivityQC_00.00/YYYYMMDD/
File:   MergedReflectivityQC_00.00_YYYYMMDD-HHMMSS.grib2.gz
Size:   ~50 MB per file
```

Files are gzip-compressed GRIB2. The `.gz` is decompressed to a temp file before parsing.

### Parsing

```python
# services/mrms.py
ds = xr.open_dataset(tmp_grib2_path, engine='cfgrib', backend_kwargs={'indexpath': ''})
```

Requires `cfgrib` and `eccodes` system library (`libeccodes2` in Dockerfile runtime stage).

The MRMS longitude values are 0–360 (not −180 to 180). The service converts them:

```python
lons = np.where(lons > 180, lons - 360, lons)
```

Bounds are always read from the dataset metadata — never hardcoded — because they vary slightly between products.

### Rendering

The reflectivity data is rendered using the NWS standard dBZ color scale (16 levels from −30 to 75 dBZ) as a full-CONUS transparent PNG with matplotlib. The image is saved to `TILE_OUTPUT_DIR/mrms/`.

### Retention

The `poll_mrms_mosaic` task keeps the last 60 minutes of tiles (30 frames at 2-min intervals). Older `MRMSTile` records and their files are deleted at the end of each task run.

---

## NEXRAD Level 2

### What is NEXRAD Level 2?

Raw per-station WSR-88D volume scans. Each scan covers a ~230 km radius around the station. Files contain multiple elevation sweeps (tilts) of reflectivity, velocity, and dual-pol fields.

### S3 Access

```
Bucket: s3://noaa-nexrad-level2 (public, no credentials)
Path:   YYYY/MM/DD/KXXX/KXXX20240101_120000_V06
Size:   ~10–25 MB per file
```

Files use the NEXRAD Level 2 archive format (sometimes called "SuperRes" or "V06").

### On-Demand Fetching

NEXRAD data is only downloaded for stations currently in the `ActiveStation` table. The flow:

1. User selects a station → `POST /api/radar/stations/<code>/activate/`
2. `ActiveStation` record created with `expires_at = now() + STATION_SCAN_TTL`
3. `check_station_for_new_scans` queued immediately
4. `poll_active_stations` (every 90s via Beat) re-queues it for all non-expired stations
5. `ActiveStation` auto-expires when user closes the tab or TTL passes

### Py-ART Processing

```python
# services/processor.py

# 1. Load
radar = pyart.io.read_nexrad_archive(file_path)

# 2. Dealias velocity
dealiased = pyart.correct.dealias_region_based(radar, vel_field='velocity')
radar.add_field('dealiased_velocity', dealiased)

# 3. Grid to Cartesian (500×500 km, 1 km resolution, 20 vertical levels)
grid = pyart.map.grid_from_radars(
    (radar,),
    grid_shape=(20, 500, 500),
    grid_limits=((0, 20000), (-230000, 230000), (-230000, 230000)),
    fields=['reflectivity', 'dealiased_velocity'],
    gridding_algo='map_gates_to_grid',
    weighting_function='Barnes2',
)
```

### Tile Rendering

Both reflectivity and velocity are rendered as transparent PNGs at 1000×1000 px. Color scales:

**Reflectivity (NWS standard dBZ):**

| Range | Color |
|-------|-------|
| −30 to 0 | Gray `#646464` |
| 0–5 | Light cyan `#04e9e7` |
| 5–10 | Blue `#019ff4` |
| 10–15 | Dark blue `#0300f4` |
| 15–20 | Light green `#02fd02` |
| 20–25 | Green `#01c501` |
| 25–30 | Dark green `#008e00` |
| 30–35 | Yellow `#fdf802` |
| 35–40 | Dark yellow `#e5bc00` |
| 40–45 | Orange `#fd9500` |
| 45–50 | Red `#fd0000` |
| 50–55 | Dark red `#d40000` |
| 55–60 | Deeper red `#bc0000` |
| 60–65 | Magenta `#f800fd` |
| 65–70 | Purple `#9854c6` |
| 70–75 | White `#fdfdfd` |

**Velocity (diverging, m/s):**

- Strong negative (toward): dark green
- Weak negative: light green
- Near zero: gray
- Weak positive: light red
- Strong positive (away): dark red

Tile geographic bounds are derived from `grid.point_latitude` and `grid.point_longitude` arrays and stored in `RadarTile.bounds_json` as `{north, south, east, west}`. Leaflet's `ImageOverlay` uses `[[south, west], [north, east]]`.

---

## Hail Detection (MESH)

### Algorithm

Maximum Expected Size of Hail (MESH) uses the reflectivity column to estimate hail size at the surface. PyHail implements the Witt et al. (1998) algorithm.

```python
# services/hail.py
mesh_ds = pyhail.mesh.process_single_file(radar)
```

The result is a 2D grid of MESH values in mm. Any grid point ≥ `HAIL_MESH_THRESHOLD` (default 25 mm) is included in the GeoJSON output as a point feature with `mesh_mm` and `hail_size` properties.

### Hail Size Reference

| MESH (mm) | Description |
|-----------|-------------|
| < 6 | Pea (< 0.25") |
| 6–13 | Marble (0.5") |
| 13–19 | Dime (0.75") |
| 19–25 | Quarter (1") |
| 25–38 | Golf Ball (1.5") |
| 38–51 | Baseball (2") |
| > 51 | Softball (2"+) |

---

## Nowcasting (pysteps STEPS)

### Requirements

- At least **4 processed scans** for the station before nowcasting is triggered
- Each scan must have a local file path (`local_path` column not empty)

### Algorithm

Short-Term Ensemble Prediction System (STEPS) uses a Lagrangian advection approach:

1. Last 3–4 reflectivity grids are stacked into a precipitation series
2. dBZ values converted to rain rate (Z-R relationship: Z = 300 R^1.4)
3. Log transform applied for STEPS algorithm stability
4. Optical flow estimated from the last two frames
5. 12 ensemble members × `NOWCAST_TIMESTEPS` (default 12) forecast frames generated
6. Single deterministic member extracted, converted back to dBZ
7. Each of the 12 forecast arrays rendered as a PNG tile

### Output

12 `RadarTile` records per station per nowcast run:
- Products: `nowcast_00`, `nowcast_15`, `nowcast_30`, `nowcast_45`, `nowcast_60` (bucketed)
- Valid times: `latest_scan_time + 5min`, `+10min`, ..., `+60min`

### Fallback

If pysteps fails for any reason, `run_nowcast()` returns copies of the last observed frame as a graceful fallback — the pipeline does not crash.

---

## NWS Alerts

### Source

`GET https://api.weather.gov/alerts/active` — no query parameters, no API key. Returns **all active US alerts** as GeoJSON.

The NWS requires a `User-Agent` header identifying your application and contact email. Set `NWS_USER_AGENT` in `.env`.

### Parsing

Alert geometry is stored as-is from the NWS GeoJSON response (`feature.geometry`). NWS uses GeoJSON coordinate order `[longitude, latitude]`. Leaflet's `L.geoJSON()` handles this correctly — no coordinate swapping needed.

### Alert Colors

Each alert event type maps to an NWS standard color defined in `models.py`:

```python
NWS_ALERT_COLORS = {
    'Tornado Warning':             '#FF0000',
    'Severe Thunderstorm Warning': '#FFA500',
    'Tornado Watch':               '#FFFF00',
    ...
}
```

Unknown event types fall back to `#999999` (gray).

### Retention

`poll_nws_alerts` calls `expire_old_alerts()` at the end of each run, which deletes any `NWSAlert` records where `expires < now()`. The `cleanup_old_data` hourly task also purges expired alerts.
