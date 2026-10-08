// Per-frame breakdown of landmark error, to see whether it grows with drone tilt.
//   node scripts/au-air/per_frame.mjs [--landmarks path] [--fov 84] [--heading-fit]
//
// For each frame the script reports the mean position offset (predicted minus
// satellite) and the scatter around it. A rigidly mounted camera on a drone
// tilted by theta at height h would shift positions by about h * tan(theta); a
// stabilised camera should not. The FOV and heading offset are fitted on ALL
// landmarks here (in-sample), which is fine for comparing frames with each
// other but is not an accuracy figure.
import fs from 'fs';
import path from 'path';
import { parseArgs } from './args.mjs';
import { toLocalMeters } from '../../src/geo.js';
import { evaluateLandmarks, calibrateFov, calibrateHeadingOffset, median } from './lib.mjs';

const args = parseArgs(process.argv.slice(2), { clip: '20190829091111', data: 'data_check' });
const derived = path.join(args.data, 'derived');
const frames = {};
for (const f of JSON.parse(fs.readFileSync(path.join(derived, `${args.clip}.json`))).frames) frames[f.image] = f;
const landmarks = JSON.parse(fs.readFileSync(args.landmarks ?? path.join(derived, 'landmarks.json'))).landmarks
    .filter(l => Number.isFinite(l.lat) && Number.isFinite(l.lon) && l.observations?.length);
if (landmarks.length < 2) { console.error('Need at least 2 landmarks with a satellite lat/lon.'); process.exit(1); }

const ids = landmarks.map(l => l.id);
const fov = args.fov ?? calibrateFov({ landmarks, frames, calibrationIds: ids }).fov;
const headingOffset = args['heading-fit']
    ? calibrateHeadingOffset({ landmarks, frames, fov, calibrationIds: ids }).headingOffset
    : (args['heading-offset'] ?? 0);

const result = evaluateLandmarks({ landmarks, frames, fov, headingOffset });
const ref = landmarks[0];
const byImage = new Map();
for (const o of result.observations) {
    const lm = landmarks.find(l => l.id === o.landmark);
    const p = toLocalMeters(o.latitude, o.longitude, ref.lat, ref.lon);
    const t = toLocalMeters(lm.lat, lm.lon, ref.lat, ref.lon);
    if (!byImage.has(o.image)) byImage.set(o.image, []);
    byImage.get(o.image).push({ dE: p.east - t.east, dN: p.north - t.north });
}

console.log(`FOV ${fov.toFixed(2)} deg, heading offset ${headingOffset.toFixed(1)} deg (fitted on all landmarks: compare frames, do not quote as accuracy)\n`);
console.log('frame  alt(m)  roll  pitch  tilt | landmarks | offset E,N (m)   |off| | scatter RMS | pair-dist err | tilt shift if camera NOT stabilised');
const rows = [...byImage.entries()].map(([image, v]) => {
    const f = frames[image];
    const mE = v.reduce((s, x) => s + x.dE, 0) / v.length;
    const mN = v.reduce((s, x) => s + x.dN, 0) / v.length;
    const rms = Math.sqrt(v.reduce((s, x) => s + (x.dE - mE) ** 2 + (x.dN - mN) ** 2, 0) / v.length);
    const tilt = Math.hypot(f.rollDeg, f.pitchDeg);
    const pairs = result.pairs.filter(p => p.image === image);
    return { f, image, n: v.length, mE, mN, off: Math.hypot(mE, mN), rms, tilt,
             rel: pairs.length ? median(pairs.map(p => p.errorPct)) : NaN,
             expected: f.altitude * Math.tan((tilt * Math.PI) / 180) };
}).sort((a, b) => a.tilt - b.tilt);

for (const r of rows) {
    console.log(`${r.image.match(/_(\d+)\.jpg/)[1]}  ${r.f.altitude.toFixed(1).padStart(5)}  ${r.f.rollDeg.toFixed(1).padStart(5)} ${r.f.pitchDeg.toFixed(1).padStart(6)} ${r.tilt.toFixed(1).padStart(5)} | ${String(r.n).padStart(9)} | ${r.mE.toFixed(2).padStart(6)},${r.mN.toFixed(2).padStart(6)}  ${r.off.toFixed(2).padStart(5)} | ${r.rms.toFixed(2).padStart(6)} m    | ${Number.isFinite(r.rel) ? r.rel.toFixed(1) + '%' : 'n/a'}`.padEnd(106)
        + ` | ${r.expected.toFixed(1)} m`);
}
console.log('\nRead it like this: if |off| tracks the last column (grows with tilt), the camera is NOT compensated for body tilt.\n' +
    'If |off| stays about the same (typically 1-2 m, the GPS level) while tilt rises, the Bebop\'s image stabilisation is working.\n' +
    'Only a few frames, so treat the conclusion as suggestive.');
