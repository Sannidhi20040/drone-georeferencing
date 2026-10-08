import { toLocalMeters, fromLocalMeters } from './geo.js';

// Generous top speeds (m/s) used to widen the association gate with elapsed time.
const DEFAULT_MAX_SPEEDS = { 'small-vehicle': 20, 'large-vehicle': 15, human: 3 };
const FALLBACK_MAX_SPEED = 15;

// Lightweight multi-object tracker in the spirit of SORT: per-class,
// constant-velocity (alpha-beta) prediction, and greedy nearest-first
// one-to-one assignment within each frame. Positions are tracked in a local
// metric frame, so it works directly on georeferenced detections.
//
// Only reliable when frames are sampled densely enough that an object moves
// less than a few car-lengths between samples; with sparse sampling, distinct
// vehicles fall inside each other's gates and can swap identities.
export function trackDetections(detections, options = {}) {
    const {
        gateMeters = 5,
        maxGapSeconds = 6,
        maxSpeeds = DEFAULT_MAX_SPEEDS,
        alpha = 0.6,
        beta = 0.3
    } = options;

    if (detections.length === 0) return [];

    const refLat = detections[0].latitude;
    const refLon = detections[0].longitude;
    const sorted = [...detections].sort((a, b) => a.timestamp - b.timestamp);

    const tracks = [];
    let nextId = 1;

    let i = 0;
    while (i < sorted.length) {
        const t = sorted[i].timestamp;
        const group = [];
        while (i < sorted.length && sorted[i].timestamp === t) group.push(sorted[i++]);

        const points = group.map(det => toLocalMeters(det.latitude, det.longitude, refLat, refLon));

        // Candidate (track, detection) pairs inside the gate; a track can only
        // be updated once per frame, and tracks born this frame are excluded.
        const pairs = [];
        tracks.forEach((track, ti) => {
            const dt = t - track.lastT;
            if (dt <= 0 || dt > maxGapSeconds) return;

            const predicted = {
                east: track.pos.east + track.vel.east * dt,
                north: track.pos.north + track.vel.north * dt
            };
            const maxSpeed = maxSpeeds[track.class] ?? FALLBACK_MAX_SPEED;
            const gate = gateMeters + maxSpeed * dt;

            group.forEach((det, di) => {
                if (det.class !== track.class) return;
                const d = Math.hypot(points[di].east - predicted.east, points[di].north - predicted.north);
                if (d <= gate) pairs.push({ ti, di, d, dt, predicted });
            });
        });

        pairs.sort((a, b) => a.d - b.d);
        const usedTracks = new Set();
        const usedDets = new Set();

        for (const { ti, di, dt, predicted } of pairs) {
            if (usedTracks.has(ti) || usedDets.has(di)) continue;
            usedTracks.add(ti);
            usedDets.add(di);
            updateTrack(tracks[ti], group[di], points[di], predicted, dt, t, alpha, beta);
        }

        group.forEach((det, di) => {
            if (usedDets.has(di)) return;
            tracks.push({
                id: nextId++,
                class: det.class,
                pos: points[di],
                vel: { east: 0, north: 0 },
                lastT: t,
                count: 1,
                confidence: det.confidence,
                simulated: Boolean(det.simulated),
                last: det,
                path: [{ ...points[di], timestamp: t }]
            });
        });
    }

    return tracks.map(track => {
        const { latitude, longitude } = fromLocalMeters(track.pos.east, track.pos.north, refLat, refLon);
        return {
            ...track.last,
            trackId: track.id,
            class: track.class,
            confidence: track.confidence,
            latitude,
            longitude,
            count: track.count,
            speed: Math.hypot(track.vel.east, track.vel.north),
            simulated: track.simulated,
            path: track.path.map(p => ({
                ...fromLocalMeters(p.east, p.north, refLat, refLon),
                timestamp: p.timestamp
            }))
        };
    });
}

function updateTrack(track, det, point, predicted, dt, t, alpha, beta) {
    if (track.count === 1) {
        // Two points define a velocity directly; the filter refines it afterwards.
        track.vel = {
            east: (point.east - track.pos.east) / dt,
            north: (point.north - track.pos.north) / dt
        };
        track.pos = { ...point };
    } else {
        const rEast = point.east - predicted.east;
        const rNorth = point.north - predicted.north;
        track.pos = { east: predicted.east + alpha * rEast, north: predicted.north + alpha * rNorth };
        track.vel = {
            east: track.vel.east + (beta * rEast) / dt,
            north: track.vel.north + (beta * rNorth) / dt
        };
    }

    track.confidence = (track.confidence * track.count + det.confidence) / (track.count + 1);
    track.count += 1;
    track.simulated = track.simulated || Boolean(det.simulated);
    track.lastT = t;
    track.last = det;
    track.path.push({ ...track.pos, timestamp: t });
}
