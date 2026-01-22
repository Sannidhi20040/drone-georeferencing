import Papa from 'papaparse';

class FlightLogParser {
    constructor() {
        this.telemetryData = [];
    }
    
    async parseCSV(file) {
        return new Promise((resolve, reject) => {
            Papa.parse(file, {
                header: true,
                dynamicTyping: true,
                skipEmptyLines: true,
                complete: (results) => {
                    console.log('📊 Parsed CSV rows:', results.data.length);
                    this.telemetryData = this.processData(results.data);
                    console.log('✅ Processed telemetry entries:', this.telemetryData.length);
                    resolve(this.telemetryData);
                },
                error: (error) => {
                    console.error('❌ CSV parsing error:', error);
                    reject(error);
                }
            });
        });
    }
    
    processData(rawData) {
        // Filter and map to required format
        return rawData
            .filter(row => row.latitude && row.longitude && row.altitude)
            .map(row => ({
                timestamp: row.time || row.timestamp || Date.now(),
                lat: parseFloat(row.latitude || row.lat || row['OSD.latitude']),
                lon: parseFloat(row.longitude || row.lon || row['OSD.longitude']),
                altitude: parseFloat(row.altitude || row.alt || row['OSD.altitude']),
                heading: parseFloat(row.heading || row.yaw || row['OSD.yaw'] || 0),
                isVideo: row.isVideo !== undefined ? row.isVideo : 1
            }))
            .filter(entry => !isNaN(entry.lat) && !isNaN(entry.lon));
    }
    
    getTelemetryAtTime(timestamp) {
        if (this.telemetryData.length === 0) return null;
        
        // Find closest telemetry entry
        let closest = this.telemetryData[0];
        let minDiff = Math.abs(closest.timestamp - timestamp);
        
        for (let entry of this.telemetryData) {
            const diff = Math.abs(entry.timestamp - timestamp);
            if (diff < minDiff) {
                minDiff = diff;
                closest = entry;
            }
        }
        
        return closest;
    }
    
    getTelemetryAtFrame(frameNumber, fps = 30) {
        const timestamp = frameNumber / fps;
        return this.getTelemetryAtTime(timestamp);
    }
}

export default FlightLogParser;
