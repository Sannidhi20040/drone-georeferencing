// The georeferencing math needs height ABOVE GROUND. Flight logs differ:
//   'agl' - altitude is already height above the ground below the drone.
//   'asl' - altitude is above sea level (or the takeoff point, measured from
//           a barometer that was zeroed elsewhere); subtract the first log
//           sample, which assumes the drone took off from ground level.
// `offset` is subtracted afterwards, e.g. to correct for a rooftop takeoff
// or known terrain elevation.
export function effectiveAltitude(rawAltitude, { mode = 'agl', firstSampleAltitude = 0, offset = 0 } = {}) {
    const base = mode === 'asl' ? firstSampleAltitude : 0;
    return rawAltitude - base - offset;
}
