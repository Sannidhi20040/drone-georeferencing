import L from 'leaflet';
import FlightLogParser from './flightLogParser.js';
import VideoProcessor from './videoProcessor.js';
import ModelInference from './modelInference.js';
import GeoConverter from './geoConverter.js';

class ProcessingPipeline {
    constructor(map) {
        this.map = map;
        this.flightLogParser = new FlightLogParser();
        this.videoProcessor = new VideoProcessor();
        this.modelInference = new ModelInference();
        this.geoConverter = null;
        this.detections = [];
        this.markers = [];
        this.flightPathLine = null;
    }

    async initialize(videoFile, flightLogFile, config = {}) {
        console.log('🚀 Initializing processing pipeline...');

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
        
        // Get telemetry
        const telemetry = this.flightLogParser.getTelemetryAtFrame(frameNumber, fps);
        if (!telemetry) {
            console.warn(`⚠️  No telemetry for frame ${frameNumber}`);
            return [];
        }
        
        // Run detection
        const detections = await this.modelInference.detectObjects(
            imageData,
            this.config.confidenceThreshold || 0.5
        );
        
        // Convert to GPS
        const geoDetections = detections.map(det => {
            const gps = this.geoConverter.pixelToGPS(det.x, det.y, telemetry);
            return {
                ...det,
                ...gps,
                frame: frameNumber,
                timestamp: timeSeconds
            };
        });
        
        return geoDetections;
    }
    
    async processVideo(progressCallback, config = {}) {
        this.config = config;
        const fps = 30;
        const totalFrames = Math.floor(this.videoProcessor.video.duration * fps);
        const framesToProcess = config.sampleRate || 30; // Process every Nth frame
        
        console.log(`🎬 Processing ${totalFrames} frames (sampling every ${framesToProcess} frames)...`);
        
        const allDetections = [];
        
        for (let frame = 0; frame < totalFrames; frame += framesToProcess) {
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
        
        this.detections = this.clusterDetections(allDetections, config.clusterDistance || 5);
        this.plotOnMap(config.minDetections || 2);
        
        console.log(`✅ Processing complete: ${this.detections.length} unique detections`);
        return this.detections;
    }
    
    clusterDetections(detections, maxDistance = 5) {
        // Simple clustering: merge detections within maxDistance meters
        const clusters = [];
        
        detections.forEach(det => {
            let merged = false;
            
            for (let cluster of clusters) {
                const distance = this.calculateDistance(
                    det.latitude, det.longitude,
                    cluster.latitude, cluster.longitude
                );
                
                if (distance < maxDistance && det.class === cluster.class) {
                    // Merge into cluster as a running weighted average, so the
                    // centroid converges to the true mean instead of drifting
                    // toward whichever detection happened to merge last.
                    const newCount = cluster.count + 1;
                    cluster.latitude = (cluster.latitude * cluster.count + det.latitude) / newCount;
                    cluster.longitude = (cluster.longitude * cluster.count + det.longitude) / newCount;
                    cluster.confidence = (cluster.confidence * cluster.count + det.confidence) / newCount;
                    cluster.count = newCount;
                    merged = true;
                    break;
                }
            }
            
            if (!merged) {
                clusters.push({
                    ...det,
                    count: 1
                });
            }
        });
        
        return clusters;
    }
    
    calculateDistance(lat1, lon1, lat2, lon2) {
        const R = 6371e3; // Earth radius in meters
        const φ1 = lat1 * Math.PI / 180;
        const φ2 = lat2 * Math.PI / 180;
        const Δφ = (lat2 - lat1) * Math.PI / 180;
        const Δλ = (lon2 - lon1) * Math.PI / 180;
        
        const a = Math.sin(Δφ / 2) * Math.sin(Δφ / 2) +
                  Math.cos(φ1) * Math.cos(φ2) *
                  Math.sin(Δλ / 2) * Math.sin(Δλ / 2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        
        return R * c;
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

        const filtered = this.detections.filter(det => det.count >= minCount);

        filtered.forEach(det => {
            const color = this.getMarkerColor(det.confidence);
            const marker = L.circleMarker([det.latitude, det.longitude], {
                radius: 6 + Math.min(det.count, 8),
                color,
                fillColor: color,
                fillOpacity: 0.7,
                weight: 2
            }).addTo(this.map);
            marker.bindPopup(
                `<b>${det.class}</b><br>` +
                `Confidence: ${det.confidence.toFixed(2)}<br>` +
                `Detections: ${det.count}<br>` +
                `Distance: ${det.distanceFromDrone.toFixed(2)}m`
            );
            this.markers.push(marker);
        });

        if (this.markers.length > 0) {
            const group = L.featureGroup(this.markers);
            this.map.fitBounds(group.getBounds().pad(0.1));
        }
    }
}

export default ProcessingPipeline;
