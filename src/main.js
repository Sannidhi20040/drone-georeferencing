import L from 'leaflet';
import ProcessingPipeline, { CancelledError } from './processingPipeline.js';
import { ExportUtils } from './exportUtils.js';
import { parseGroundTruthFile, evaluate } from './validation.js';

console.log('🚀 Drone Georeferencing System Starting...');

let map;
let pipeline;
let currentDetections = [];
let validationLayers = [];

document.addEventListener('DOMContentLoaded', () => {
    console.log('✅ DOM loaded');

    map = L.map('map').setView([12.9716, 77.5946], 13);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19
    }).addTo(map);

    addLegend(map);
    console.log('✅ Map initialized');

    pipeline = new ProcessingPipeline(map);
    console.log('✅ Processing pipeline initialized');

    setupEventListeners();
});

function addLegend(map) {
    const legend = L.control({ position: 'bottomright' });
    legend.onAdd = () => {
        const div = L.DomUtil.create('div', 'map-legend');
        div.innerHTML =
            '<b>Detections</b><br>' +
            '<i style="background:#22c55e"></i>Confidence ≥ 0.8<br>' +
            '<i style="background:#eab308"></i>Confidence 0.6–0.8<br>' +
            '<i style="background:#f97316"></i>Confidence &lt; 0.6<br>' +
            'Larger marker = more sightings<br>' +
            '<span class="line" style="border-top:2px dashed #38bdf8"></span>Drone flight path<br>' +
            '<span class="line" style="border-top:2px solid #e2e8f0"></span>Tracked path (moving mode)<br>' +
            '<i style="background:transparent;border:2px solid #c084fc"></i>Ground-truth point';
        return div;
    };
    legend.addTo(map);
}

function setupEventListeners() {
    const processBtn = document.getElementById('processBtn');
    const cancelBtn = document.getElementById('cancelBtn');
    const videoInput = document.getElementById('videoInput');
    const flightLogInput = document.getElementById('flightLogInput');
    const groundTruthInput = document.getElementById('groundTruthInput');
    const videoFileName = document.getElementById('videoFileName');
    const logFileName = document.getElementById('logFileName');
    const groundTruthFileName = document.getElementById('groundTruthFileName');
    const exportGeoJSONBtn = document.getElementById('exportGeoJSON');
    const exportCSVBtn = document.getElementById('exportCSV');

    let videoFile = null;
    let flightLogFile = null;
    let groundTruthFile = null;

    videoInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            videoFile = e.target.files[0];
            videoFileName.textContent = `✅ ${videoFile.name}`;
            checkInputs();
        }
    });

    flightLogInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            flightLogFile = e.target.files[0];
            logFileName.textContent = `✅ ${flightLogFile.name}`;
            checkInputs();
        }
    });

    groundTruthInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            groundTruthFile = e.target.files[0];
            groundTruthFileName.textContent = `✅ ${groundTruthFile.name}`;
        }
    });

    const checkInputs = () => {
        if (videoFile && flightLogFile) {
            processBtn.disabled = false;
        }
    };

    document.getElementById('confThreshold').addEventListener('input', (e) => {
        document.getElementById('confValue').textContent = e.target.value;
    });

    document.getElementById('clusterDistance').addEventListener('input', (e) => {
        document.getElementById('clusterValue').textContent = e.target.value;
    });

    document.getElementById('minDetections').addEventListener('input', (e) => {
        document.getElementById('minDetValue').textContent = e.target.value;
    });

    cancelBtn.addEventListener('click', () => {
        cancelBtn.disabled = true;
        pipeline.cancel();
    });

    processBtn.addEventListener('click', async () => {
        if (!videoFile || !flightLogFile) {
            alert('Please upload both video and flight log files!');
            return;
        }

        processBtn.disabled = true;
        processBtn.textContent = '⏳ Processing...';
        cancelBtn.hidden = false;
        cancelBtn.disabled = false;
        showProgressBar(true);

        try {
            await processRealVideo(videoFile, flightLogFile, groundTruthFile);
        } catch (error) {
            if (error instanceof CancelledError) {
                console.log('⏹️  Processing cancelled');
            } else {
                console.error('❌ Processing error:', error);
                alert('Error processing video: ' + error.message);
            }
        } finally {
            processBtn.disabled = false;
            processBtn.textContent = '🚀 Process Video';
            cancelBtn.hidden = true;
            showProgressBar(false);
        }
    });

    // Export button handlers
    exportGeoJSONBtn.addEventListener('click', () => {
        if (currentDetections.length > 0) {
            ExportUtils.downloadGeoJSON(currentDetections, 'drone_detections.geojson');
            console.log('📥 GeoJSON exported');
        } else {
            alert('No detections to export!');
        }
    });

    exportCSVBtn.addEventListener('click', () => {
        if (currentDetections.length > 0) {
            ExportUtils.downloadCSV(currentDetections, 'drone_detections.csv');
            console.log('📊 CSV exported');
        } else {
            alert('No detections to export!');
        }
    });
}

function readNumber(id, fallback, min, max) {
    const value = parseFloat(document.getElementById(id).value);
    if (!Number.isFinite(value)) return fallback;
    return Math.min(max, Math.max(min, value));
}

function setSimulationBanner(active, reason = '') {
    document.getElementById('simulationBanner').classList.toggle('hidden', !active);
    document.getElementById('simulationReason').textContent = reason;
}

function showProgressBar(show) {
    const container = document.getElementById('progressContainer');
    if (show) {
        container.classList.add('active');
    } else {
        container.classList.remove('active');
        updateProgress(0, '');
    }
}

function updateProgress(percent, text) {
    document.getElementById('progressFill').style.width = `${percent}%`;
    document.getElementById('progressText').textContent = text;
}

function clearPreviousResults() {
    currentDetections = [];
    pipeline.clearResults();
    validationLayers.forEach(layer => map.removeLayer(layer));
    validationLayers = [];
    document.getElementById('statsSection').classList.add('hidden');
    document.getElementById('validationStats').classList.add('hidden');
    document.getElementById('exportControls').style.display = 'none';
}

async function processRealVideo(videoFile, flightLogFile, groundTruthFile) {
    console.log('🎬 Starting video processing...');

    const fps = readNumber('fpsInput', 30, 1, 240);
    const sampleSeconds = readNumber('sampleSeconds', 2, 0.1, 60);

    const config = {
        fov: readNumber('fovInput', 84, 10, 180),
        fps,
        syncOffset: readNumber('syncOffset', 0, -3600, 3600),
        gimbalPitch: readNumber('gimbalPitch', -90, -90, 0),
        altitudeMode: document.getElementById('altitudeMode').value,
        altitudeOffset: readNumber('altitudeOffset', 0, -1000, 1000),
        objectMode: document.getElementById('objectMode').value,
        confidenceThreshold: parseFloat(document.getElementById('confThreshold').value),
        clusterDistance: parseFloat(document.getElementById('clusterDistance').value),
        minDetections: parseInt(document.getElementById('minDetections').value),
        sampleRate: Math.max(1, Math.round(sampleSeconds * fps))
    };

    console.log('⚙️  Config:', config);

    clearPreviousResults();
    setSimulationBanner(false);

    // Parse the optional ground truth up front so a bad file fails before the slow part.
    const groundTruth = groundTruthFile ? await parseGroundTruthFile(groundTruthFile) : null;
    if (groundTruthFile && groundTruth.length === 0) {
        throw new Error('No valid latitude/longitude rows were found in the ground-truth file.');
    }

    await pipeline.initialize(videoFile, flightLogFile, config);

    if (!pipeline.modelInference.modelLoaded) {
        setSimulationBanner(true, pipeline.modelInference.simulationReason);
    }

    await pipeline.processVideo((progress) => {
        const percent = progress.progress.toFixed(1);
        const text = `Processing: ${percent}% - ${progress.detections} detections found`;
        updateProgress(progress.progress, text);
        console.log(`📊 ${text}`);
    }, config);

    if (pipeline.modelInference.usedSimulation) {
        setSimulationBanner(true, pipeline.modelInference.simulationReason);
    }

    // Only what is drawn on the map is counted and exported.
    const detections = pipeline.visibleDetections(config.minDetections);
    currentDetections = detections;

    // Update UI
    document.getElementById('statsSection').classList.remove('hidden');
    document.getElementById('exportControls').style.display = 'flex';

    const stats = calculateStats(detections);
    document.getElementById('statSmallVehicles').textContent = stats.smallVehicles;
    document.getElementById('statLargeVehicles').textContent = stats.largeVehicles;
    document.getElementById('statHumans').textContent = stats.humans;
    document.getElementById('statTotal').textContent = detections.length;
    showSkippedNote(pipeline.stats);

    if (groundTruth) {
        showValidation(groundTruth, detections);
    }

    console.log('✅ Processing complete!', stats);
}

function showSkippedNote(skipped) {
    const note = document.getElementById('statsNote');
    const parts = [];
    if (skipped.framesSkipped) {
        parts.push(`${skipped.framesSkipped} frame(s) skipped (no telemetry or height ≤ 0)`);
    }
    if (skipped.detectionsSkipped) {
        parts.push(`${skipped.detectionsSkipped} detection(s) discarded (above the horizon)`);
    }
    note.textContent = parts.length ? `ℹ️ ${parts.join('; ')}` : '';
    note.classList.toggle('hidden', parts.length === 0);
}

function showValidation(groundTruth, detections) {
    const result = evaluate(detections, groundTruth, { matchRadius: readNumber('matchRadius', 10, 1, 100) });

    groundTruth.forEach(gt => {
        validationLayers.push(
            L.circleMarker([gt.latitude, gt.longitude], {
                radius: 10, color: '#c084fc', weight: 3, fillOpacity: 0
            }).addTo(map)
        );
    });
    result.matches.forEach(({ gi, di }) => {
        validationLayers.push(
            L.polyline(
                [[groundTruth[gi].latitude, groundTruth[gi].longitude],
                 [detections[di].latitude, detections[di].longitude]],
                { color: '#c084fc', weight: 2, dashArray: '2, 4' }
            ).addTo(map)
        );
    });

    const meters = (v) => (v === null ? '—' : `${v.toFixed(2)} m`);
    const percent = (v) => (v === null ? '—' : `${(v * 100).toFixed(0)}%`);
    document.getElementById('valCounts').textContent =
        `${result.truePositives} / ${result.falseNegatives} / ${result.falsePositives}`;
    document.getElementById('valPR').textContent = `${percent(result.precision)} / ${percent(result.recall)}`;
    document.getElementById('valMean').textContent = meters(result.meanError);
    document.getElementById('valMedian').textContent = meters(result.medianError);
    document.getElementById('valRmse').textContent = meters(result.rmse);
    document.getElementById('valMax').textContent = meters(result.maxError);
    document.getElementById('validationStats').classList.remove('hidden');

    console.log('🎯 Validation:', result);
}

function calculateStats(detections) {
    return {
        smallVehicles: detections.filter(d => d.class === 'small-vehicle').length,
        largeVehicles: detections.filter(d => d.class === 'large-vehicle').length,
        humans: detections.filter(d => d.class === 'human').length
    };
}

export { map, pipeline, currentDetections };
