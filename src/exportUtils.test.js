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
        expect(real.split(',').at(-1)).toBe('false');
        expect(fake.split(',').at(-1)).toBe('true');
    });
});
