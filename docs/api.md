# REST API Reference

Base path: `/api/radar/`

All responses are JSON. No authentication required. CSRF token required for POST requests (sent automatically by the browser).

---

## Station Selector

### `GET /api/radar/stations/`

Returns all 159 active WSR-88D radar stations.

**Response:**
```json
[
  {
    "code": "KTLX",
    "name": "Oklahoma City",
    "state": "OK",
    "latitude": 35.3331,
    "longitude": -97.2778,
    "region": ""
  },
  ...
]
```

Used by the map to plot 159 station markers and by the sidebar browse-all list.

---

### `GET /api/radar/stations/search/?q=<query>`

Fuzzy-searches stations by code, name, or state. Returns up to 10 results.

**Query params:**
| Param | Required | Description |
|-------|----------|-------------|
| `q` | Yes | Search string (min 2 characters) |

**Response:** Same format as `/stations/`. Returns `[]` if `q` is empty or < 2 chars.

**Example:**
```
GET /api/radar/stations/search/?q=oklahoma
```
```json
[
  {"code": "KTLX", "name": "Oklahoma City", "state": "OK", ...},
  {"code": "KINX", "name": "Tulsa", "state": "OK", ...}
]
```

---

### `GET /api/radar/stations/nearest/?lat=<lat>&lon=<lon>`

Returns the 3 closest stations to the given coordinates, sorted by distance.

**Query params:**
| Param | Required | Description |
|-------|----------|-------------|
| `lat` | Yes | Latitude (decimal degrees) |
| `lon` | Yes | Longitude (decimal degrees) |

**Response:** Same as `/stations/` plus a `distance_km` field.

```json
[
  {"code": "KTLX", "name": "Oklahoma City", "state": "OK", "distance_km": 12.4, ...},
  {"code": "KFDR", "name": "Frederick", "state": "OK", "distance_km": 89.1, ...},
  {"code": "KVNX", "name": "Enid", "state": "OK", "distance_km": 102.3, ...}
]
```

Distance computed using the Haversine formula in pure Python.

---

### `POST /api/radar/stations/<code>/activate/`

Activates a station for on-demand polling. Creates or refreshes the `ActiveStation` record, resetting the TTL to `STATION_SCAN_TTL` seconds. Immediately queues a scan check.

**URL params:**
| Param | Description |
|-------|-------------|
| `code` | Station code (case-insensitive, e.g. `KTLX`) |

**Headers:** `X-CSRFToken: <csrf-token>`

**Response:**
```json
{
  "status": "activated",
  "station": {
    "code": "KTLX",
    "name": "Oklahoma City",
    "state": "OK",
    "latitude": 35.3331,
    "longitude": -97.2778
  },
  "eta_seconds": 30
}
```

**Frontend note:** Call this every `STATION_SCAN_TTL / 3` seconds (default: every 10 minutes) to keep the station alive. Failing to do so causes the station to be deactivated after 30 minutes.

---

### `GET /api/radar/stations/<code>/status/`

Returns the current processing status for a station. Poll this every 3 seconds after activating until `last_scan_time` is recent.

**Response:**
```json
{
  "is_active": true,
  "last_scan_time": "2024-01-15T18:42:00+00:00",
  "scan_count_last_hour": 8,
  "processing": false
}
```

| Field | Description |
|-------|-------------|
| `is_active` | Whether an unexpired `ActiveStation` record exists |
| `last_scan_time` | ISO 8601 timestamp of the most recent processed scan (`null` if none) |
| `scan_count_last_hour` | Number of scans processed in the last 60 minutes |
| `processing` | `true` if any scans are still being processed |

**Frontend logic:** Stop polling when `last_scan_time` is within the last 15 minutes and `processing` is `false`.

---

## MRMS National Mosaic

### `GET /api/radar/national/latest/?product=<product>`

Returns the most recent MRMS tile for the given product.

**Query params:**
| Param | Default | Options |
|-------|---------|---------|
| `product` | `reflectivity` | `reflectivity`, `precip_type`, `mesh` |

**Response:**
```json
{
  "valid_time": "2024-01-15T18:42:00+00:00",
  "tile_url": "/api/radar/tiles/mrms/MergedReflectivityQC_20240115_184200.png",
  "bounds": {
    "north": 54.99,
    "south": 20.00,
    "east": -60.01,
    "west": -130.00
  }
}
```

**Leaflet usage:**
```javascript
L.imageOverlay(data.tile_url, [[bounds.south, bounds.west], [bounds.north, bounds.east]])
```

---

### `GET /api/radar/national/frames/?product=<product>&minutes=<n>`

Returns an ordered list of MRMS tiles for animation.

**Query params:**
| Param | Default | Description |
|-------|---------|-------------|
| `product` | `reflectivity` | Product name |
| `minutes` | `60` | How far back to fetch frames |

**Response:** Array of frames, oldest first:
```json
[
  {"valid_time": "2024-01-15T17:44:00+00:00", "tile_url": "...", "bounds": {...}},
  {"valid_time": "2024-01-15T17:46:00+00:00", "tile_url": "...", "bounds": {...}},
  ...
]
```

---

## Station-Level NEXRAD

### `GET /api/radar/station/<code>/latest/?product=<product>`

Returns the most recent tile for a station + product.

**Query params:**
| Param | Default | Options |
|-------|---------|---------|
| `product` | `reflectivity` | `reflectivity`, `velocity`, `mesh`, `nowcast_00`…`nowcast_60` |

**Response:** Same format as `/national/latest/`.

---

### `GET /api/radar/station/<code>/frames/?product=<product>&minutes=<n>`

Returns ordered frames for animation. Same format as `/national/frames/`.

---

### `GET /api/radar/station/<code>/hail/`

Returns the latest MESH hail swath as GeoJSON.

**Response:**
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [-97.5, 35.4]
      },
      "properties": {
        "mesh_mm": 42.3,
        "hail_size": "Golf Ball (1.5\")"
      }
    }
  ]
}
```

Returns `{"type": "FeatureCollection", "features": []}` if no hail detected or no scans processed yet.

---

### `GET /api/radar/station/<code>/nowcast/`

Returns nowcast tiles for the latest scan, ordered from +5 min to +60 min.

**Response:**
```json
[
  {"valid_time": "2024-01-15T18:47:00+00:00", "tile_url": "...", "bounds": {...}},
  {"valid_time": "2024-01-15T18:52:00+00:00", "tile_url": "...", "bounds": {...}},
  ...
]
```

Returns `[]` if fewer than 4 scans have been processed (pysteps requires at least 4).

---

## NWS Alerts

### `GET /api/radar/alerts/`

Returns all currently active US NWS alerts as GeoJSON. No area filter — covers the full United States.

**Response:**
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[...]]]
      },
      "properties": {
        "event": "Tornado Warning",
        "severity": "Extreme",
        "headline": "Tornado Warning issued...",
        "description": "...",
        "instruction": "Take shelter immediately...",
        "area_desc": "Central Oklahoma",
        "expires": "2024-01-15T19:15:00+00:00",
        "color": "#FF0000",
        "nws_office": "OUN",
        "alert_id": "urn:oid:2.49.0.1.840.0...."
      }
    }
  ]
}
```

The `color` field is the NWS standard hex color for that event type, ready for use in Leaflet `style()`.

---

## Tile Serving

### `GET /api/radar/tiles/<path>`

Serves a PNG tile file. The `<path>` comes from `tile_url` fields in other API responses.

**Security:** Path traversal is prevented — only paths inside `TILE_OUTPUT_DIR` are served.

**Content-Type:** `image/png`

**Example:**
```
GET /api/radar/tiles/mrms/MergedReflectivityQC_20240115_184200.png
GET /api/radar/tiles/KTLX/KTLX_ref_20240115_184200.png
```

---

## Error Responses

All errors return JSON:

```json
{"error": "Station not found"}
```

| Status | Meaning |
|--------|---------|
| 400 | Missing or invalid query parameters |
| 404 | Station, tile, or data not found |
| 500 | Internal server error (check Celery worker logs) |
