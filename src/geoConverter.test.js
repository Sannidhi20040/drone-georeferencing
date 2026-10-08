import { describe, it, expect } from 'vitest';
import GeoConverter from './geoConverter.js';

describe('GeoConverter', () => {
    it('splits a diagonal FOV into horizontal/vertical components by aspect ratio', () => {
        const converter = new GeoConverter({ fov: 84, videoWidth: 1920, videoHeight: 1080 });

        expect(converter.fovHorizontal).toBeCloseTo(76.2475, 3);
        expect(converter.fovVertical).toBeCloseTo(47.6365, 3);
    });

    it('maps the center pixel to the drone position directly below it', () => {
        const converter = new GeoConverter({ fov: 84, videoWidth: 1920, videoHeight: 1080 });
        const telemetry = { lat: 12.9716, lon: 77.5946, altitude: 100, heading: 45 };

        const result = converter.pixelToGPS(1920 / 2, 1080 / 2, telemetry);

        expect(result.latitude).toBeCloseTo(telemetry.lat, 6);
        expect(result.longitude).toBeCloseTo(telemetry.lon, 6);
        expect(result.distanceFromDrone).toBeCloseTo(0, 6);
        expect(result.bearing).toBeCloseTo(telemetry.heading, 6);
    });

    it('places a pixel above image-center on the far side of the drone', () => {
        const converter = new GeoConverter({ fov: 84, videoWidth: 1920, videoHeight: 1080 });
        const telemetry = { lat: 12.9716, lon: 77.5946, altitude: 100, heading: 0 };

        const result = converter.pixelToGPS(1920 / 2, 0, telemetry);

        // Heading 0 (north) + a pixel above center should project further north.
        expect(result.latitude).toBeGreaterThan(telemetry.lat);
        expect(result.distanceFromDrone).toBeGreaterThan(0);
    });

    it('reports higher altitude as covering a larger ground footprint', () => {
        const converter = new GeoConverter({ fov: 84, videoWidth: 1920, videoHeight: 1080 });
        const telemetry = { lat: 12.9716, lon: 77.5946, altitude: 100, heading: 0 };
        const highAltTelemetry = { ...telemetry, altitude: 200 };

        const near = converter.pixelToGPS(0, 0, telemetry);
        const far = converter.pixelToGPS(0, 0, highAltTelemetry);

        expect(far.distanceFromDrone).toBeGreaterThan(near.distanceFromDrone);
    });

    describe('isValidGPS', () => {
        const converter = new GeoConverter();

        it('accepts coordinates within range', () => {
            expect(converter.isValidGPS(12.9716, 77.5946)).toBe(true);
            expect(converter.isValidGPS(-90, -180)).toBe(true);
            expect(converter.isValidGPS(90, 180)).toBe(true);
        });

        it('rejects out-of-range coordinates', () => {
            expect(converter.isValidGPS(91, 0)).toBe(false);
            expect(converter.isValidGPS(0, 181)).toBe(false);
            expect(converter.isValidGPS(-91, 0)).toBe(false);
        });
    });
});
