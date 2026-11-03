const EARTH_RADIUS_M = 6371e3;
const toRad = (deg) => (deg * Math.PI) / 180;

export function distanceMeters(lat1, lon1, lat2, lon2) {
    const φ1 = toRad(lat1);
    const φ2 = toRad(lat2);
    const Δφ = toRad(lat2 - lat1);
    const Δλ = toRad(lon2 - lon1);

    const a = Math.sin(Δφ / 2) ** 2 +
              Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ / 2) ** 2;

    return EARTH_RADIUS_M * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// Local flat-earth (equirectangular) frame around a reference point. Accurate
// to well under a centimetre per kilometre, which is plenty at drone scales.
export function toLocalMeters(lat, lon, refLat, refLon) {
    return {
        east: toRad(lon - refLon) * Math.cos(toRad(refLat)) * EARTH_RADIUS_M,
        north: toRad(lat - refLat) * EARTH_RADIUS_M
    };
}

export function fromLocalMeters(east, north, refLat, refLon) {
    return {
        latitude: refLat + (north / EARTH_RADIUS_M) * (180 / Math.PI),
        longitude: refLon + (east / (EARTH_RADIUS_M * Math.cos(toRad(refLat)))) * (180 / Math.PI)
    };
}
