import Papa from 'papaparse';

function lerp(a, b, t) {
    return a + (b - a) * t;
}

// Interpolates heading across the shorter angular path (e.g. 350deg -> 10deg
// should pass through 0deg, not wrap the long way around through 180deg).
function lerpAngle(a, b, t) {
    const diff = ((b - a + 540) % 360) - 180;
    return (a + diff * t + 360) % 360;
}

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
        // Filter and map to required format.
        // Uses ?? / != null checks throughout (not || / truthiness) because
        // 0 is a valid timestamp, latitude, longitude, and altitude value
        // (e.g. the first sample of a log, or a location on the equator) and
        // must not be treated as "missing".
        return rawData
            .filter(row =>
                (row.latitude ?? row.lat ?? row['OSD.latitude']) != null &&
                (row.longitude ?? row.lon ?? row['OSD.longitude']) != null &&
                (row.altitude ?? row.alt ?? row['OSD.altitude']) != null
            )
            .map(row => ({
                timestamp: row.time ?? row.timestamp ?? Date.now(),
                lat: parseFloat(row.latitude ?? row.lat ?? row['OSD.latitude']),
                lon: parseFloat(row.longitude ?? row.lon ?? row['OSD.longitude']),
                altitude: parseFloat(row.altitude ?? row.alt ?? row['OSD.altitude']),
                heading: parseFloat(row.heading ?? row.yaw ?? row['OSD.yaw'] ?? 0),
                isVideo: row.isVideo !== undefined ? row.isVideo : 1
            }))
            // Drop rows with non-numeric values (e.g. a blank CSV cell passes
            // the presence check above but parses to NaN, which would
            // otherwise poison every downstream pixel-to-GPS calculation),
            // then sort by timestamp since getTelemetryAtTime()'s bracketing
            // interpolation assumes ascending order, which CSV row order
            // does not guarantee.
            .filter(entry =>
                !isNaN(entry.lat) && !isNaN(entry.lon) &&
                !isNaN(entry.altitude) && !isNaN(entry.heading)
            )
            .sort((a, b) => a.timestamp - b.timestamp);
    }
    
    getTelemetryAtTime(timestamp) {
        if (this.telemetryData.length === 0) return null;
        if (this.telemetryData.length === 1) return this.telemetryData[0];

        // Find the two samples bracketing this timestamp and interpolate,
        // instead of snapping to the nearest one (logs are often sparse,
        // e.g. 0.5s intervals, so nearest-sample lookup causes position/
        // heading jitter between samples).
        let before = null;
        let after = null;

        for (const entry of this.telemetryData) {
            if (entry.timestamp <= timestamp) {
                before = entry;
            }
            if (entry.timestamp >= timestamp) {
                after = entry;
                break;
            }
        }

        if (!before) return after;
        if (!after || before === after) return before;

        const span = after.timestamp - before.timestamp;
        const t = span === 0 ? 0 : (timestamp - before.timestamp) / span;

        return {
            timestamp,
            lat: lerp(before.lat, after.lat, t),
            lon: lerp(before.lon, after.lon, t),
            altitude: lerp(before.altitude, after.altitude, t),
            heading: lerpAngle(before.heading, after.heading, t),
            isVideo: before.isVideo
        };
    }
    
    getTelemetryAtFrame(frameNumber, fps = 30) {
        const timestamp = frameNumber / fps;
        return this.getTelemetryAtTime(timestamp);
    }
}

export default FlightLogParser;
