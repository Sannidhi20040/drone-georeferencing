import L from 'leaflet';
import FlightLogParser from './flightLogParser.js';
import VideoProcessor from './videoProcessor.js';
import ModelInference from './modelInference.js';
import GeoConverter from './geoConverter.js';
import { clusterDetections } from './clustering.js';
import { trackDetections } from './tracker.js';
import { effectiveAltitude } from './altitude.js';

export class CancelledError extends Error {
    constructor() {
        super('Processing cancelled');
        this.name = 'CancelledError';
    }
}

class ProcessingPipeline {
    constructor(map) {
        this.map = map;
        this.flightLogParser = new FlightLogParser();
        this.videoProcessor = new VideoProcessor();
        this.modelInference = new ModelInference();
        this.geoConverter = null;
        this.config = {};
        this.detections = [];
        this.markers = [];
        this.flightPathLine = null;
        this.cancelRequested = false;
        this.stats = { framesSkipped: 0, detectionsSkipped: 0 };
    }

    cancel() {
        this.cancelRequested = true;
    }

    async initialize(videoFile, flightLogFile, config = {}) {
        console.log('🚀 Initializing processing pipeline...');
        this.cancelRequested = false;

        // Load flight log
        await this.flightLogParser.parseCSV(flightLogFile);
        this.drawFlightPath();

        // Load video
        const videoInfo = await this.videoProcessor.loadVideo(videoFile);

        // Initialize GeoConverter with video dimensions
        this.geoConverter = new GeoConverter({
            fov: config.fov || 84,
            videoWidth: videoInfo.width,
            videoHeight: videoInfo.height
        });

        // Load model
        await this.modelInference.loadModel(config.modelPath);

        console.log('✅ Pipeline initialized');
        return videoInfo;
    }

    async processFrame(frameNumber, fps = 30) {
        // Extract frame
        const timeSeconds = frameNumber / fps;
        const imageData = await this.videoProcessor.extractFrame(timeSeconds);

        // Get telemetry. syncOffset aligns the two clocks: log time = video time + offset.
        const telemetry = this.flightLogParser.getTelemetryAtTime(
            timeSeconds + (this.config.syncOffset || 0)
        );
        if (!telemetry) {
            console.warn(`⚠️  No telemetry for frame ${frameNumber}`);
            this.stats.framesSkipped++;
            return [];
        }

        const altitude = effectiveAltitude(telemetry.altitude, {
            mode: this.config.altitudeMode,
            firstSampleAltitude: this.flightLogParser.telemetryData[0]?.altitude ?? 0,
            offset: this.config.altitudeOffset
        });
        if (!(altitude > 0)) {
            console.warn(`⚠️  Frame ${frameNumber}: height above ground is ${altitude.toFixed(1)} m; skipping`);
            this.stats.framesSkipped++;
            return [];
        }
        const pose = {
            ...telemetry,
            altitude,
            gimbalPitch: telemetry.gimbalPitch ?? this.config.gimbalPitch ?? -90
        };

        // Run detection
        const detections = await this.modelInference.detectObjects(
            imageData,
            this.config.confidenceThreshold || 0.5
        );

        // Convert to GPS; rays that never reach the ground (above the horizon) are dropped
        const geoDetections = [];
        for (const det of detections) {
            const gps = this.geoConverter.pixelToGPS(det.x, det.y, pose);
            if (!gps) {
                this.stats.detectionsSkipped++;
                continue;
            }
            geoDetections.push({
                ...det,
                ...gps,
                frame: frameNumber,
                timestamp: timeSeconds
            });
        }

        return geoDetections;
    }

    async processVideo(progressCallback, config = {}) {
        this.config = config;
        this.stats = { framesSkipped: 0, detectionsSkipped: 0 };
        const fps = config.fps || 30;
        const totalFrames = Math.floor(this.videoProcessor.video.duration * fps);
        const framesToProcess = Math.max(1, config.sampleRate || 30); // Process every Nth frame

        console.log(`🎬 Processing ${totalFrames} frames (sampling every ${framesToProcess} frames)...`);

        const allDetections = [];

        for (let frame = 0; frame < totalFrames; frame += framesToProcess) {
            if (this.cancelRequested) throw new CancelledError();

            const detections = await this.processFrame(frame, fps);
            allDetections.push(...detections);

            if (progressCallback) {
                progressCallback({
                    frame,
                    totalFrames,
                    progress: (frame / totalFrames) * 100,
                    detections: allDetections.length
                });
            }
        }

        if (this.cancelRequested) throw new CancelledError();

        const maxDistance = config.clusterDistance || 5;
        this.detections = config.objectMode === 'moving'
            ? trackDetections(allDetections, { gateMeters: maxDistance })
            : clusterDetections(allDetections, maxDistance);
        this.plotOnMap(config.minDetections || 2);

        if (this.stats.framesSkipped || this.stats.detectionsSkipped) {
            console.warn(
                `⚠️  Skipped ${this.stats.framesSkipped} frame(s) and ` +
                `${this.stats.detectionsSkipped} detection(s) above the horizon`
            );
        }
        console.log(`✅ Processing complete: ${this.detections.length} unique detections`);
        return this.detections;
    }

    clearResults() {
        this.markers.forEach(m => this.map.removeLayer(m));
        this.markers = [];
        this.detections = [];
    }
    
    // The detections that are shown on the map, counted in stats, and exported.
    visibleDetections(minCount = this.config.minDetections || 2) {
        return this.detections.filter(det => det.count >= minCount);
    }

    drawFlightPath() {
        if (this.flightPathLine) {
            this.map.removeLayer(this.flightPathLine);
            this.flightPathLine = null;
        }

        const points = this.flightLogParser.telemetryData.map(t => [t.lat, t.lon]);
        if (points.length < 2) return;

        this.flightPathLine = L.polyline(points, {
            color: '#38bdf8',
            weight: 2,
            opacity: 0.7,
            dashArray: '4, 6'
        }).addTo(this.map);

        this.map.fitBounds(this.flightPathLine.getBounds().pad(0.1));
    }

    getMarkerColor(confidence) {
        if (confidence >= 0.8) return '#22c55e'; // high confidence - green
        if (confidence >= 0.6) return '#eab308'; // medium confidence - yellow
        return '#f97316'; // low confidence - orange
    }

    plotOnMap(minCount = 2) {
        // Clear existing markers
        this.markers.forEach(m => this.map.removeLayer(m));
        this.markers = [];

        for (const det of this.visibleDetections(minCount)) {
            if (det.path && det.path.length > 1) {
                const trail = L.polyline(det.path.map(p => [p.latitude, p.longitude]), {
                    color: '#e2e8f0',
                    weight: 2,
                    opacity: 0.8
                }).addTo(this.map);
                this.markers.push(trail);
            }

            const color = this.getMarkerColor(det.confidence);
            const marker = L.circleMarker([det.latitude, det.longitude], {
                radius: 6 + Math.min(det.count, 8),
                color,
                fillColor: color,
                fillOpacity: 0.7,
                weight: 2
            }).addTo(this.map);
            marker.bindPopup(
                `<b>${det.class}</b>` +
                (det.trackId ? ` (track ${det.trackId})` : '') + `<br>` +
                `Confidence: ${det.confidence.toFixed(2)}<br>` +
                `Detections: ${det.count}<br>` +
                (det.speed !== undefined ? `Speed: ${(det.speed * 3.6).toFixed(1)} km/h<br>` : '') +
                `Distance: ${det.distanceFromDrone.toFixed(2)}m`
            );
            this.markers.push(marker);
        }

        if (this.markers.length > 0) {
            const group = L.featureGroup(this.markers);
            this.map.fitBounds(group.getBounds().pad(0.1));
        }
    }
}

export default ProcessingPipeline;
