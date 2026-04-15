/**
 * alerts.js — NWS alert GeoJSON layer, always on top, polls every 60s.
 */

'use strict';

let alertsLayer = null;
let alertsData = null;
let alertsRefreshTimer = null;

document.addEventListener('DOMContentLoaded', () => {
    // Wait for map to be initialized by radar_map.js
    setTimeout(() => {
        loadAlerts();
        alertsRefreshTimer = setInterval(loadAlerts, 60000);
    }, 500);
});

function loadAlerts() {
    fetch(`${API_BASE}/alerts/`)
        .then(r => r.json())
        .then(geojson => {
            alertsData = geojson;
            renderAlertLayer(geojson);
            updateAlertsBadge(geojson.features.length);
        })
        .catch(err => console.error('loadAlerts failed:', err));
}

function renderAlertLayer(geojson) {
    if (!map) return;

    if (alertsLayer) {
        map.removeLayer(alertsLayer);
        alertsLayer = null;
    }

    if (!geojson.features || !geojson.features.length) return;

    alertsLayer = L.geoJSON(geojson, {
        pane: 'alertPane',
        style: feature => {
            const color = feature.properties.color || '#999999';
            const isTornado = feature.properties.event &&
                (feature.properties.event.includes('Tornado') ||
                 feature.properties.event.includes('Severe Thunderstorm'));
            return {
                fillColor: color,
                fillOpacity: 0.35,
                color: color,
                weight: isTornado ? 2 : 1,
                className: isTornado ? 'pulse-warning' : '',
            };
        },
        onEachFeature: (feature, layer) => {
            const p = feature.properties;
            const expires = p.expires ? new Date(p.expires).toLocaleString() : 'Unknown';
            layer.bindPopup(`
                <div class="alert-popup">
                    <h4>${p.event || 'Alert'}</h4>
                    <div class="alert-meta">
                        ${p.area_desc || ''}<br>
                        Expires: ${expires}
                        ${p.nws_office ? ' · ' + p.nws_office : ''}
                    </div>
                    ${p.headline ? `<p style="margin-bottom:6px;font-size:12px;">${p.headline}</p>` : ''}
                    ${p.description ?
                        `<div class="alert-desc">${(p.description || '').substring(0, 500)}${
                            p.description.length > 500 ? '...' : ''
                        }</div>` : ''}
                    ${p.instruction ?
                        `<div class="alert-desc" style="margin-top:6px;border-top:1px solid #333;padding-top:6px;">
                            <strong>Instructions:</strong><br>${(p.instruction || '').substring(0, 300)}
                        </div>` : ''}
                </div>
            `, { maxWidth: 320 });
        },
    }).addTo(map);
}

function updateAlertsBadge(count) {
    const badge = document.getElementById('alerts-badge');
    if (!badge) return;
    if (count === 0) {
        badge.textContent = 'No Active Alerts';
        badge.classList.add('no-alerts');
    } else {
        badge.textContent = `⚠ ${count} Active Warning${count !== 1 ? 's' : ''}`;
        badge.classList.remove('no-alerts');
    }
}

function openAlertsPanel() {
    if (!alertsData) return;
    const count = alertsData.features ? alertsData.features.length : 0;
    alert(`${count} active NWS alert${count !== 1 ? 's' : ''} nationwide. Click on the map polygons for details.`);
}
