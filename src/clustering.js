import { distanceMeters } from './geo.js';

// Merges same-class detections closer than maxDistance meters into one point.
// Suited to stationary objects (parked vehicles); see tracker.js for moving ones.
export function clusterDetections(detections, maxDistance = 5) {
    const clusters = [];

    for (const det of detections) {
        let merged = false;

        for (const cluster of clusters) {
            const distance = distanceMeters(
                det.latitude, det.longitude,
                cluster.latitude, cluster.longitude
            );

            if (distance < maxDistance && det.class === cluster.class) {
                // Running weighted average, so the centroid converges to the
                // true mean instead of drifting toward the last merged detection.
                const newCount = cluster.count + 1;
                cluster.latitude = (cluster.latitude * cluster.count + det.latitude) / newCount;
                cluster.longitude = (cluster.longitude * cluster.count + det.longitude) / newCount;
                cluster.confidence = (cluster.confidence * cluster.count + det.confidence) / newCount;
                cluster.count = newCount;
                cluster.simulated = Boolean(cluster.simulated || det.simulated);
                merged = true;
                break;
            }
        }

        if (!merged) {
            clusters.push({ ...det, count: 1 });
        }
    }

    return clusters;
}
