import * as turf from '@turf/rhumb-destination';
import { point } from '@turf/helpers';

class GeoConverter {
    constructor(config = {}) {
        this.fovDiagonal = config.fov || 84;
        this.videoWidth = config.videoWidth || 1920;
        this.videoHeight = config.videoHeight || 1080;
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
        
        console.log(`📐 FOV: H=${this.fovHorizontal.toFixed(2)}°, V=${this.fovVertical.toFixed(2)}°`);
    }
    
    pixelToGPS(pixelX, pixelY, telemetry) {
        const { lat, lon, altitude, heading } = telemetry;
        
        const groundWidth = 2 * altitude * Math.tan((this.fovHorizontal * Math.PI / 180) / 2);
        const groundHeight = 2 * altitude * Math.tan((this.fovVertical * Math.PI / 180) / 2);
        
        const centerX = this.videoWidth / 2;
        const centerY = this.videoHeight / 2;
        
        const offsetX = (pixelX - centerX) / (this.videoWidth / 2);
        const offsetY = (pixelY - centerY) / (this.videoHeight / 2);
        
        const metersX = offsetX * (groundWidth / 2);
        const metersY = -offsetY * (groundHeight / 2);
        
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
