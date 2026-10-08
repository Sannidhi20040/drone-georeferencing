// Converts AU-AIR annotations for one clip into a clean per-frame table.
//   node scripts/au-air/prepare.mjs [--clip 20190829091111] [--smooth 25] [--data data_check]
// Writes data_check/derived/<clip>.json (used by the picker and evaluator) and
// <clip>_log.csv (flight-log CSV in this app's format, 5 frames per second).
import fs from 'fs';
import path from 'path';
import { parseArgs } from './args.mjs';
import { medianFilter } from './lib.mjs';

const args = parseArgs(process.argv.slice(2), { clip: '20190829091111', smooth: 25, data: 'data_check' });
const clip = String(args.clip);
const FRAMES_PER_SECOND = 5; // AU-AIR frames are extracted at 5 fps

const annotations = JSON.parse(fs.readFileSync(path.join(args.data, 'annotations.json'))).annotations;
const rows = annotations
    .filter(a => a.image_name.startsWith(`frame_${clip}_`))
    .map(a => ({ a, index: Number(a.image_name.match(/_(\d+)\.jpg$/)[1]) }))
    .sort((p, q) => p.index - q.index);

if (rows.length === 0) {
    console.error(`No frames found for clip ${clip}`);
    process.exit(1);
}

const lat = rows.map(r => r.a.latitude);
const lon = rows.map(r => r.a.longtitude);          // sic: the dataset's spelling
const alt = rows.map(r => r.a.altitude / 1000);     // millimetres -> metres
const window = Math.max(1, Math.round(args.smooth));

// Missing frames leave gaps in the frame numbering; the drone really moves
// across them, so smooth each continuous run separately, never across a gap.
const MAX_CONTIGUOUS_GAP = 5;
const segments = [];
rows.forEach((r, i) => {
    if (i === 0 || r.index - rows[i - 1].index > MAX_CONTIGUOUS_GAP) segments.push([]);
    segments.at(-1).push(i);
});
const smoothBySegment = (values) => {
    const out = new Array(values.length);
    for (const seg of segments) {
        medianFilter(seg.map(i => values[i]), window).forEach((v, k) => { out[seg[k]] = v; });
    }
    return out;
};
const latS = smoothBySegment(lat);
const lonS = smoothBySegment(lon);
const altS = smoothBySegment(alt);

const frames = rows.map((r, i) => ({
    image: r.a.image_name,
    index: r.index,
    lat: latS[i], lon: lonS[i], altitude: altS[i],
    rawLat: lat[i], rawLon: lon[i], rawAltitude: alt[i],
    yaw: (r.a.angle_psi * 180) / Math.PI,           // radians -> degrees
    rollDeg: (r.a.angle_phi * 180) / Math.PI,
    pitchDeg: (r.a.angle_theta * 180) / Math.PI,
    boxes: r.a.bbox
}));

const outDir = path.join(args.data, 'derived');
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, `${clip}.json`), JSON.stringify({ clip, smoothWindow: window, frames }));

const first = frames[0].index;
const csv = ['timestamp,latitude,longitude,altitude,heading,isVideo'];
for (const f of frames) {
    const heading = ((f.yaw % 360) + 360) % 360;
    csv.push([((f.index - first) / FRAMES_PER_SECOND).toFixed(3), f.lat.toFixed(8), f.lon.toFixed(8),
              f.altitude.toFixed(3), heading.toFixed(2), 1].join(','));
}
fs.writeFileSync(path.join(outDir, `${clip}_log.csv`), csv.join('\n') + '\n');

const metres = (i, j) => Math.hypot((lat[j] - lat[i]) * 111320,
    (lon[j] - lon[i]) * 111320 * Math.cos((lat[i] * Math.PI) / 180));
const within = [], across = [];
for (let i = 1; i < rows.length; i++) {
    (rows[i].index - rows[i - 1].index > MAX_CONTIGUOUS_GAP ? across : within).push(metres(i - 1, i));
}
console.log(`clip ${clip}: ${frames.length} frames, indices ${first}..${frames.at(-1).index}`);
console.log(`altitude ${Math.min(...alt).toFixed(1)}-${Math.max(...alt).toFixed(1)} m (converted from mm)`);
console.log(`${segments.length} continuous segments (${segments.length - 1} gaps of missing frames)`);
console.log(`largest raw GPS step inside a segment: ${Math.max(...within).toFixed(2)} m; across a gap: ${across.length ? Math.max(...across).toFixed(1) : '-'} m (real movement)`);
console.log(`wrote ${path.join(outDir, `${clip}.json`)} and ${clip}_log.csv`);
