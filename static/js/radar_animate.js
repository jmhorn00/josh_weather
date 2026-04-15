/**
 * radar_animate.js — TimeDimension animation helpers.
 * Provides frame-by-frame playback using Leaflet.TimeDimension.
 */

'use strict';

let timeDimension = null;
let tdLayer = null;
let animationFrames = [];
let currentFrameIndex = 0;
let isPlaying = false;
let playTimer = null;

/**
 * Load frames for animation.
 * frames: [{valid_time, tile_url, bounds}, ...]
 */
function loadAnimationFrames(frames) {
    animationFrames = frames || [];
    currentFrameIndex = Math.max(0, animationFrames.length - 1);
    renderCurrentFrame();
}

function renderCurrentFrame() {
    if (!animationFrames.length || !map) return;
    const frame = animationFrames[currentFrameIndex];
    if (!frame) return;

    if (stationLayer) { map.removeLayer(stationLayer); stationLayer = null; }

    const b = frame.bounds;
    if (!b || (b.north === 0 && b.south === 0)) return;

    stationLayer = L.imageOverlay(frame.tile_url, [[b.south, b.west], [b.north, b.east]], {
        opacity: 0.85,
        pane: 'radarPane',
    }).addTo(map);

    updateTimeDisplay(frame.valid_time);
}

function stepForward() {
    if (!animationFrames.length) return;
    currentFrameIndex = (currentFrameIndex + 1) % animationFrames.length;
    renderCurrentFrame();
}

function stepBackward() {
    if (!animationFrames.length) return;
    currentFrameIndex = (currentFrameIndex - 1 + animationFrames.length) % animationFrames.length;
    renderCurrentFrame();
}

function togglePlay() {
    if (isPlaying) {
        clearInterval(playTimer);
        isPlaying = false;
    } else {
        isPlaying = true;
        playTimer = setInterval(() => {
            currentFrameIndex = (currentFrameIndex + 1) % animationFrames.length;
            // Loop: pause 2s on last frame before restarting
            renderCurrentFrame();
        }, 500);
    }
}
