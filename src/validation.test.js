import { describe, it, expect } from 'vitest';
import { evaluate, parseGroundTruthRows } from './validation.js';
import { fromLocalMeters } from './geo.js';

const REF = [12.9716, 77.5946];
const at = (east, north, extra = {}) => ({ ...fromLocalMeters(east, north, ...REF), ...extra });

describe('parseGroundTruthRows', () => {
    it('accepts several column spellings and drops unusable rows', () => {
        const rows = [
            { latitude: 12.97, longitude: 77.59, class: 'human' },
            { lat: 12.98, lon: 77.6 },
            { lat: 12.99, lng: 77.61 },
            { latitude: '', longitude: 77.6 },
            { latitude: 'abc', longitude: 77.6 }
        ];

        const parsed = parseGroundTruthRows(rows);

        expect(parsed).toHaveLength(3);
        expect(parsed[0].class).toBe('human');
        expect(parsed[1].class).toBeNull();
    });
});

describe('evaluate', () => {
    it('reports the exact position error in metres for matched pairs', () => {
        const result = evaluate([at(3, 4)], [at(0, 0)], { matchRadius: 10 });

        expect(result.truePositives).toBe(1);
        expect(result.meanError).toBeCloseTo(5, 1);
        expect(result.rmse).toBeCloseTo(5, 1);
        expect(result.maxError).toBeCloseTo(5, 1);
    });

    it('counts misses and extras', () => {
        const result = evaluate([at(0, 0), at(500, 0)], [at(1, 0), at(0, 300)], { matchRadius: 10 });

        expect(result.truePositives).toBe(1);
        expect(result.falsePositives).toBe(1);
        expect(result.falseNegatives).toBe(1);
        expect(result.precision).toBeCloseTo(0.5, 6);
        expect(result.recall).toBeCloseTo(0.5, 6);
    });

    it('matches one-to-one, nearest first', () => {
        // Two detections near one ground-truth point: only the closer one may match.
        const result = evaluate([at(4, 0), at(1, 0)], [at(0, 0)], { matchRadius: 10 });

        expect(result.truePositives).toBe(1);
        expect(result.falsePositives).toBe(1);
        expect(result.meanError).toBeCloseTo(1, 1);
    });

    it('ignores points outside the match radius and requires classes to agree when both are known', () => {
        expect(evaluate([at(50, 0)], [at(0, 0)], { matchRadius: 10 }).truePositives).toBe(0);

        const wrongClass = evaluate(
            [at(0, 0, { class: 'small-vehicle' })],
            [at(0, 0, { class: 'human' })]
        );
        expect(wrongClass.truePositives).toBe(0);

        const unlabelled = evaluate([at(0, 0, { class: 'small-vehicle' })], [at(0, 0)]);
        expect(unlabelled.truePositives).toBe(1);
    });

    it('reports null error statistics when nothing matched, and computes the median', () => {
        const none = evaluate([at(100, 0)], [at(0, 0)], { matchRadius: 10 });
        expect(none.meanError).toBeNull();
        expect(none.medianError).toBeNull();

        const three = evaluate(
            [at(1, 0), at(12, 0), at(23, 0)],
            [at(0, 0), at(10, 0), at(20, 0)],
            { matchRadius: 10 }
        );
        expect(three.medianError).toBeCloseTo(2, 1);
        expect(three.meanError).toBeCloseTo(2, 1);
    });
});
