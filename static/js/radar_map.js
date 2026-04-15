/**
 * radar_map.js — Core map logic
 * Handles Leaflet init, national/station mode switching, refresh loop.
 */

'use strict';

// ── Globals ──────────────────────────────────────────────────────────────────
let map;
let allStations = [];
let currentStation = null;
let currentProduct = 'reflectivity';
let mrmsLayer = null;
let stationLayer = null;
let rangeRing = null;
let stationMarkers = {};
let keepAliveTimer = null;
let refreshTimer = null;
let lastKnownValidTime = null;
let statusPollTimer = null;

// ── Map Init ─────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    map = L.map('map', {
        center: [38.5, -98.0],
        zoom: 4,
        zoomControl: true,
        preferCanvas: true,
    });

    // Dark basemap (CartoDB Dark Matter)
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
        maxZoom: 19,
        subdomains: 'abcd',
    }).addTo(map);

    // Alert layer pane (always on top)
    map.createPane('alertPane');
    map.getPane('alertPane').style.zIndex = 650;

    // Radar layer pane
    map.createPane('radarPane');
    map.getPane('radarPane').style.zIndex = 400;

    // Load stations and draw markers
    fetchStations();

    // Load MRMS national mosaic
    loadNationalMosaic();

    // Restore last selected station
    const lastStation = localStorage.getItem('lastStation');
    if (lastStation) {
        setTimeout(() => selectStation(lastStation), 800);
    }
});

// ── Station Markers ───────────────────────────────────────────────────────────
function fetchStations() {
    fetch(`${API_BASE}/stations/`)
        .then(r => r.json())
        .then(stations => {
            allStations = stations;
            stations.forEach(s => {
                const icon = L.divIcon({
                    html: '<div class="station-marker"></div>',
                    className: '',
                    iconSize: [10, 10],
                    iconAnchor: [5, 5],
                });
                const marker = L.marker([s.latitude, s.longitude], { icon })
                    .addTo(map)
                    .bindTooltip(`${s.code} — ${s.name}, ${s.state}`, { direction: 'top' })
                    .on('click', () => selectStation(s.code));
                stationMarkers[s.code] = marker;
            });
            // Populate sidebar browse list
            if (typeof populateBrowseAll === 'function') populateBrowseAll(stations);
        })
        .catch(err => console.error('fetchStations failed:', err));
}

// ── National MRMS Mode ────────────────────────────────────────────────────────
function loadNationalMosaic() {
    fetch(`${API_BASE}/national/frames/?product=reflectivity&minutes=60`)
        .then(r => r.json())
        .then(frames => {
            if (!frames.length) {
                // Fallback: try latest single frame
                return fetch(`${API_BASE}/national/latest/?product=reflectivity`)
                    .then(r => r.json())
                    .then(data => data.tile_url ? [data] : []);
            }
            return frames;
        })
        .then(frames => {
            if (mrmsLayer) map.removeLayer(mrmsLayer);
            if (!frames.length) return;

            const latest = frames[frames.length - 1];
            const b = latest.bounds;
            mrmsLayer = L.imageOverlay(latest.tile_url, [[b.south, b.west], [b.north, b.east]], {
                opacity: 0.85,
                pane: 'radarPane',
            }).addTo(map);

            updateTimeDisplay(latest.valid_time);
        })
        .catch(err => console.error('loadNationalMosaic failed:', err));
}

// ── Station Mode ──────────────────────────────────────────────────────────────
function selectStation(code) {
    code = code.toUpperCase();
    const station = allStations.find(s => s.code === code);
    if (!station) {
        console.warn('selectStation: unknown code', code);
        return;
    }

    // Mark as selected visually
    Object.keys(stationMarkers).forEach(c => {
        const el = stationMarkers[c].getElement();
        if (el) el.querySelector('.station-marker').classList.remove('selected');
    });
    const selEl = stationMarkers[code]?.getElement();
    if (selEl) selEl.querySelector('.station-marker').classList.add('selected');

    currentStation = code;

    // Remove national layer
    if (mrmsLayer) { map.removeLayer(mrmsLayer); mrmsLayer = null; }
    if (stationLayer) { map.removeLayer(stationLayer); stationLayer = null; }
    if (rangeRing) { map.removeLayer(rangeRing); rangeRing = null; }

    // Show loading
    showLoadingOverlay(`Loading radar for ${station.code} — ${station.name}`);

    // Activate on server
    fetch(`${API_BASE}/stations/${code}/activate/`, { method: 'POST',
        headers: { 'X-CSRFToken': getCsrfToken() } })
        .then(r => r.json())
        .then(() => {
            // Zoom to station
            map.setView([station.latitude, station.longitude], 7);

            // Range ring (230 km radius)
            rangeRing = L.circle([station.latitude, station.longitude], {
                radius: 230000,
                color: 'rgba(255,255,255,0.3)',
                weight: 1,
                dashArray: '6,4',
                fill: false,
            }).addTo(map);

            // Poll status until data arrives
            pollStationStatus(code);
        })
        .catch(err => console.error('station activate failed:', err));

    // Update sidebar
    updateRecentlyViewed(station);
    updateActiveStationInfo(station);

    // Keep-alive timer
    clearInterval(keepAliveTimer);
    keepAliveTimer = setInterval(() => {
        if (currentStation === code) {
            fetch(`${API_BASE}/stations/${code}/activate/`, {
                method: 'POST',
                headers: { 'X-CSRFToken': getCsrfToken() },
            });
        }
    }, 10 * 60 * 1000); // every 10 minutes

    // Save to localStorage
    localStorage.setItem('lastStation', code);
}

function pollStationStatus(code) {
    clearInterval(statusPollTimer);
    statusPollTimer = setInterval(() => {
        fetch(`${API_BASE}/stations/${code}/status/`)
            .then(r => r.json())
            .then(status => {
                if (status.last_scan_time && !status.processing) {
                    const scanTime = new Date(status.last_scan_time);
                    const ageMin = (Date.now() - scanTime.getTime()) / 60000;
                    if (ageMin < 15) {
                        clearInterval(statusPollTimer);
                        hideLoadingOverlay();
                        loadStationFrames(code, currentProduct);
                        startRefreshLoop(code);
                    }
                }
            })
            .catch(err => console.error('pollStationStatus failed:', err));
    }, 3000);

    // Timeout after 90 seconds
    setTimeout(() => {
        clearInterval(statusPollTimer);
        hideLoadingOverlay();
        loadStationFrames(code, currentProduct);
    }, 90000);
}

function loadStationFrames(code, product) {
    if (stationLayer) { map.removeLayer(stationLayer); stationLayer = null; }

    const url = product.startsWith('nowcast')
        ? `${API_BASE}/station/${code}/nowcast/`
        : `${API_BASE}/station/${code}/frames/?product=${product}&minutes=60`;

    fetch(url)
        .then(r => r.json())
        .then(frames => {
            if (!frames.length) return;
            const latest = frames[frames.length - 1];
            const b = latest.bounds;
            if (!b || (b.north === 0 && b.south === 0)) return;

            stationLayer = L.imageOverlay(latest.tile_url, [[b.south, b.west], [b.north, b.east]], {
                opacity: 0.85,
                pane: 'radarPane',
            }).addTo(map);

            lastKnownValidTime = latest.valid_time;
            updateTimeDisplay(latest.valid_time);
        })
        .catch(err => console.error('loadStationFrames failed:', err));
}

function startRefreshLoop(code) {
    clearInterval(refreshTimer);
    refreshTimer = setInterval(() => {
        if (!currentStation) return;
        const product = currentProduct;
        const endpoint = product.startsWith('nowcast')
            ? `${API_BASE}/station/${code}/nowcast/`
            : `${API_BASE}/station/${code}/latest/?product=${product}`;

        fetch(endpoint)
            .then(r => r.json())
            .then(data => {
                const frame = Array.isArray(data) ? data[data.length - 1] : data;
                if (!frame || !frame.valid_time) return;
                if (frame.valid_time !== lastKnownValidTime) {
                    loadStationFrames(code, product);
                }
            })
            .catch(() => {});
    }, 90000);
}

// ── Product Switching ─────────────────────────────────────────────────────────
function switchProduct(product) {
    currentProduct = product;
    document.querySelectorAll('.product-btn').forEach(btn => btn.classList.remove('active'));
    const labels = { reflectivity: 'Reflectivity', velocity: 'Velocity',
                     mesh: 'MESH', nowcast_00: 'Nowcast' };
    document.querySelectorAll('.product-btn').forEach(btn => {
        if (btn.textContent === (labels[product] || product)) btn.classList.add('active');
    });

    if (currentStation) loadStationFrames(currentStation, product);
}

// ── Return to National ────────────────────────────────────────────────────────
function returnToNational() {
    currentStation = null;
    clearInterval(keepAliveTimer);
    clearInterval(refreshTimer);
    clearInterval(statusPollTimer);
    hideLoadingOverlay();

    if (stationLayer) { map.removeLayer(stationLayer); stationLayer = null; }
    if (rangeRing) { map.removeLayer(rangeRing); rangeRing = null; }

    // Deselect all markers
    Object.values(stationMarkers).forEach(marker => {
        const el = marker.getElement();
        if (el) el.querySelector('.station-marker')?.classList.remove('selected');
    });

    // Zoom to CONUS
    map.setView([38.5, -98.0], 4);
    loadNationalMosaic();

    localStorage.removeItem('lastStation');
    document.getElementById('active-station-info').classList.add('hidden');
}

// ── UI Helpers ────────────────────────────────────────────────────────────────
function showLoadingOverlay(message) {
    let overlay = document.getElementById('loading-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'loading-overlay';
        overlay.innerHTML = `<h3 id="loading-msg"></h3><div class="spinner"></div>`;
        document.getElementById('map').style.position = 'relative';
        document.getElementById('map').appendChild(overlay);
    }
    document.getElementById('loading-msg').textContent = message;
    overlay.classList.remove('hidden');
}

function hideLoadingOverlay() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.classList.add('hidden');
}

function updateTimeDisplay(isoString) {
    const el = document.getElementById('time-display');
    if (!el || !isoString) return;
    const d = new Date(isoString);
    el.textContent = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) +
        ' ' + Intl.DateTimeFormat().resolvedOptions().timeZone;
}

function updateActiveStationInfo(station) {
    const el = document.getElementById('active-station-info');
    document.getElementById('active-station-name').textContent =
        `${station.code} — ${station.name}, ${station.state}`;
    el.classList.remove('hidden');
}

function updateRecentlyViewed(station) {
    let recent = JSON.parse(localStorage.getItem('recentStations') || '[]');
    recent = recent.filter(s => s.code !== station.code);
    recent.unshift(station);
    recent = recent.slice(0, 5);
    localStorage.setItem('recentStations', JSON.stringify(recent));

    const list = document.getElementById('recent-list');
    list.innerHTML = recent.map(s =>
        `<li onclick="selectStation('${s.code}')">${s.code} — ${s.name}, ${s.state}</li>`
    ).join('');
}

function toggleBrowseAll() {
    const panel = document.getElementById('browse-all');
    panel.classList.toggle('hidden');
}

function getCsrfToken() {
    const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
    return cookie ? cookie.trim().split('=')[1] : '';
}

function showAlerts() {
    // Handled by alerts.js
    if (typeof openAlertsPanel === 'function') openAlertsPanel();
}
