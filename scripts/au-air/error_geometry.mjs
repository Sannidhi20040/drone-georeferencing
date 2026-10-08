// Splits landmark error into radial (toward/away from the point under the
// drone) and tangential (sideways) parts and fits a per-frame similarity
// transform, to tell scale/lens-distortion effects from rotation (yaw) effects.
//   node scripts/au-air/error_geometry.mjs [--fit-on L1,L2,L3,L4] [--landmarks path] [--csv out.csv]
//
// Reading the output:
//   radial error growing with range  -> scale / FOV / altitude / lens distortion
//   tangential error growing with range -> rotation, i.e. heading (yaw) error
// A rotation that differs from frame to frame means noisy yaw, not a fixed offset.
// Few points: suggestive only.
import fs from 'fs';
import path from 'path';
import { parseArgs } from './args.mjs';
import { toLocalMeters } from '../../src/geo.js';
import { evaluateLandmarks, calibrateFov, calibrateHeadingOffset } from './lib.mjs';

const args = parseArgs(process.argv.slice(2), { clip: '20190829091111', data: 'data_check' });
const derived = path.join(args.data, 'derived');
const frames = {};
for (const f of JSON.parse(fs.readFileSync(path.join(derived, `${args.clip}.json`))).frames) frames[f.image] = f;
const landmarks = JSON.parse(fs.readFileSync(args.landmarks ?? path.join(derived, 'landmarks.json'))).landmarks
    .filter(l => Number.isFinite(l.lat) && Number.isFinite(l.lon) && l.observations?.length);
const ids = landmarks.map(l => l.id);
const fitIds = args['fit-on'] ? String(args['fit-on']).split(',') : ids;

const fov = args.fov ?? calibrateFov({ landmarks, frames, calibrationIds: fitIds }).fov;
const headingOffset = args['heading-offset'] ??
    calibrateHeadingOffset({ landmarks, frames, fov, calibrationIds: fitIds }).headingOffset;
const { observations } = evaluateLandmarks({ landmarks, frames, fov, headingOffset });

const ref = landmarks[0];
const enu = (lat, lon) => toLocalMeters(lat, lon, ref.lat, ref.lon);
const short = s => s.match(/_(\d+)\.jpg/)[1];
const rows = [];

console.log(`FOV ${fov.toFixed(2)} deg, heading offset ${headingOffset.toFixed(1)} deg, geometry fitted on ${fitIds.join(',')}\n`);

const perFrame = [];
for (const image of [...new Set(observations.map(o => o.image))]) {
    const obs = observations.filter(o => o.image === image).map(o => {
        const lm = landmarks.find(l => l.id === o.landmark);
        const px = lm.observations.find(x => x.image === image);
        return { id: o.landmark, pred: enu(o.latitude, o.longitude), truth: enu(lm.lat, lm.lon),
                 rho: Math.hypot(px.x - 960, px.y - 540), fit: fitIds.includes(o.landmark) };
    });
    const f = frames[image];
    const anchor = obs.filter(o => o.fit);
    const off = {
        e: anchor.reduce((s, o) => s + o.pred.east - o.truth.east, 0) / anchor.length,
        n: anchor.reduce((s, o) => s + o.pred.north - o.truth.north, 0) / anchor.length
    };
    // Point under the drone, expressed in the satellite frame after removing the frame's offset.
    const nadir = enu(f.lat, f.lon);
    const c = { east: nadir.east - off.e, north: nadir.north - off.n };

    for (const o of obs) {
        const e = { e: o.pred.east - o.truth.east - off.e, n: o.pred.north - o.truth.north - off.n };
        const dx = o.truth.east - c.east, dy = o.truth.north - c.north;
        const range = Math.hypot(dx, dy);
        const rx = dx / range, ry = dy / range;
        rows.push({ frame: short(image), id: o.id, rho: o.rho, range, fit: o.fit,
                    radial: e.e * rx + e.n * ry,            // + = predicted farther from the centre than truth
                    tangential: -e.e * ry + e.n * rx });    // + = predicted rotated counter-clockwise
    }

    // Per-frame similarity (scale + rotation + translation), predicted -> truth, via complex numbers.
    const mp = { e: obs.reduce((s, o) => s + o.pred.east, 0) / obs.length, n: obs.reduce((s, o) => s + o.pred.north, 0) / obs.length };
    const mt = { e: obs.reduce((s, o) => s + o.truth.east, 0) / obs.length, n: obs.reduce((s, o) => s + o.truth.north, 0) / obs.length };
    let re = 0, im = 0, den = 0;
    for (const o of obs) {
        const pe = o.pred.east - mp.e, pn = o.pred.north - mp.n, te = o.truth.east - mt.e, tn = o.truth.north - mt.n;
        re += pe * te + pn * tn; im += pe * tn - pn * te; den += pe * pe + pn * pn;
    }
    const a = { re: re / den, im: im / den };
    const scalePredOverTruth = 1 / Math.hypot(a.re, a.im);
    const rotCw = (Math.atan2(a.im, a.re) * 180) / Math.PI;      // predicted layout is rotated this many degrees clockwise vs truth
    const resid = obs.map(o => {
        const pe = o.pred.east - mp.e, pn = o.pred.north - mp.n;
        const fe = a.re * pe - a.im * pn + mt.e, fn = a.im * pe + a.re * pn + mt.n;
        return Math.hypot(fe - o.truth.east, fn - o.truth.north);
    });
    perFrame.push({ frame: short(image), n: obs.length, tilt: Math.hypot(f.rollDeg, f.pitchDeg), yaw: f.yaw,
                    scale: scalePredOverTruth, rotCw, rmsAfter: Math.sqrt(resid.reduce((s, r) => s + r * r, 0) / resid.length),
                    maxSpan: Math.max(...obs.map(o => Math.hypot(o.truth.east - mt.e, o.truth.north - mt.n))) });
}

console.log('Radial / tangential error after removing each frame\'s overall shift (m)');
console.log('frame    lm   pixel-r  range(m)  radial  tangential');
for (const r of rows.sort((a, b) => a.range - b.range)) {
    console.log(`${r.frame}  ${r.id.padEnd(3)} ${r.rho.toFixed(0).padStart(7)} ${r.range.toFixed(1).padStart(9)} ${r.radial.toFixed(2).padStart(8)} ${r.tangential.toFixed(2).padStart(10)}${r.fit ? '' : '   <- not used in the fit'}`);
}

const slope = (key, set) => set.reduce((s, r) => s + r.range * r[key], 0) / set.reduce((s, r) => s + r.range * r.range, 0);
const report = (label, set) => {
    if (set.length < 3) return;
    const sr = slope('radial', set), st = slope('tangential', set);
    console.log(`${label.padEnd(26)} n=${String(set.length).padEnd(2)} radial slope ${(sr * 100).toFixed(1).padStart(5)}% of range (+ = predicted too far out) | tangential slope ${(st * 180 / Math.PI).toFixed(1).padStart(5)} deg (+ = rotated CCW)`);
};
console.log('\nSlope of error against range (through the origin):');
report('all landmarks', rows);
report('near (fit set)', rows.filter(r => r.fit));
report('far (not in fit set)', rows.filter(r => !r.fit));

console.log('\nPer-frame similarity fit (predicted layout vs satellite):');
console.log('frame    n  tilt  yaw    scale(pred/true)  rotation (deg, + = predicted clockwise)  residual RMS after fit');
for (const p of perFrame) {
    console.log(`${p.frame}  ${p.n}  ${p.tilt.toFixed(1).padStart(4)}  ${p.yaw.toFixed(0).padStart(4)}   ${p.scale.toFixed(3).padStart(8)}          ${p.rotCw.toFixed(1).padStart(8)}                              ${p.rmsAfter.toFixed(2)} m`);
}

if (args.csv) {
    fs.writeFileSync(args.csv, 'frame,landmark,pixel_radius,range_m,radial_m,tangential_m,in_fit\n' +
        rows.map(r => [r.frame, r.id, r.rho.toFixed(0), r.range.toFixed(2), r.radial.toFixed(3), r.tangential.toFixed(3), r.fit].join(',')).join('\n') + '\n');
    console.log(`\n(wrote ${args.csv})`);
}
