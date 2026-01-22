export class ExportUtils {
    static toGeoJSON(detections) {
        const features = detections.map((det, idx) => ({
            type: 'Feature',
            id: idx,
            geometry: {
                type: 'Point',
                coordinates: [det.longitude, det.latitude]
            },
            properties: {
                class: det.class,
                confidence: det.confidence,
                count: det.count || 1,
                distanceFromDrone: det.distanceFromDrone,
                bearing: det.bearing,
                frame: det.frame,
                timestamp: det.timestamp
            }
        }));
        
        return {
            type: 'FeatureCollection',
            features: features
        };
    }
    
    static downloadGeoJSON(detections, filename = 'detections.geojson') {
        const geojson = this.toGeoJSON(detections);
        const blob = new Blob([JSON.stringify(geojson, null, 2)], {
            type: 'application/json'
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
    }
    
    static toCSV(detections) {
        const headers = ['id', 'class', 'latitude', 'longitude', 'confidence', 'count', 'distance_m', 'bearing_deg'];
        const rows = detections.map((det, idx) => [
            idx,
            det.class,
            det.latitude.toFixed(6),
            det.longitude.toFixed(6),
            det.confidence.toFixed(3),
            det.count || 1,
            det.distanceFromDrone.toFixed(2),
            det.bearing.toFixed(2)
        ]);
        
        return [headers, ...rows]
            .map(row => row.join(','))
            .join('\n');
    }
    
    static downloadCSV(detections, filename = 'detections.csv') {
        const csv = this.toCSV(detections);
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
    }
}
