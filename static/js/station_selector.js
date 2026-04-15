/**
 * station_selector.js — Search, geolocation, sidebar browse-all.
 */

'use strict';

// ── Search Autocomplete ────────────────────────────────────────────────────────
let searchDebounce = null;

document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('station-search');
    const results = document.getElementById('search-results');

    input.addEventListener('input', () => {
        clearTimeout(searchDebounce);
        const q = input.value.trim();
        if (q.length < 2) {
            results.classList.add('hidden');
            results.innerHTML = '';
            return;
        }
        searchDebounce = setTimeout(() => {
            fetch(`${API_BASE}/stations/search/?q=${encodeURIComponent(q)}`)
                .then(r => r.json())
                .then(stations => {
                    if (!stations.length) {
                        results.classList.add('hidden');
                        return;
                    }
                    results.innerHTML = stations.map(s =>
                        `<div class="search-result-item" data-code="${s.code}">
                            <strong>${s.code}</strong> — ${s.name}, ${s.state}
                        </div>`
                    ).join('');
                    results.classList.remove('hidden');
                    results.querySelectorAll('.search-result-item').forEach(el => {
                        el.addEventListener('click', () => {
                            selectStation(el.dataset.code);
                            input.value = '';
                            results.classList.add('hidden');
                        });
                    });
                })
                .catch(err => console.error('station search failed:', err));
        }, 300);
    });

    // Close dropdown on outside click
    document.addEventListener('click', e => {
        if (!e.target.closest('#search-container')) {
            results.classList.add('hidden');
        }
    });

    // ── Geolocation Button ──────────────────────────────────────────────────
    document.getElementById('btn-geolocate').addEventListener('click', () => {
        if (!navigator.geolocation) {
            alert('Geolocation is not supported by your browser.');
            return;
        }
        navigator.geolocation.getCurrentPosition(
            pos => {
                const { latitude, longitude } = pos.coords;
                fetch(`${API_BASE}/stations/nearest/?lat=${latitude}&lon=${longitude}`)
                    .then(r => r.json())
                    .then(stations => {
                        if (stations.length) selectStation(stations[0].code);
                    })
                    .catch(err => console.error('nearest station failed:', err));
            },
            err => {
                console.error('Geolocation error:', err);
                alert('Could not get your location. Please check permissions.');
            }
        );
    });

    // ── Populate recently viewed from localStorage ──────────────────────────
    const recent = JSON.parse(localStorage.getItem('recentStations') || '[]');
    const list = document.getElementById('recent-list');
    if (recent.length) {
        list.innerHTML = recent.map(s =>
            `<li onclick="selectStation('${s.code}')">${s.code} — ${s.name}, ${s.state}</li>`
        ).join('');
    }
});

// ── Browse All (populated once stations are loaded) ────────────────────────────
function populateBrowseAll(stations) {
    const container = document.getElementById('browse-all');

    // Group by state
    const byState = {};
    stations.forEach(s => {
        const st = s.state || 'XX';
        if (!byState[st]) byState[st] = [];
        byState[st].push(s);
    });

    const stateNames = {
        AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas', CA: 'California',
        CO: 'Colorado', CT: 'Connecticut', DE: 'Delaware', FL: 'Florida', GA: 'Georgia',
        GU: 'Guam', HI: 'Hawaii', ID: 'Idaho', IL: 'Illinois', IN: 'Indiana',
        IA: 'Iowa', KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana', ME: 'Maine',
        MD: 'Maryland', MA: 'Massachusetts', MI: 'Michigan', MN: 'Minnesota',
        MS: 'Mississippi', MO: 'Missouri', MT: 'Montana', NE: 'Nebraska', NV: 'Nevada',
        NH: 'New Hampshire', NJ: 'New Jersey', NM: 'New Mexico', NY: 'New York',
        NC: 'North Carolina', ND: 'North Dakota', OH: 'Ohio', OK: 'Oklahoma',
        OR: 'Oregon', PA: 'Pennsylvania', PR: 'Puerto Rico', RI: 'Rhode Island',
        SC: 'South Carolina', SD: 'South Dakota', TN: 'Tennessee', TX: 'Texas',
        UT: 'Utah', VT: 'Vermont', VA: 'Virginia', WA: 'Washington', WV: 'West Virginia',
        WI: 'Wisconsin', WY: 'Wyoming', XX: 'Other',
    };

    const sortedStates = Object.keys(byState).sort();
    container.innerHTML = sortedStates.map(st => {
        const stateName = stateNames[st] || st;
        const items = byState[st].sort((a, b) => a.code.localeCompare(b.code));
        return `
            <div class="state-group">
                <div class="state-header" onclick="toggleState('${st}')">
                    ${stateName} (${items.length})
                </div>
                <div class="state-stations" id="state-${st}">
                    ${items.map(s =>
                        `<div class="station-list-item" onclick="selectStation('${s.code}')">
                            ${s.code} — ${s.name}
                        </div>`
                    ).join('')}
                </div>
            </div>`;
    }).join('');
}

function toggleState(st) {
    const el = document.getElementById(`state-${st}`);
    if (el) el.classList.toggle('open');
}
