import { describe, it, expect } from 'vitest';
import {
    median, medianFilter, summarize, makeConverter,
    evaluateLandmarks, calibrateFov, calibrateHeadingOffset
} from './lib.mjs';

const TRUE_FOV = 70;
const TRUE_HEADING_OFFSET = 20;

const frames = {
    f1: { image: 'f1', lat: 56.2063, lon: 10.188, altitude: 20, yaw: 64 },
    f2: { image: 'f2', lat: 56.20634, lon: 10.18806, altitude: 25, yaw: 75 }
};

// "Satellite" truth: where a pixel really is, generated with the true FOV and
// heading offset, so a correct calibration must recover both.
function landmarkAt(id, image, x, y) {
    const f = frames[image];
    const p = makeConverter(TRUE_FOV).pixelToGPS(x, y, {
        lat: f.lat, lon: f.lon, altitude: f.altitude,
        heading: (f.yaw + TRUE_HEADING_OFFSET + 360) % 360
    });
    return { id, lat: p.latitude, lon: p.longitude, observations: [{ image, x, y }] };
}

const landmarks = [
    landmarkAt('A', 'f1', 300, 200),
    landmarkAt('B', 'f1', 1500, 300),
    landmarkAt('C', 'f1', 900, 900),
    landmarkAt('D', 'f1', 200, 800),
    landmarkAt('E', 'f2', 1600, 700),
    landmarkAt('F', 'f2', 500, 400)
];

describe('statistics helpers', () => {
    it('computes medians', () => {
        expect(median([3, 1, 2])).toBe(2);
        expect(median([4, 1, 3, 2])).toBe(2.5);
        expect(median([])).toBeNaN();
    });

    it('removes a single-sample GPS spike without smearing the track', () => {
        const track = [0, 1, 2, 3, 50, 5, 6, 7, 8];

        const filtered = medianFilter(track, 5);

        // The spike becomes the median of its neighbours' range, not 50.
        expect(filtered[4]).toBe(5);
        expect(Math.max(...filtered)).toBeLessThan(10);
        expect(filtered[0]).toBeLessThan(2);
    });

    it('summarizes errors', () => {
        const s = summarize([1, 2, 3, 10]);

        expect(s.n).toBe(4);
        expect(s.median).toBe(2.5);
        expect(s.max).toBe(10);
        expect(s.mean).toBe(4);
        expect(summarize([]).n).toBe(0);
    });
});

describe('evaluateLandmarks', () => {
    it('reports zero error when FOV and heading offset are right', () => {
        const r = evaluateLandmarks({ landmarks, frames, fov: TRUE_FOV, headingOffset: TRUE_HEADING_OFFSET });

        expect(r.absolute.n).toBe(6);
        expect(r.absolute.max).toBeLessThan(0.01);
        expect(r.relativeMeters.max).toBeLessThan(0.01);
    });

    it('measures a heading error as absolute error but barely changes relative distances', () => {
        const r = evaluateLandmarks({ landmarks, frames, fov: TRUE_FOV, headingOffset: 0 });

        expect(r.absolute.median).toBeGreaterThan(1);
        expect(r.relativeMeters.max).toBeLessThan(0.01);
    });

    it('pairs landmarks only within the same frame', () => {
        const r = evaluateLandmarks({ landmarks, frames, fov: TRUE_FOV, headingOffset: TRUE_HEADING_OFFSET });

        // f1 has A,B,C,D -> 6 pairs; f2 has E,F -> 1 pair.
        expect(r.pairs).toHaveLength(7);
        expect(r.pairs.every(p => p.image === 'f1' || (p.a === 'E' && p.b === 'F'))).toBe(true);
    });

    it('scores only the included landmarks', () => {
        const r = evaluateLandmarks({
            landmarks, frames, fov: TRUE_FOV, headingOffset: TRUE_HEADING_OFFSET, include: new Set(['E', 'F'])
        });

        expect(r.absolute.n).toBe(2);
        expect(r.pairs).toHaveLength(1);
    });

    it('shows a larger relative error for a wrong FOV', () => {
        const right = evaluateLandmarks({ landmarks, frames, fov: TRUE_FOV, headingOffset: TRUE_HEADING_OFFSET });
        const wrong = evaluateLandmarks({ landmarks, frames, fov: 90, headingOffset: TRUE_HEADING_OFFSET });

        expect(wrong.relativePct.median).toBeGreaterThan(right.relativePct.median + 10);
    });
});

describe('calibration', () => {
    it('recovers the FOV from a single landmark pair', () => {
        const { fov } = calibrateFov({ landmarks, frames, calibrationIds: ['A', 'B'] });

        expect(fov).toBeCloseTo(TRUE_FOV, 0);
    });

    it('recovers the heading offset from absolute positions', () => {
        const { headingOffset } = calibrateHeadingOffset({
            landmarks, frames, fov: TRUE_FOV, calibrationIds: ['A', 'B', 'C']
        });

        expect(headingOffset).toBeCloseTo(TRUE_HEADING_OFFSET, 0);
    });

    it('generalizes: calibrating on A,B leaves the held-out landmarks near zero error', () => {
        const { fov } = calibrateFov({ landmarks, frames, calibrationIds: ['A', 'B'] });
        const { headingOffset } = calibrateHeadingOffset({ landmarks, frames, fov, calibrationIds: ['A', 'B', 'C'] });

        const held = evaluateLandmarks({
            landmarks, frames, fov, headingOffset, include: new Set(['D', 'E', 'F'])
        });

        expect(held.absolute.max).toBeLessThan(0.5);
    });

    it('returns no usable fit when the calibration landmarks never share a frame', () => {
        const { objective } = calibrateFov({ landmarks, frames, calibrationIds: ['A', 'E'] });

        expect(objective).toBe(Infinity);
    });
});
