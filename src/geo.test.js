import { describe, it, expect } from 'vitest';
import { distanceMeters, toLocalMeters, fromLocalMeters } from './geo.js';

describe('geo helpers', () => {
    it('measures one degree of latitude as about 111.2 km', () => {
        expect(distanceMeters(0, 0, 1, 0)).toBeCloseTo(111195, -1);
    });

    it('is zero for identical points and symmetric', () => {
        expect(distanceMeters(12.97, 77.59, 12.97, 77.59)).toBe(0);
        expect(distanceMeters(12.97, 77.59, 13.0, 77.6)).toBeCloseTo(distanceMeters(13.0, 77.6, 12.97, 77.59), 6);
    });

    it('round-trips local metric coordinates', () => {
        const { east, north } = toLocalMeters(12.9720, 77.5950, 12.9716, 77.5946);
        const back = fromLocalMeters(east, north, 12.9716, 77.5946);

        expect(back.latitude).toBeCloseTo(12.9720, 9);
        expect(back.longitude).toBeCloseTo(77.5950, 9);
    });

    it('agrees with the haversine distance at drone scales', () => {
        const { east, north } = toLocalMeters(12.9720, 77.5950, 12.9716, 77.5946);

        expect(Math.hypot(east, north)).toBeCloseTo(distanceMeters(12.9716, 77.5946, 12.9720, 77.5950), 1);
    });
});
