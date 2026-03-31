// main.js  –  video analysis player with overlay + timeline

let currentAnomalyIndex = 0;
let allAnomalies = [];
let videoElement = null;
let isPlaying = false;
let overlayCanvas = null;
let overlayCtx = null;

/** Entry point – called from dashboard.html */
function loadVideoPlayer(videoSrc, anomalies) {
    console.log('🎬 Loading video player:', videoSrc, 'with', anomalies.length, 'anomalies');

    videoElement = document.getElementById('video-player');
    overlayCanvas = document.getElementById('anomaly-overlay');

    if (!videoElement || !overlayCanvas) {
        console.error('Video or canvas not found');
        return;
    }

    overlayCtx = overlayCanvas.getContext('2d');

    allAnomalies = (anomalies || []).slice().sort((a, b) => a.frame_timestamp - b.frame_timestamp);
    currentAnomalyIndex = 0;

    // set video source and controls
    if (videoSrc) videoElement.src = videoSrc;
    videoElement.controls = true;

    videoElement.addEventListener('error', (e) => {
        console.error('❌ Video failed to load', e);
        alert('Unable to load the video. Check the Network tab.');
    });

    // --- canvas sizing to match video pixels ---
    const syncCanvasSize = () => {
        if (!videoElement.videoWidth || !videoElement.videoHeight) return;
        overlayCanvas.width = videoElement.videoWidth;
        overlayCanvas.height = videoElement.videoHeight;
        // keep CSS size in sync with displayed video
        overlayCanvas.style.width = videoElement.clientWidth + 'px';
        overlayCanvas.style.height = videoElement.clientHeight + 'px';
    };

    videoElement.addEventListener('loadedmetadata', () => {
        syncCanvasSize();
        createAnomalyTimeline();   // uses global allAnomalies
    });
    window.addEventListener('resize', syncCanvasSize);

    // --- draw overlay when time changes ---
    videoElement.addEventListener('timeupdate', () => {
        updateProgressBar();
        if (!overlayCtx) return;

        const t = videoElement.currentTime || 0;
        // anomaly within ±1s window
        const currentAnomaly = allAnomalies.find(a => Math.abs((a.frame_timestamp || 0) - t) < 1);

        drawOverlay(currentAnomaly);

        if (currentAnomaly) {
            highlightAnomalyInList(currentAnomaly);
        }
    });

    videoElement.addEventListener('play', () => { isPlaying = true; updatePlayPauseButton(); });
    videoElement.addEventListener('pause', () => { isPlaying = false; updatePlayPauseButton(); });

    setupVideoControls();
}

/* ---------- overlay drawing ---------- */

function drawOverlay(currentAnomaly) {
    if (!overlayCtx || !overlayCanvas) return;

    overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
    if (!currentAnomaly) return;

    overlayCtx.strokeStyle = "rgba(255,0,0,0.9)";
    overlayCtx.lineWidth = Math.max(2, Math.round(Math.min(overlayCanvas.width, overlayCanvas.height) / 200));

    const bbs = currentAnomaly.bboxes || [];
    if (bbs.length) {
        bbs.forEach((b) => {
            let [x, y, w, h] = b;
            // support normalized 0–1 coords
            if (x <= 1 && y <= 1 && w <= 1 && h <= 1) {
                x *= overlayCanvas.width;
                y *= overlayCanvas.height;
                w *= overlayCanvas.width;
                h *= overlayCanvas.height;
            }
            overlayCtx.strokeRect(x, y, w, h);
        });
    } else {
        // fallback: centered box
        const w = overlayCanvas.width * 0.3;
        const h = overlayCanvas.height * 0.2;
        const x = (overlayCanvas.width - w) / 2;
        const y = (overlayCanvas.height - h) / 2;
        overlayCtx.strokeRect(x, y, w, h);
    }

    // optional label
    const label = (currentAnomaly.anomaly_type || 'Alert').toUpperCase();
    overlayCtx.fillStyle = 'rgba(220,53,69,0.8)';
    overlayCtx.font = '14px sans-serif';
    overlayCtx.fillText(label, 10, 20);
}

/* ---------- timeline ---------- */

function createAnomalyTimeline() {
    const timeline = document.getElementById("anomaly-timeline");
    if (!timeline || !videoElement || !allAnomalies.length) return;

    timeline.innerHTML = "";
    const duration = videoElement.duration || 1;

    const maxMarkers = 250;
    const bucketCount = Math.min(maxMarkers, Math.max(1, Math.floor(timeline.clientWidth / 4)));
    const buckets = new Array(bucketCount).fill(0);

    const bucketSize = duration / bucketCount;
    allAnomalies.forEach(a => {
        const t = a.frame_timestamp || 0;
        const idx = Math.min(bucketCount - 1, Math.floor(t / bucketSize));
        buckets[idx] += 1;
    });

    buckets.forEach((count, i) => {
        if (!count) return;
        const marker = document.createElement("div");
        marker.className = "anomaly-marker";
        const left = (i / bucketCount) * 100;
        const width = (1 / bucketCount) * 100;
        marker.style.left = `${left}%`;
        marker.style.width = `${Math.max(0.15, width)}%`;
        marker.style.opacity = Math.min(0.95, 0.2 + (count / 10));
        marker.title = `${count} anomaly/anomalies`;
        timeline.appendChild(marker);
    });

    // click timeline to seek
    timeline.addEventListener('click', (e) => {
        const rect = timeline.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        const percentage = clickX / rect.width;
        videoElement.currentTime = percentage * duration;
    });
}

/* ---------- controls & navigation ---------- */

function setupVideoControls() {
    const nextBtn = document.getElementById('next-anomaly');
    const prevBtn = document.getElementById('prev-anomaly');
    const playPauseBtn = document.getElementById('play-pause-btn');
    const skipToFirstBtn = document.getElementById('skip-to-first');

    if (nextBtn) {
        nextBtn.addEventListener('click', () => {
            jumpToNextAnomaly();
        });
    }

    if (prevBtn) {
        prevBtn.addEventListener('click', () => {
            jumpToPreviousAnomaly();
        });
    }

    if (playPauseBtn) {
        playPauseBtn.addEventListener('click', () => {
            togglePlayPause();
        });
    }

    if (skipToFirstBtn) {
        skipToFirstBtn.addEventListener('click', () => {
            if (allAnomalies.length > 0) {
                currentAnomalyIndex = 0;
                jumpToAnomaly(allAnomalies[0].frame_timestamp);
            }
        });
    }
}

function jumpToNextAnomaly() {
    if (!allAnomalies.length) {
        alert('No anomalies detected in this video');
        return;
    }

    const currentTime = videoElement.currentTime;
    const nextIndex = allAnomalies.findIndex(a => a.frame_timestamp > currentTime);

    if (nextIndex !== -1) {
        currentAnomalyIndex = nextIndex;
        jumpToAnomaly(allAnomalies[nextIndex].frame_timestamp);
    } else {
        alert('No more anomalies. This was the last one.');
        currentAnomalyIndex = 0;
        jumpToAnomaly(allAnomalies[0].frame_timestamp);
    }
}

function jumpToPreviousAnomaly() {
    if (!allAnomalies.length) {
        alert('No anomalies detected');
        return;
    }

    const currentTime = videoElement.currentTime;

    for (let i = allAnomalies.length - 1; i >= 0; i--) {
        if (allAnomalies[i].frame_timestamp < currentTime - 1) {
            currentAnomalyIndex = i;
            jumpToAnomaly(allAnomalies[i].frame_timestamp);
            return;
        }
    }

    alert('No previous anomaly found');
}

function jumpToAnomaly(timestamp) {
    if (!videoElement) return;
    videoElement.currentTime = timestamp;
    videoElement.pause();
    isPlaying = false;
    updatePlayPauseButton();
    console.log(`Jumped to anomaly at ${timestamp.toFixed(1)}s`);
}

function togglePlayPause() {
    if (!videoElement) return;

    if (isPlaying) {
        videoElement.pause();
    } else {
        videoElement.play();
    }
}

function updatePlayPauseButton() {
    const btn = document.getElementById('play-pause-btn');
    if (btn) {
        btn.textContent = isPlaying ? '⏸️ Pause' : '▶️ Play Analysis';
    }
}

/* ---------- progress + list highlight ---------- */

function updateProgressBar() {
    const progressBar = document.getElementById('progress-bar');
    if (progressBar && videoElement && videoElement.duration) {
        const percentage = (videoElement.currentTime / videoElement.duration) * 100;
        progressBar.style.width = `${percentage}%`;
    }
}

function highlightAnomalyInList(anomaly) {
    // Remove previous highlights
    document.querySelectorAll('.list-group-item').forEach(item => {
        item.classList.remove('active-anomaly');
    });

    // Highlight current anomaly (uses data-timestamp attribute)
    const items = document.querySelectorAll(`[data-timestamp="${anomaly.frame_timestamp}"]`);
    items.forEach(item => {
        item.classList.add('active-anomaly');
        item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
}

/* ---------- globals exposed / theme toggle ---------- */

window.jumpToAnomalyTime = function (timestamp) {
    jumpToAnomaly(timestamp);
};

document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.getElementById('theme-toggle');
    if (toggle) {
        toggle.addEventListener('click', () => {
            document.body.classList.toggle('dark-mode');
        });
    }
});