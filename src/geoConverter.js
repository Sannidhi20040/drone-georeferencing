import * as turf from '@turf/rhumb-destination';
import { point } from '@turf/helpers';

class GeoConverter {
    constructor(config = {}) {
        this.fovDiagonal = config.fov || 84;
        this.videoWidth = config.videoWidth || 1920;
        this.videoHeight = config.videoHeight || 1080;
        // Rays closer to the horizon than this hit the ground absurdly far away,
        // where the flat-ground assumption and the pitch reading are unreliable.
        this.minDepressionDeg = config.minDepressionDeg ?? 5;
        this.calculateFOV();
    }
    
    calculateFOV() {
        const aspectRatio = this.videoWidth / this.videoHeight;
        const diagonalRatio = Math.sqrt(this.videoWidth ** 2 + this.videoHeight ** 2);
        const fovDiagRad = (this.fovDiagonal * Math.PI) / 180;
        
        this.fovHorizontal = 2 * Math.atan(
            (this.videoWidth / diagonalRatio) * Math.tan(fovDiagRad / 2)
        ) * (180 / Math.PI);
        
        this.fovVertical = 2 * Math.atan(
            (this.videoHeight / diagonalRatio) * Math.tan(fovDiagRad / 2)
        ) * (180 / Math.PI);
        
        // Pinhole focal lengths in pixels (equal for both axes when derived from
        // a diagonal FOV).
        this.focalX = (this.videoWidth / 2) / Math.tan((this.fovHorizontal * Math.PI / 180) / 2);
        this.focalY = (this.videoHeight / 2) / Math.tan((this.fovVertical * Math.PI / 180) / 2);
        
        console.log(`📐 FOV: H=${this.fovHorizontal.toFixed(2)}°, V=${this.fovVertical.toFixed(2)}°`);
    }
    
    // Casts the pixel's viewing ray onto a flat ground plane `altitude` metres
    // below the camera. telemetry.gimbalPitch is in degrees from the horizon
    // (0 = level, -90 = straight down, the default). Returns null when the
    // altitude is not positive or the ray does not reach the ground.
    pixelToGPS(pixelX, pixelY, telemetry) {
        const { lat, lon, altitude, heading } = telemetry;
        const pitch = telemetry.gimbalPitch ?? -90;
        
        if (!(altitude > 0)) return null;
        
        // Ray through the pixel in camera axes: x right, y image-down, z forward.
        const rayX = (pixelX - this.videoWidth / 2) / this.focalX;
        const rayY = (pixelY - this.videoHeight / 2) / this.focalY;
        
        // Express it in (forward, right, down) axes level with the drone's heading.
        const depression = (-pitch * Math.PI) / 180;
        const forward = Math.cos(depression) - rayY * Math.sin(depression);
        const right = rayX;
        const down = Math.sin(depression) + rayY * Math.cos(depression);
        
        const rayLength = Math.sqrt(forward ** 2 + right ** 2 + down ** 2);
        if (down / rayLength < Math.sin((this.minDepressionDeg * Math.PI) / 180)) return null;
        
        const scale = altitude / down;
        const metersX = right * scale;
        const metersY = forward * scale;
        
        const distanceMeters = Math.sqrt(metersX ** 2 + metersY ** 2);
        // atan2(0, -0) is 180deg, which would report a bogus bearing for a
        // detection exactly under the drone; a zero offset has no direction.
        let angleFromNorth = distanceMeters === 0
            ? 0
            : Math.atan2(metersX, metersY) * (180 / Math.PI);
        let absoluteBearing = (heading + angleFromNorth + 360) % 360;
        
        const dronePoint = point([lon, lat]);
        const destination = turf.rhumbDestination(dronePoint, distanceMeters / 1000, absoluteBearing);
        
        return {
            latitude: destination.geometry.coordinates[1],
            longitude: destination.geometry.coordinates[0],
            distanceFromDrone: distanceMeters,
            bearing: absoluteBearing
        };
    }
    
    isValidGPS(lat, lon) {
        return lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180;
    }
}

export default GeoConverter;
