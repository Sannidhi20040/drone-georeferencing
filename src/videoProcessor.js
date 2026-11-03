class VideoProcessor {
    constructor() {
        this.video = document.createElement('video');
        this.canvas = document.createElement('canvas');
        this.ctx = this.canvas.getContext('2d', { willReadFrequently: true });
        this.objectUrl = null;
    }

    async loadVideo(file) {
        this.releaseObjectUrl();

        return new Promise((resolve, reject) => {
            this.objectUrl = URL.createObjectURL(file);
            this.video.src = this.objectUrl;
            this.video.onloadedmetadata = () => {
                this.canvas.width = this.video.videoWidth;
                this.canvas.height = this.video.videoHeight;
                console.log(`📹 Video loaded: ${this.video.videoWidth}x${this.video.videoHeight}`);
                console.log(`⏱️  Duration: ${this.video.duration}s`);
                resolve({
                    width: this.video.videoWidth,
                    height: this.video.videoHeight,
                    duration: this.video.duration
                });
            };
            this.video.onerror = () => reject(new Error('The selected file could not be loaded as a video.'));
        });
    }

    async extractFrame(timeSeconds) {
        return new Promise((resolve, reject) => {
            this.video.onseeked = () => {
                this.ctx.drawImage(this.video, 0, 0);
                resolve(this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height));
            };
            this.video.onerror = () => reject(new Error(`Failed to seek the video to ${timeSeconds}s.`));
            this.video.currentTime = timeSeconds;
        });
    }

    releaseObjectUrl() {
        if (this.objectUrl) {
            URL.revokeObjectURL(this.objectUrl);
            this.objectUrl = null;
        }
    }
}

export default VideoProcessor;
