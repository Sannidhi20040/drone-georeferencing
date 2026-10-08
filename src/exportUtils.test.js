import { describe, it, expect } from 'vitest';
import { ExportUtils } from './exportUtils.js';

const detection = (overrides = {}) => ({
    class: 'small-vehicle',
    confidence: 0.9,
    latitude: 12.9716,
    longitude: 77.5946,
    distanceFromDrone: 10,
    bearing: 45,
    count: 3,
    ...overrides
});

describe('ExportUtils', () => {
    it('writes GeoJSON coordinates as [longitude, latitude]', () => {
        const geojson = ExportUtils.toGeoJSON([detection()]);

        expect(geojson.features[0].geometry.coordinates).toEqual([77.5946, 12.9716]);
    });

    it('flags simulated detections in GeoJSON so fake data is never mistaken for real', () => {
        const geojson = ExportUtils.toGeoJSON([detection(), detection({ simulated: true })]);

        expect(geojson.features.map(f => f.properties.simulated)).toEqual([false, true]);
    });

    it('flags simulated detections in CSV', () => {
        const [header, real, fake] = ExportUtils.toCSV([
            detection(),
            detection({ simulated: true })
        ]).split('\n');

        expect(header.split(',').at(-1)).toBe('simulated');
        expect(header.split(',').slice(-3)).toEqual(['track_id', 'speed_mps', 'simulated']);
        expect(real.split(',').at(-1)).toBe('false');
        expect(fake.split(',').at(-1)).toBe('true');
    });

    it('exports track id and speed for tracked objects and leaves them empty otherwise', () => {
        const geojson = ExportUtils.toGeoJSON([detection(), detection({ trackId: 7, speed: 4.5 })]);
        expect(geojson.features[0].properties.trackId).toBeNull();
        expect(geojson.features[1].properties).toMatchObject({ trackId: 7, speedMps: 4.5 });

        const [, plain, tracked] = ExportUtils.toCSV([detection(), detection({ trackId: 7, speed: 4.5 })]).split('\n');
        expect(plain.split(',').slice(-3)).toEqual(['', '', 'false']);
        expect(tracked.split(',').slice(-3)).toEqual(['7', '4.50', 'false']);
    });
});
