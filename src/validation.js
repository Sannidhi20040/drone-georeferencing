import Papa from 'papaparse';
import { distanceMeters } from './geo.js';

// Accepts rows with latitude/longitude (or lat/lon/lng) and an optional class.
export function parseGroundTruthRows(rows) {
    return rows
        .map(row => ({
            latitude: toNumber(row.latitude ?? row.lat),
            longitude: toNumber(row.longitude ?? row.lon ?? row.lng),
            class: row.class ?? row.label ?? null
        }))
        .filter(p => p.latitude !== null && p.longitude !== null);
}

export function parseGroundTruthFile(file) {
    return new Promise((resolve, reject) => {
        Papa.parse(file, {
            header: true,
            dynamicTyping: true,
            skipEmptyLines: true,
            complete: results => resolve(parseGroundTruthRows(results.data)),
            error: reject
        });
    });
}

function toNumber(value) {
    if (value === null || value === undefined || value === '') return null;
    const n = typeof value === 'number' ? value : parseFloat(value);
    return Number.isFinite(n) ? n : null;
}

// One-to-one nearest-first matching of detections to surveyed ground-truth
// points within `matchRadius` meters. When both sides carry a class, classes
// must agree. The reported error is the horizontal distance in meters between
// each matched pair, so it combines detector localisation error and
// georeferencing error.
export function evaluate(detections, groundTruth, { matchRadius = 10 } = {}) {
    const pairs = [];
    groundTruth.forEach((gt, gi) => {
        detections.forEach((det, di) => {
            if (gt.class && det.class && gt.class !== det.class) return;
            const d = distanceMeters(gt.latitude, gt.longitude, det.latitude, det.longitude);
            if (d <= matchRadius) pairs.push({ gi, di, error: d });
        });
    });

    pairs.sort((a, b) => a.error - b.error);
    const usedGt = new Set();
    const usedDet = new Set();
    const matches = [];

    for (const pair of pairs) {
        if (usedGt.has(pair.gi) || usedDet.has(pair.di)) continue;
        usedGt.add(pair.gi);
        usedDet.add(pair.di);
        matches.push(pair);
    }

    const truePositives = matches.length;
    const falsePositives = detections.length - truePositives;
    const falseNegatives = groundTruth.length - truePositives;
    const errors = matches.map(m => m.error).sort((a, b) => a - b);

    return {
        truePositives,
        falsePositives,
        falseNegatives,
        precision: detections.length ? truePositives / detections.length : null,
        recall: groundTruth.length ? truePositives / groundTruth.length : null,
        meanError: errors.length ? errors.reduce((s, e) => s + e, 0) / errors.length : null,
        medianError: errors.length ? median(errors) : null,
        rmse: errors.length ? Math.sqrt(errors.reduce((s, e) => s + e * e, 0) / errors.length) : null,
        maxError: errors.length ? errors[errors.length - 1] : null,
        matches
    };
}

function median(sorted) {
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}
