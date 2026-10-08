import { describe, it, expect } from 'vitest';
import { computeLetterbox, boxToOriginal } from './letterbox.js';

describe('computeLetterbox', () => {
    it('pads top and bottom for a 16:9 frame', () => {
        const lb = computeLetterbox(1920, 1080, 640);

        expect(lb.scale).toBeCloseTo(1 / 3, 6);
        expect(lb.newWidth).toBe(640);
        expect(lb.newHeight).toBe(360);
        expect(lb.padX).toBe(0);
        expect(lb.padY).toBe(140);
    });

    it('pads left and right for a portrait frame', () => {
        const lb = computeLetterbox(1080, 1920, 640);

        expect(lb.newWidth).toBe(360);
        expect(lb.newHeight).toBe(640);
        expect(lb.padX).toBe(140);
        expect(lb.padY).toBe(0);
    });

    it('needs no padding for a square frame', () => {
        const lb = computeLetterbox(1000, 1000, 640);

        expect(lb.padX).toBe(0);
        expect(lb.padY).toBe(0);
        expect(lb.scale).toBeCloseTo(0.64, 6);
    });
});

describe('boxToOriginal', () => {
    it('maps the center of the letterboxed image back to the center of the frame', () => {
        const lb = computeLetterbox(1920, 1080, 640);

        const box = boxToOriginal(320, 320, 30, 15, lb);

        expect(box.x).toBeCloseTo(960, 6);
        expect(box.y).toBeCloseTo(540, 6);
        expect(box.width).toBeCloseTo(90, 6);
        expect(box.height).toBeCloseTo(45, 6);
    });

    it('maps the top-left of the content area to pixel (0, 0)', () => {
        const lb = computeLetterbox(1920, 1080, 640);

        const box = boxToOriginal(0, 140, 0, 0, lb);

        expect(box.x).toBeCloseTo(0, 6);
        expect(box.y).toBeCloseTo(0, 6);
    });

    it('maps the bottom-right of the content area to the last pixel', () => {
        const lb = computeLetterbox(1920, 1080, 640);

        const box = boxToOriginal(640, 500, 0, 0, lb);

        expect(box.x).toBeCloseTo(1920, 6);
        expect(box.y).toBeCloseTo(1080, 6);
    });
});
