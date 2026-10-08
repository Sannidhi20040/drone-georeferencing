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

    describe('straight-down camera (regression against the original formula)', () => {
        it('reproduces the exact values the pre-pitch implementation produced', () => {
            const converter = new GeoConverter({ fov: 84, videoWidth: 1920, videoHeight: 1080 });
            const telemetry = { lat: 12.9716, lon: 77.5946, altitude: 100, heading: 45 };

            const result = converter.pixelToGPS(1400, 300, telemetry);

            expect(result.latitude).toBeCloseTo(12.971496031767346, 9);
            expect(result.longitude).toBeCloseTo(77.59496274873993, 9);
            expect(result.distanceFromDrone).toBeCloseTo(40.97142354899016, 6);
            expect(result.bearing).toBeCloseTo(106.38954033403479, 6);
        });

        it('treats a missing gimbalPitch as straight down', () => {
            const converter = new GeoConverter({ fov: 84, videoWidth: 1920, videoHeight: 1080 });
            const base = { lat: 12.9716, lon: 77.5946, altitude: 100, heading: 45 };

            const implicit = converter.pixelToGPS(1400, 300, base);
            const explicit = converter.pixelToGPS(1400, 300, { ...base, gimbalPitch: -90 });

            expect(implicit).toEqual(explicit);
        });
    });

    describe('tilted camera', () => {
        const converter = new GeoConverter({ fov: 84, videoWidth: 1920, videoHeight: 1080 });
        const telemetry = { lat: 12.9716, lon: 77.5946, altitude: 100, heading: 0 };

        it('sees its centre pixel one altitude ahead when pitched 45 degrees down', () => {
            const result = converter.pixelToGPS(960, 540, { ...telemetry, gimbalPitch: -45 });

            expect(result.distanceFromDrone).toBeCloseTo(100, 4);
            expect(result.bearing).toBeCloseTo(0, 6);
        });

        it('reaches farther for the top of the frame, by the exact pinhole geometry', () => {
            const result = converter.pixelToGPS(960, 0, { ...telemetry, gimbalPitch: -45 });

            const halfVertical = (converter.fovVertical / 2) * Math.PI / 180;
            const expected = 100 / Math.tan(Math.PI / 4 - halfVertical);
            expect(result.distanceFromDrone).toBeCloseTo(expected, 3);
        });

        it('sees the bottom of the frame closer than the centre', () => {
            const centre = converter.pixelToGPS(960, 540, { ...telemetry, gimbalPitch: -45 });
            const bottom = converter.pixelToGPS(960, 1079, { ...telemetry, gimbalPitch: -45 });

            expect(bottom.distanceFromDrone).toBeLessThan(centre.distanceFromDrone);
        });

        it('rotates the forward direction with the heading', () => {
            const east = converter.pixelToGPS(960, 540, { ...telemetry, heading: 90, gimbalPitch: -45 });

            expect(east.bearing).toBeCloseTo(90, 6);
            expect(east.longitude).toBeGreaterThan(telemetry.lon);
        });

        it('returns null for rays that do not reach the ground', () => {
            // Level camera: the centre ray runs parallel to the ground.
            expect(converter.pixelToGPS(960, 540, { ...telemetry, gimbalPitch: 0 })).toBeNull();
            // Pixels above the horizon in a tilted camera.
            expect(converter.pixelToGPS(960, 0, { ...telemetry, gimbalPitch: -10 })).toBeNull();
        });

        it('discards rays within 5 degrees of the horizon but keeps steeper ones', () => {
            expect(converter.pixelToGPS(960, 540, { ...telemetry, gimbalPitch: -4 })).toBeNull();

            const ok = converter.pixelToGPS(960, 540, { ...telemetry, gimbalPitch: -10 });
            expect(ok.distanceFromDrone).toBeCloseTo(100 / Math.tan(10 * Math.PI / 180), 3);
        });
    });

    it('returns null when the height above ground is not positive', () => {
        const converter = new GeoConverter({ fov: 84, videoWidth: 1920, videoHeight: 1080 });
        const telemetry = { lat: 12.9716, lon: 77.5946, heading: 0 };

        expect(converter.pixelToGPS(100, 100, { ...telemetry, altitude: 0 })).toBeNull();
        expect(converter.pixelToGPS(100, 100, { ...telemetry, altitude: -5 })).toBeNull();
        expect(converter.pixelToGPS(100, 100, { ...telemetry, altitude: NaN })).toBeNull();
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
