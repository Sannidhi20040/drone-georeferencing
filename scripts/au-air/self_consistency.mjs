// Georeferences the dataset's own ground-truth boxes and checks that the same
// object seen in two frames lands in the same place. Needs no satellite imagery.
//   node scripts/au-air/self_consistency.mjs [--gap 50] [--step 20] [--classes 1]
//
// This measures RELATIVE repeatability, not absolute accuracy, and it cannot
// pin down FOV (see the table: it barely changes with FOV for a hovering drone).
// The 4 m matching radius also biases the result toward small numbers, so report
// the matched percentage next to the median.
import fs from 'fs';
import path from 'path';
import { parseArgs } from './args.mjs';
import { makeConverter, median } from './lib.mjs';
import { distanceMeters } from '../../src/geo.js';

const args = parseArgs(process.argv.slice(2), {
    clip: '20190829091111', data: 'data_check', gap: 50, step: 20, classes: '1', radius: 4
});
const classes = String(args.classes).split(',').map(Number);
const frames = JSON.parse(fs.readFileSync(path.join(args.data, 'derived', `${args.clip}.json`))).frames;

function project(frame, fov, headingFn) {
    const converter = makeConverter(fov);
    return frame.boxes.filter(b => classes.includes(b.class)).map(b => {
        const r = converter.pixelToGPS(b.left + b.width / 2, b.top + b.height / 2, {
            lat: frame.lat, lon: frame.lon, altitude: frame.altitude, heading: headingFn(frame.yaw)
        });
        return r && { lat: r.latitude, lon: r.longitude, cls: b.class };
    }).filter(Boolean);
}

function consistency(fov, headingFn) {
    const dists = [];
    let candidates = 0;
    for (let i = 0; i + args.gap < frames.length; i += args.step) {
        // Only compare frames from the same continuous run, so a real move across a gap is not counted.
        if (frames[i + args.gap].index - frames[i].index > args.gap * 1.5) continue;
        const P = project(frames[i], fov, headingFn);
        const Q = project(frames[i + args.gap], fov, headingFn);
        for (const p of P) {
            candidates++;
            let best = Infinity;
            for (const q of Q) if (q.cls === p.cls) best = Math.min(best, distanceMeters(p.lat, p.lon, q.lat, q.lon));
            if (best <= args.radius) dists.push(best);
        }
    }
    return { median: median(dists), matched: Math.round((100 * dists.length) / Math.max(1, candidates)), n: dists.length };
}

const conventions = { 'heading = +yaw': h => h, 'heading = -yaw': h => -h, 'heading = 90-yaw': h => 90 - h };
console.log(`classes ${classes.join(',')}, frames ${args.gap} apart (${args.gap / 5} s), match radius ${args.radius} m`);
console.log('median distance between the same object in two frames | % of objects matched\n');
console.log('FOV'.padEnd(6) + Object.keys(conventions).map(k => k.padEnd(30)).join(''));
for (const fov of [55, 65, 75, 84, 95, 105]) {
    let row = String(fov).padEnd(6);
    for (const f of Object.values(conventions)) {
        const c = consistency(fov, f);
        row += `${c.median.toFixed(2)} m | ${c.matched}% (n=${c.n})`.padEnd(30);
    }
    console.log(row);
}
