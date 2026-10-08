// Scores georeferencing against hand-picked landmarks (see README.md).
//   node scripts/au-air/evaluate.mjs --calibrate L1,L2 [--heading-fit] [--raw-gps]
//   node scripts/au-air/evaluate.mjs --cv [--heading-fit]
//   node scripts/au-air/evaluate.mjs --fov 70 --heading-offset 0        (no calibration)
import fs from 'fs';
import path from 'path';
import { parseArgs } from './args.mjs';
import {
    evaluateLandmarks, calibrateFov, calibrateHeadingOffset, median, summarize
} from './lib.mjs';

const args = parseArgs(process.argv.slice(2), {
    clip: '20190829091111', data: 'data_check'
});
const derived = path.join(args.data, 'derived');
const framesFile = args.frames ?? path.join(derived, `${args.clip}.json`);
const landmarksFile = args.landmarks ?? path.join(derived, 'landmarks.json');

const frameList = JSON.parse(fs.readFileSync(framesFile)).frames;
const frames = {};
for (const f of frameList) {
    frames[f.image] = args['raw-gps']
        ? { ...f, lat: f.rawLat, lon: f.rawLon, altitude: f.rawAltitude }
        : f;
}

const landmarks = JSON.parse(fs.readFileSync(landmarksFile)).landmarks
    .filter(l => Number.isFinite(l.lat) && Number.isFinite(l.lon) && l.observations?.length);
if (landmarks.length < 2) {
    console.error('Need at least 2 landmarks with a satellite lat/lon and at least one observation.');
    process.exit(1);
}

const f2 = (v) => (Number.isFinite(v) ? v.toFixed(2) : 'n/a');
const line = (label, s, unit) =>
    `  ${label.padEnd(22)} n=${String(s.n).padEnd(3)} median ${f2(s.median)}${unit}  mean ${f2(s.mean)}${unit}  RMSE ${f2(s.rmse)}${unit}  max ${f2(s.max)}${unit}`;

function fit(calibrationIds) {
    const params = { fov: args.fov ?? 84, headingOffset: args['heading-offset'] ?? 0, notes: [] };
    if (args.fov === undefined) {
        if (calibrationIds.length) {
            const c = calibrateFov({ landmarks, frames, calibrationIds });
            if (Number.isFinite(c.objective)) params.fov = c.fov;
            else params.notes.push('calibration landmarks never share a frame; FOV left at 84 deg');
        } else {
            params.notes.push('no calibration set: FOV left at the 84 deg default');
        }
    }
    if (args['heading-fit'] && calibrationIds.length && args['heading-offset'] === undefined) {
        params.headingOffset = calibrateHeadingOffset({
            landmarks, frames, fov: params.fov, calibrationIds
        }).headingOffset;
    }
    return params;
}

function score(params, testIds) {
    return evaluateLandmarks({
        landmarks, frames, fov: params.fov, headingOffset: params.headingOffset,
        include: testIds ? new Set(testIds) : null
    });
}

const allIds = landmarks.map(l => l.id);
const result = { clip: args.clip, gps: args['raw-gps'] ? 'raw' : 'smoothed', landmarks: landmarks.length };

if (args.cv) {
    // Leave-pair-out: calibrate on each co-observed pair, test on every other landmark.
    const folds = [];
    const seen = new Set();
    const probe = evaluateLandmarks({ landmarks, frames, fov: 84 });
    for (const p of probe.pairs) {
        const key = [p.a, p.b].sort().join('|');
        if (seen.has(key)) continue;
        seen.add(key);
        const calibrationIds = [p.a, p.b];
        const testIds = allIds.filter(id => !calibrationIds.includes(id));
        if (testIds.length < 2) continue;
        const params = fit(calibrationIds);
        const r = score(params, testIds);
        folds.push({
            calibration: calibrationIds, fov: params.fov, headingOffset: params.headingOffset,
            absoluteMedian: r.absolute.median, relativePctMedian: r.relativePct.median, tested: testIds.length
        });
    }
    if (folds.length === 0) {
        console.error('Not enough co-observed landmark pairs for cross-validation (need pairs seen in one frame, plus 2+ other landmarks).');
        process.exit(1);
    }
    const abs = folds.map(f => f.absoluteMedian).filter(Number.isFinite);
    const rel = folds.map(f => f.relativePctMedian).filter(Number.isFinite);
    console.log(`Leave-pair-out cross-validation: ${folds.length} folds, ${landmarks.length} landmarks, ${result.gps} GPS`);
    console.log(`  fitted FOV across folds:        median ${f2(median(folds.map(f => f.fov)))} deg (min ${f2(Math.min(...folds.map(f => f.fov)))}, max ${f2(Math.max(...folds.map(f => f.fov)))})`);
    console.log(`  held-out absolute error (m):    median of fold medians ${f2(median(abs))}  (best ${f2(Math.min(...abs))}, worst ${f2(Math.max(...abs))})`);
    console.log(`  held-out relative error (%):    median of fold medians ${f2(median(rel))}  (best ${f2(Math.min(...rel))}, worst ${f2(Math.max(...rel))})`);
    result.cv = { folds, absoluteMedianOfMedians: median(abs), relativePctMedianOfMedians: median(rel) };
} else {
    const calibrationIds = args.calibrate ? String(args.calibrate).split(',') : [];
    const unknown = calibrationIds.filter(id => !allIds.includes(id));
    if (unknown.length) {
        console.error(`Unknown calibration landmark id(s): ${unknown.join(', ')}. Available: ${allIds.join(', ')}`);
        process.exit(1);
    }
    const params = fit(calibrationIds);
    const testIds = calibrationIds.length ? allIds.filter(id => !calibrationIds.includes(id)) : null;

    console.log(`Clip ${args.clip} | ${landmarks.length} landmarks | ${result.gps} GPS`);
    console.log(`Parameters: FOV ${f2(params.fov)} deg, heading offset ${f2(params.headingOffset)} deg` +
        (calibrationIds.length ? ` (fitted on ${calibrationIds.join(', ')})` : ' (not fitted)'));
    params.notes.forEach(n => console.log(`  note: ${n}`));

    if (calibrationIds.length) {
        const inSample = score(params, calibrationIds);
        console.log('\nIN-SAMPLE (calibration landmarks; optimistic, do not report as accuracy):');
        console.log(line('absolute position', inSample.absolute, ' m'));
        console.log(line('distance between pairs', inSample.relativePct, ' %'));
    }

    const test = score(params, testIds);
    console.log(testIds
        ? `\nHELD-OUT (${testIds.length} landmarks not used for calibration):`
        : '\nALL LANDMARKS (no held-out split; in-sample):');
    console.log(line('absolute position', test.absolute, ' m'));
    console.log(line('distance between pairs', test.relativeMeters, ' m'));
    console.log(line('distance between pairs', test.relativePct, ' %'));
    if (test.pairs.length === 0) console.log('  (no two held-out landmarks share a frame, so no pair distances)');

    console.log('\nPer landmark (mean over observations):');
    for (const lm of landmarks.filter(l => !testIds || testIds.includes(l.id))) {
        const errs = test.observations.filter(o => o.landmark === lm.id).map(o => o.errorMeters);
        console.log(`  ${lm.id.padEnd(6)} ${String(errs.length).padStart(2)} obs  error ${f2(summarize(errs).mean)} m`);
    }
    Object.assign(result, { params, calibrationIds, test: { absolute: test.absolute, relativeMeters: test.relativeMeters, relativePct: test.relativePct } });
}

console.log('\nReminder: absolute error includes the drone\'s own GPS error and the satellite image\'s offset;' +
    '\nthe pair-distance error (same frame) cancels both. Report both, and say it is one scene.');
const resultsFile = path.join(path.dirname(landmarksFile), 'results.json');
fs.writeFileSync(resultsFile, JSON.stringify(result, null, 2));
console.log(`(saved ${resultsFile})`);
