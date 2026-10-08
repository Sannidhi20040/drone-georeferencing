import { describe, it, expect } from 'vitest';
import { trackDetections } from './tracker.js';
import { fromLocalMeters } from './geo.js';

const REF = [12.9716, 77.5946];
const obs = (t, east, north, extra = {}) => ({
    class: 'small-vehicle',
    confidence: 0.8,
    timestamp: t,
    frame: t * 30,
    distanceFromDrone: 0,
    bearing: 0,
    ...fromLocalMeters(east, north, ...REF),
    ...extra
});

describe('trackDetections', () => {
    it('follows one vehicle moving at 10 m/s as a single track with the right speed', () => {
        const tracks = trackDetections([obs(0, 0, 0), obs(1, 10, 0), obs(2, 20, 0), obs(3, 30, 0)]);

        expect(tracks).toHaveLength(1);
        expect(tracks[0].count).toBe(4);
        expect(tracks[0].speed).toBeCloseTo(10, 0);
        expect(tracks[0].path).toHaveLength(4);
    });

    it('keeps two vehicles far apart as separate tracks', () => {
        const tracks = trackDetections([
            obs(0, 0, 0), obs(0, 0, 200),
            obs(1, 10, 0), obs(1, 10, 200)
        ]);

        expect(tracks).toHaveLength(2);
        expect(tracks.every(t => t.count === 2)).toBe(true);
    });

    it('never assigns two detections from the same frame to one track', () => {
        const tracks = trackDetections([obs(0, 0, 0), obs(0, 1, 0)]);

        expect(tracks).toHaveLength(2);
    });

    it('does not link different classes', () => {
        const tracks = trackDetections([obs(0, 0, 0), obs(1, 1, 0, { class: 'human' })]);

        expect(tracks).toHaveLength(2);
    });

    it('starts a new track after the object has been unseen for too long', () => {
        const tracks = trackDetections([obs(0, 0, 0), obs(20, 1, 0)], { maxGapSeconds: 6 });

        expect(tracks).toHaveLength(2);
    });

    it('does not follow an impossible jump for a pedestrian', () => {
        // 100 m in one second is far beyond the pedestrian speed cap.
        const tracks = trackDetections([obs(0, 0, 0, { class: 'human' }), obs(1, 100, 0, { class: 'human' })]);

        expect(tracks).toHaveLength(2);
    });

    it('assigns each of two close vehicles to its own track using nearest-first matching', () => {
        const tracks = trackDetections([
            obs(0, 0, 0), obs(0, 8, 0),
            obs(1, 1, 0), obs(1, 9, 0)
        ]);

        expect(tracks).toHaveLength(2);
        const moved = tracks.map(t => t.path.length);
        expect(moved).toEqual([2, 2]);
    });

    it('returns nothing for no input and carries simulated flags through', () => {
        expect(trackDetections([])).toEqual([]);

        const [track] = trackDetections([obs(0, 0, 0), obs(1, 1, 0, { simulated: true })]);
        expect(track.simulated).toBe(true);
    });
});
