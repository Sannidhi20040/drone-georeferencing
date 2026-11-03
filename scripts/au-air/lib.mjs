import GeoConverter from '../../src/geoConverter.js';
import { distanceMeters } from '../../src/geo.js';

export const IMAGE_WIDTH = 1920;
export const IMAGE_HEIGHT = 1080;

export function median(values) {
    if (values.length === 0) return NaN;
    const s = [...values].sort((a, b) => a - b);
    const mid = Math.floor(s.length / 2);
    return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

// Centered running median; the window shrinks at the ends. Removes the
// single-sample GPS jumps present in the AU-AIR logs without lagging the track.
export function medianFilter(values, window = 25) {
    const half = Math.floor(window / 2);
    return values.map((_, i) =>
        median(values.slice(Math.max(0, i - half), Math.min(values.length, i + half + 1))));
}

export function summarize(errors) {
    if (errors.length === 0) return { n: 0, mean: NaN, median: NaN, rmse: NaN, max: NaN };
    return {
        n: errors.length,
        mean: errors.reduce((s, e) => s + e, 0) / errors.length,
        median: median(errors),
        rmse: Math.sqrt(errors.reduce((s, e) => s + e * e, 0) / errors.length),
        max: Math.max(...errors)
    };
}

// GeoConverter logs its FOV on every construction; keep sweeps quiet.
const converters = new Map();
export function makeConverter(fov) {
    const key = fov.toFixed(4);
    if (!converters.has(key)) {
        const log = console.log;
        console.log = () => {};
        try {
            converters.set(key, new GeoConverter({ fov, videoWidth: IMAGE_WIDTH, videoHeight: IMAGE_HEIGHT }));
        } finally {
            console.log = log;
        }
    }
    return converters.get(key);
}

// Frames are keyed by image name: { image, lat, lon, altitude, yaw } with
// altitude in metres and yaw in degrees (heading = yaw + headingOffset).
function project(frame, pixel, { fov, headingOffset = 0 }) {
    return makeConverter(fov).pixelToGPS(pixel.x, pixel.y, {
        lat: frame.lat,
        lon: frame.lon,
        altitude: frame.altitude,
        heading: (((frame.yaw + headingOffset) % 360) + 360) % 360
    });
}

// Scores landmarks against their satellite coordinates.
//   landmarks: [{ id, lat, lon, observations: [{ image, x, y }] }]
//   frames:    { [image]: frame }
//   include:   optional Set of landmark ids to score (others are ignored)
// Reports absolute error (predicted vs satellite position, includes the
// drone's GPS error) and relative error (distance between two landmarks seen
// in the SAME frame, which cancels the drone's GPS and heading-origin error).
export function evaluateLandmarks({ landmarks, frames, fov, headingOffset = 0, include = null }) {
    const used = landmarks.filter(l => !include || include.has(l.id));
    const observations = [];
    const byImage = new Map();

    for (const lm of used) {
        for (const obs of lm.observations) {
            const frame = frames[obs.image];
            if (!frame) continue;
            const p = project(frame, obs, { fov, headingOffset });
            if (!p) continue;
            const rec = {
                landmark: lm.id, image: obs.image,
                latitude: p.latitude, longitude: p.longitude,
                errorMeters: distanceMeters(p.latitude, p.longitude, lm.lat, lm.lon)
            };
            observations.push(rec);
            if (!byImage.has(obs.image)) byImage.set(obs.image, []);
            byImage.get(obs.image).push({ lm, rec });
        }
    }

    const pairs = [];
    for (const [image, items] of byImage) {
        for (let i = 0; i < items.length; i++) {
            for (let j = i + 1; j < items.length; j++) {
                const a = items[i], b = items[j];
                const truth = distanceMeters(a.lm.lat, a.lm.lon, b.lm.lat, b.lm.lon);
                const predicted = distanceMeters(a.rec.latitude, a.rec.longitude, b.rec.latitude, b.rec.longitude);
                if (truth < 1) continue; // too close for a meaningful percentage
                pairs.push({
                    a: a.lm.id, b: b.lm.id, image, truthMeters: truth, predictedMeters: predicted,
                    errorMeters: Math.abs(predicted - truth),
                    errorPct: (100 * Math.abs(predicted - truth)) / truth
                });
            }
        }
    }

    return {
        observations,
        pairs,
        absolute: summarize(observations.map(o => o.errorMeters)),
        relativeMeters: summarize(pairs.map(p => p.errorMeters)),
        relativePct: summarize(pairs.map(p => p.errorPct))
    };
}

function search(lo, hi, step, objective) {
    let best = { value: lo, objective: Infinity };
    for (let v = lo; v <= hi + 1e-9; v += step) {
        const o = objective(v);
        if (Number.isFinite(o) && o < best.objective) best = { value: v, objective: o };
    }
    return best;
}

// FOV is the scale of the image on the ground, so it is fitted to distances
// between landmarks seen together in one frame (independent of GPS and heading).
export function calibrateFov({ landmarks, frames, calibrationIds, range = [30, 130], step = 0.25 }) {
    const include = new Set(calibrationIds);
    const best = search(range[0], range[1], step, fov => {
        const { pairs } = evaluateLandmarks({ landmarks, frames, fov, include });
        if (pairs.length === 0) return NaN;
        return pairs.reduce((s, p) => s + (p.predictedMeters / p.truthMeters - 1) ** 2, 0) / pairs.length;
    });
    return { fov: best.value, objective: best.objective };
}

// A constant offset between the log's yaw and true north rotates every
// prediction about the drone; it is fitted to absolute position error.
export function calibrateHeadingOffset({ landmarks, frames, fov, calibrationIds, range = [-180, 180], step = 0.5 }) {
    const include = new Set(calibrationIds);
    const best = search(range[0], range[1], step, headingOffset => {
        const { absolute } = evaluateLandmarks({ landmarks, frames, fov, headingOffset, include });
        return absolute.n ? absolute.median : NaN;
    });
    return { headingOffset: best.value, medianError: best.objective };
}
