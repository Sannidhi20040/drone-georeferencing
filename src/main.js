import L from 'leaflet';
import ProcessingPipeline from './processingPipeline.js';
import { ExportUtils } from './exportUtils.js';

console.log('🚀 Drone Georeferencing System Starting...');

let map;
let pipeline;
let currentDetections = [];

document.addEventListener('DOMContentLoaded', () => {
    console.log('✅ DOM loaded');
    
    map = L.map('map').setView([12.9716, 77.5946], 13);
    
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19
    }).addTo(map);
    
    console.log('✅ Map initialized');
    
    pipeline = new ProcessingPipeline(map);
    console.log('✅ Processing pipeline initialized');
    
    setupEventListeners();
});

function setupEventListeners() {
    const processBtn = document.getElementById('processBtn');
    const videoInput = document.getElementById('videoInput');
    const flightLogInput = document.getElementById('flightLogInput');
    const videoFileName = document.getElementById('videoFileName');
    const logFileName = document.getElementById('logFileName');
    const exportGeoJSONBtn = document.getElementById('exportGeoJSON');
    const exportCSVBtn = document.getElementById('exportCSV');
    
    let videoFile = null;
    let flightLogFile = null;
    
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
    
    processBtn.addEventListener('click', async () => {
        if (!videoFile || !flightLogFile) {
            alert('Please upload both video and flight log files!');
            return;
        }
        
        processBtn.disabled = true;
        processBtn.textContent = '⏳ Processing...';
        showProgressBar(true);
        
        try {
            await processRealVideo(videoFile, flightLogFile);
        } catch (error) {
            console.error('❌ Processing error:', error);
            alert('Error processing video: ' + error.message);
        } finally {
            processBtn.disabled = false;
            processBtn.textContent = '🚀 Process Video';
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

async function processRealVideo(videoFile, flightLogFile) {
    console.log('🎬 Starting video processing...');
    
    const config = {
        fov: 84,
        confidenceThreshold: parseFloat(document.getElementById('confThreshold').value),
        clusterDistance: parseFloat(document.getElementById('clusterDistance').value),
        minDetections: parseInt(document.getElementById('minDetections').value),
        sampleRate: 60
    };
    
    console.log('⚙️  Config:', config);
    
    await pipeline.initialize(videoFile, flightLogFile, config);
    
    const detections = await pipeline.processVideo((progress) => {
        const percent = progress.progress.toFixed(1);
        const text = `Processing: ${percent}% - ${progress.detections} detections found`;
        updateProgress(progress.progress, text);
        console.log(`📊 ${text}`);
    }, config);
    
    // Store detections for export
    currentDetections = detections;
    
    // Update UI
    document.getElementById('statsSection').classList.remove('hidden');
    document.getElementById('exportControls').style.display = 'flex';
    
    const stats = calculateStats(detections);
    document.getElementById('statSmallVehicles').textContent = stats.smallVehicles;
    document.getElementById('statLargeVehicles').textContent = stats.largeVehicles;
    document.getElementById('statHumans').textContent = stats.humans;
    document.getElementById('statTotal').textContent = detections.length;
    
    console.log('✅ Processing complete!', stats);
}

function calculateStats(detections) {
    return {
        smallVehicles: detections.filter(d => d.class === 'small-vehicle').length,
        largeVehicles: detections.filter(d => d.class === 'large-vehicle').length,
        humans: detections.filter(d => d.class === 'human').length
    };
}

export { map, pipeline, currentDetections };
