# Frontend

The frontend is vanilla JavaScript + Leaflet. No build step, no npm — just files in `static/js/` served by Whitenoise.

## Files

| File | Responsibility |
|------|---------------|
| `radar_map.js` | Map init, national/station mode, station markers, refresh loop |
| `station_selector.js` | Search autocomplete, geolocation, sidebar browse-all |
| `alerts.js` | NWS alert GeoJSON layer, badge counter |
| `radar_animate.js` | Frame animation helpers (step forward/back, play/pause) |

Load order in `map.html`:
```html
<script src="radar_map.js"></script>      <!-- defines map, selectStation(), returnToNational() -->
<script src="station_selector.js"></script> <!-- depends on map, allStations -->
<script src="alerts.js"></script>          <!-- depends on map -->
<script src="radar_animate.js"></script>   <!-- depends on stationLayer -->
```

## Global State (`radar_map.js`)

```javascript
let map;              // Leaflet Map instance
let allStations = []; // All 159 station objects from /api/radar/stations/
let currentStation;   // Currently selected station code (null = national view)
let currentProduct;   // 'reflectivity' | 'velocity' | 'mesh' | 'nowcast_00'
let mrmsLayer;        // L.imageOverlay for national MRMS tile
let stationLayer;     // L.imageOverlay for station radar tile
let rangeRing;        // L.circle showing 230km station range
let stationMarkers;   // {code: L.marker} for all 159 markers
```

## Leaflet Map

Initialized with `center: [38.5, -98.0], zoom: 4` (full CONUS view).

Two custom panes:
- `radarPane` (z-index 400) — MRMS and station radar tiles
- `alertPane` (z-index 650) — NWS alert polygons, always on top of radar

Basemap: CartoDB Dark Matter (no API key needed).

## Station Selection Flow

```javascript
selectStation('KTLX')
  ├── POST /api/radar/stations/KTLX/activate/
  ├── showLoadingOverlay("Loading radar for KTLX...")
  ├── map.setView([35.33, -97.28], 7)
  ├── Draw L.circle(latlng, {radius: 230000}) — range ring
  ├── setInterval(pollStationStatus, 3000)
  │     └── GET /api/radar/stations/KTLX/status/
  │         └── When last_scan_time < 15 min ago:
  │               clearInterval()
  │               hideLoadingOverlay()
  │               loadStationFrames('KTLX', 'reflectivity')
  │               startRefreshLoop('KTLX')
  ├── updateRecentlyViewed(station)  → localStorage
  └── setInterval(keepAlive, 600000) → POST activate every 10 min
```

## National / Station Mode Toggle

```javascript
returnToNational()
  ├── currentStation = null
  ├── clearInterval(keepAliveTimer, refreshTimer, statusPollTimer)
  ├── map.removeLayer(stationLayer), map.removeLayer(rangeRing)
  ├── Deselect all markers
  ├── map.setView([38.5, -98.0], 4)
  ├── loadNationalMosaic()
  └── localStorage.removeItem('lastStation')
```

## Product Switching

```javascript
switchProduct('velocity')
  ├── currentProduct = 'velocity'
  ├── Update .active class on product buttons
  └── loadStationFrames(currentStation, 'velocity')
```

Available products: `reflectivity`, `velocity`, `mesh`, `nowcast_00`

## localStorage Keys

| Key | Value | Purpose |
|-----|-------|---------|
| `lastStation` | `"KTLX"` | Auto-restore last station on page reload |
| `recentStations` | JSON array of station objects | Sidebar "Recently Viewed" list (max 5) |

## Search Autocomplete

`station_selector.js` attaches to `#station-search` input:

- Debounced 300ms to avoid spamming the API
- `GET /api/radar/stations/search/?q=<value>`
- Dropdown renders up to 10 results: `<strong>KTLX</strong> — Oklahoma City, OK`
- Click → `selectStation(code)`, closes dropdown
- Click outside → closes dropdown

## Geolocation

```javascript
navigator.geolocation.getCurrentPosition(pos => {
  fetch(`/api/radar/stations/nearest/?lat=${lat}&lon=${lon}`)
    .then(r => r.json())
    .then(stations => selectStation(stations[0].code))
})
```

Requires HTTPS in production (browser security requirement for geolocation).

## Browse All (Sidebar Accordion)

`populateBrowseAll(stations)` in `station_selector.js`:
- Groups 159 stations by state, sorted A–Z
- Renders collapsible `<div>` per state
- `toggleState('OK')` shows/hides that state's stations
- Each station row: `selectStation(code)` on click

## NWS Alert Layer (`alerts.js`)

```javascript
// On load + every 60s
fetch('/api/radar/alerts/')
  → L.geoJSON(geojson, {
      pane: 'alertPane',
      style: feature => ({
        fillColor: feature.properties.color,
        fillOpacity: 0.35,
        color: feature.properties.color,
        weight: 2,
        className: isTornado ? 'pulse-warning' : '',
      }),
      onEachFeature: (feature, layer) => layer.bindPopup(...)
    })
```

The `pulse-warning` CSS class animates the stroke opacity for tornado warnings.

Alert count badge updates automatically: `⚠ 4 Active Warnings`.

## Tile Display

All radar imagery uses `L.imageOverlay`:

```javascript
L.imageOverlay(tile_url, [[south, west], [north, east]], {
  opacity: 0.85,
  pane: 'radarPane',
})
```

The `bounds` from the API (`{north, south, east, west}`) maps to Leaflet's `[[south, west], [north, east]]` format.

## CSS Theme

`static/css/map.css` implements a dark GitHub-inspired theme using CSS custom properties:

```css
:root {
  --bg-dark:    #0d1117;  /* page background */
  --bg-panel:   #161b22;  /* topbar, sidebar, bottombar */
  --bg-panel2:  #21262d;  /* inputs, hover states */
  --accent:     #1f6feb;  /* active buttons, links */
  --border:     #30363d;  /* dividers */
  --text:       #e6edf3;  /* primary text */
  --text-muted: #8b949e;  /* secondary text */
}
```

Layout is flex-based: `#app` is a full-viewport column containing topbar → main-layout → bottombar. `#main-layout` is a row: sidebar + map.

## Adding a New Product

1. Add tile rendering in `services/tiles.py`
2. Add product to `process_nexrad_scan` task in `tasks.py`
3. Add `RadarTile.PRODUCT_CHOICES` entry in `models.py`
4. Add a button in `map.html` bottom bar
5. Handle in `switchProduct()` in `radar_map.js`
