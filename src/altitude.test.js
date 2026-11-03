import { describe, it, expect } from 'vitest';
import { effectiveAltitude } from './altitude.js';

describe('effectiveAltitude', () => {
    it('uses the log altitude as-is when it is already above ground', () => {
        expect(effectiveAltitude(100)).toBe(100);
        expect(effectiveAltitude(100, { mode: 'agl', firstSampleAltitude: 900 })).toBe(100);
    });

    it('subtracts the takeoff sample when the log is above sea level', () => {
        expect(effectiveAltitude(950, { mode: 'asl', firstSampleAltitude: 900 })).toBe(50);
    });

    it('applies the manual offset in either mode', () => {
        expect(effectiveAltitude(100, { offset: 12 })).toBe(88);
        expect(effectiveAltitude(950, { mode: 'asl', firstSampleAltitude: 900, offset: 10 })).toBe(40);
    });
});
