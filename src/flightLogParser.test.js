import { describe, it, expect, beforeEach } from 'vitest';
import FlightLogParser from './flightLogParser.js';

describe('FlightLogParser', () => {
    let parser;

    beforeEach(() => {
        parser = new FlightLogParser();
    });

    describe('processData', () => {
        it('parses standard column names and drops rows missing GPS data', () => {
            const rows = [
                { time: 0, latitude: 12.9716, longitude: 77.5946, altitude: 100, heading: 45 },
                { time: 1, latitude: null, longitude: 77.6, altitude: 100 }, // missing lat
                { time: 2, latitude: 12.98, longitude: 77.59, altitude: 110, heading: 50 }
            ];

            const result = parser.processData(rows);

            expect(result).toHaveLength(2);
            expect(result[0]).toMatchObject({ lat: 12.9716, lon: 77.5946, altitude: 100, heading: 45 });
        });

        it('falls back to DJI-style OSD.* column names', () => {
            const rows = [
                { time: 0, 'OSD.latitude': 12.9716, 'OSD.longitude': 77.5946, 'OSD.altitude': 100, 'OSD.yaw': 30 }
            ];

            const result = parser.processData(rows);

            expect(result).toEqual([
                { timestamp: 0, lat: 12.9716, lon: 77.5946, altitude: 100, heading: 30, isVideo: 1 }
            ]);
        });

        it('defaults heading to 0 when absent', () => {
            const rows = [{ time: 0, latitude: 12.9716, longitude: 77.5946, altitude: 100 }];

            const result = parser.processData(rows);

            expect(result[0].heading).toBe(0);
        });

        it('drops rows with a blank altitude/heading cell instead of admitting NaN', () => {
            const rows = [
                { time: 0, latitude: 12.9716, longitude: 77.5946, altitude: 100, heading: 45 },
                { time: 1, latitude: 12.98, longitude: 77.59, altitude: '', heading: 50 }, // blank altitude
                { time: 2, latitude: 12.99, longitude: 77.6, altitude: 110, heading: '' }  // blank heading
            ];

            const result = parser.processData(rows);

            expect(result).toHaveLength(1);
            expect(result.some(e => isNaN(e.altitude) || isNaN(e.heading))).toBe(false);
        });

        it('sorts entries by timestamp regardless of CSV row order', () => {
            const rows = [
                { time: 2, latitude: 12.99, longitude: 77.6, altitude: 110, heading: 0 },
                { time: 0, latitude: 12.9716, longitude: 77.5946, altitude: 100, heading: 0 },
                { time: 1, latitude: 12.98, longitude: 77.59, altitude: 105, heading: 0 }
            ];

            const result = parser.processData(rows);

            expect(result.map(e => e.timestamp)).toEqual([0, 1, 2]);
        });
    });

    describe('getTelemetryAtTime', () => {
        beforeEach(() => {
            parser.telemetryData = parser.processData([
                { time: 0, latitude: 10, longitude: 20, altitude: 100, heading: 350 },
                { time: 1, latitude: 12, longitude: 24, altitude: 120, heading: 10 }
            ]);
        });

        it('returns the exact sample when the timestamp matches', () => {
            const result = parser.getTelemetryAtTime(0);
            expect(result).toMatchObject({ lat: 10, lon: 20, altitude: 100 });
        });

        it('linearly interpolates position and altitude between bracketing samples', () => {
            const result = parser.getTelemetryAtTime(0.5);

            expect(result.lat).toBeCloseTo(11, 6);
            expect(result.lon).toBeCloseTo(22, 6);
            expect(result.altitude).toBeCloseTo(110, 6);
        });

        it('interpolates heading across the shorter angular path (350deg -> 10deg through 0, not 180)', () => {
            const result = parser.getTelemetryAtTime(0.5);
            expect(result.heading).toBeCloseTo(0, 6);
        });

        it('clamps to the last sample when the timestamp is past the end of the log', () => {
            const result = parser.getTelemetryAtTime(5);
            expect(result).toMatchObject({ lat: 12, lon: 24 });
        });

        it('clamps to the first sample when the timestamp is before the log starts', () => {
            const result = parser.getTelemetryAtTime(-1);
            expect(result).toMatchObject({ lat: 10, lon: 20 });
        });
    });
});
