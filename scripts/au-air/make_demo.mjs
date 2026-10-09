// Builds a demo video + matching flight log from a continuous stretch of AU-AIR frames.
//   node scripts/au-air/make_demo.mjs [--clip 20190829091111] [--start 2062] [--frames 150]
// Needs ffmpeg (brew install ffmpeg) and the output of prepare.mjs. Writes to data_check/derived/demo/.
// The frames and telemetry are real, from the same flight; AU-AIR is licensed non-commercial,
// so use the result for demos and research only and do not publish it.
import fs from 'fs';
import path from 'path';
import { spawnSync } from 'child_process';
import { parseArgs } from './args.mjs';

const args = parseArgs(process.argv.slice(2), { clip: '20190829091111', start: 2062, frames: 150, data: 'data_check' });
const FPS = 5; // AU-AIR frames are extracted at 5 fps
const all = JSON.parse(fs.readFileSync(path.join(args.data, 'derived', `${args.clip}.json`))).frames;
const seg = all.slice(args.start, args.start + args.frames);
if (seg.length < args.frames) throw new Error('Not enough frames after --start');
for (let i = 1; i < seg.length; i++) {
    if (seg[i].index - seg[i - 1].index !== 1) {
        throw new Error(`Frame numbering has a gap at ${seg[i - 1].index} -> ${seg[i].index}; choose a continuous stretch`);
    }
}

const out = path.join(args.data, 'derived', 'demo');
fs.mkdirSync(out, { recursive: true });
const first = seg[0].index;
const pattern = path.join(args.data, 'images', `frame_${args.clip}_x_%07d.jpg`);
const video = path.join(out, 'demo_video.mp4');

const r = spawnSync('ffmpeg', [
    '-y', '-hide_banner', '-loglevel', 'error',
    '-framerate', String(FPS), '-start_number', String(first), '-i', pattern,
    '-frames:v', String(seg.length), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20',
    '-r', String(FPS), '-movflags', '+faststart', video
], { stdio: 'inherit' });
if (r.status !== 0) throw new Error('ffmpeg failed');

const rows = ['timestamp,latitude,longitude,altitude,heading,isVideo'];
for (const f of seg) {
    const heading = ((f.yaw % 360) + 360) % 360;
    rows.push([((f.index - first) / FPS).toFixed(2), f.lat.toFixed(8), f.lon.toFixed(8),
               f.altitude.toFixed(3), heading.toFixed(2), 1].join(','));
}
fs.writeFileSync(path.join(out, 'demo_flight_log.csv'), rows.join('\n') + '\n');

const duration = seg.length / FPS;
const mid = seg[Math.floor(seg.length / 2)];
console.log(`wrote ${video} (${duration} s, ${FPS} fps, 1920x1080) and demo_flight_log.csv`);
console.log(`frames ${first}..${seg.at(-1).index}, altitude ${Math.min(...seg.map(f => f.altitude)).toFixed(1)}-${Math.max(...seg.map(f => f.altitude)).toFixed(1)} m, ` +
    `mean tilt ${(seg.reduce((a, f) => a + Math.hypot(f.rollDeg, f.pitchDeg), 0) / seg.length).toFixed(1)} deg`);
console.log(`drone position near ${mid.lat.toFixed(5)}, ${mid.lon.toFixed(5)} (Aarhus, Denmark)`);
