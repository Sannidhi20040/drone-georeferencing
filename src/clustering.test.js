import { describe, it, expect } from 'vitest';
import { clusterDetections } from './clustering.js';
import { fromLocalMeters } from './geo.js';

const at = (east, north, extra = {}) => ({
    class: 'small-vehicle',
    confidence: 0.8,
    ...fromLocalMeters(east, north, 12.9716, 77.5946),
    ...extra
});

describe('clusterDetections', () => {
    it('merges nearby same-class detections and counts the sightings', () => {
        const clusters = clusterDetections([at(0, 0), at(1, 1), at(2, 0)], 5);

        expect(clusters).toHaveLength(1);
        expect(clusters[0].count).toBe(3);
    });

    it('keeps detections apart when they are farther than the distance', () => {
        expect(clusterDetections([at(0, 0), at(50, 0)], 5)).toHaveLength(2);
    });

    it('never merges different classes, even at the same spot', () => {
        const clusters = clusterDetections([at(0, 0), at(0, 0, { class: 'human' })], 5);

        expect(clusters).toHaveLength(2);
    });

    it('converges to the true mean regardless of merge order', () => {
        const pts = [at(0, 0), at(2, 0), at(4, 0)];
        const forward = clusterDetections(pts, 10)[0];
        const backward = clusterDetections([...pts].reverse(), 10)[0];

        expect(forward.longitude).toBeCloseTo(backward.longitude, 10);
        expect(forward.longitude).toBeCloseTo(at(2, 0).longitude, 8);
    });

    it('averages confidence by count and flags any simulated member', () => {
        const [cluster] = clusterDetections([
            at(0, 0, { confidence: 0.9 }),
            at(0, 0, { confidence: 0.6, simulated: true }),
            at(0, 0, { confidence: 0.6 })
        ], 5);

        expect(cluster.confidence).toBeCloseTo(0.7, 6);
        expect(cluster.simulated).toBe(true);
    });
});
