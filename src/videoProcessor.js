class VideoProcessor {
    constructor() {
        this.video = document.createElement('video');
        this.canvas = document.createElement('canvas');
        this.ctx = this.canvas.getContext('2d');
        this.currentFrame = 0;
    }
    
    async loadVideo(file) {
        return new Promise((resolve, reject) => {
            this.video.src = URL.createObjectURL(file);
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
            this.video.onerror = reject;
        });
    }
    
    async extractFrame(timeSeconds) {
        return new Promise((resolve) => {
            this.video.currentTime = timeSeconds;
            this.video.onseeked = () => {
                this.ctx.drawImage(this.video, 0, 0);
                const imageData = this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);
                resolve(imageData);
            };
        });
    }
    
    getFrameAsBlob() {
        return new Promise((resolve) => {
            this.canvas.toBlob((blob) => resolve(blob), 'image/jpeg', 0.8);
        });
    }
}

export default VideoProcessor;
