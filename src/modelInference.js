import * as ort from 'onnxruntime-web';
import { computeLetterbox, boxToOriginal } from './letterbox.js';

class ModelInference {
    constructor() {
        this.modelLoaded = false;
        this.usedSimulation = false;
        this.simulationReason = null;
        this.session = null;
        this.loadedPath = null;
        this.inputShape = [1, 3, 640, 640];
        this.classNames = ['small-vehicle', 'large-vehicle', 'human'];
        this.modelPath = `${import.meta.env.BASE_URL}models/aerial_yolov8.onnx`;
    }
    
    async loadModel() {
        // Re-creating the session on every run re-parses a 43 MB model.
        if (this.session && this.loadedPath === this.modelPath) {
            this.modelLoaded = true;
            this.usedSimulation = false;
            this.simulationReason = null;
            return true;
        }
        
        try {
            console.log('🤖 Loading YOLO model from:', this.modelPath);

            this.session = await ort.InferenceSession.create(this.modelPath, {
                executionProviders: ['wasm'],
                graphOptimizationLevel: 'all',
            });
            
            this.loadedPath = this.modelPath;
            this.modelLoaded = true;
            this.usedSimulation = false;
            this.simulationReason = null;
            console.log('✅ YOLO model loaded successfully!');
            console.log('📊 Input name:', this.session.inputNames[0]);
            console.log('📊 Output name:', this.session.outputNames[0]);
            return true;
            
        } catch (error) {
            console.error('❌ Model loading failed:', error);
            console.warn('⚠️  Using simulation mode instead');
            this.modelLoaded = false;
            this.session = null;
            this.loadedPath = null;
            this.simulationReason = `Model failed to load: ${error.message}`;
            return false;
        }
    }
    
    async detectObjects(imageData, confidenceThreshold = 0.5) {
        if (!this.modelLoaded || !this.session) {
            console.warn('⚠️  Running in simulation mode');
            return this.simulateDetections(imageData.width, imageData.height);
        }
        
        try {
            const startTime = performance.now();
            
            // Preprocess
            const { tensor: inputTensor, letterbox } = this.preprocessImage(imageData);
            
            // Run inference
            const feeds = { [this.session.inputNames[0]]: inputTensor };
            const results = await this.session.run(feeds);
            const output = results[this.session.outputNames[0]];
            
            // Post-process
            const detections = this.postProcessYOLOv8(
                output.data, 
                output.dims,
                confidenceThreshold, 
                letterbox,
                imageData.width, 
                imageData.height
            );
            
            const elapsed = performance.now() - startTime;
            console.log(`🎯 Detected ${detections.length} objects in ${elapsed.toFixed(1)}ms`);
            
            return detections;
            
        } catch (error) {
            console.error('❌ Inference error:', error);
            this.simulationReason = `Inference error: ${error.message}`;
            return this.simulateDetections(imageData.width, imageData.height);
        }
    }
    
    preprocessImage(imageData) {
        const targetSize = 640;
        const letterbox = computeLetterbox(imageData.width, imageData.height, targetSize);

        const srcCanvas = document.createElement('canvas');
        srcCanvas.width = imageData.width;
        srcCanvas.height = imageData.height;
        srcCanvas.getContext('2d', { willReadFrequently: true }).putImageData(imageData, 0, 0);

        // Letterbox: scale to fit while preserving aspect ratio and pad with the
        // neutral gray (114) Ultralytics uses in training, rather than stretching.
        const dstCanvas = document.createElement('canvas');
        dstCanvas.width = targetSize;
        dstCanvas.height = targetSize;
        const dstCtx = dstCanvas.getContext('2d', { willReadFrequently: true });
        dstCtx.fillStyle = 'rgb(114, 114, 114)';
        dstCtx.fillRect(0, 0, targetSize, targetSize);
        dstCtx.drawImage(
            srcCanvas,
            0, 0, imageData.width, imageData.height,
            letterbox.padX, letterbox.padY, letterbox.newWidth, letterbox.newHeight
        );
        const resized = dstCtx.getImageData(0, 0, targetSize, targetSize).data;

        // CHW float32, normalized to [0, 1]
        const pixelCount = targetSize * targetSize;
        const input = new Float32Array(3 * pixelCount);

        for (let i = 0; i < pixelCount; i++) {
            const srcIdx = i * 4;
            input[i] = resized[srcIdx] / 255.0;                       // R
            input[pixelCount + i] = resized[srcIdx + 1] / 255.0;       // G
            input[2 * pixelCount + i] = resized[srcIdx + 2] / 255.0;   // B
        }

        return {
            tensor: new ort.Tensor('float32', input, [1, 3, targetSize, targetSize]),
            letterbox
        };
    }
    
    postProcessYOLOv8(output, dims, threshold, letterbox, imgWidth, imgHeight) {
        // Raw YOLOv8 detect output, channel-major: [1, 4 + numClasses, 8400]
        // (here [1, 7, 8400]): cx, cy, w, h in letterboxed 640x640 pixels, then
        // one score per class. YOLOv8 has no separate objectness channel.
        const [, , numBoxes] = dims;
        
        const detections = [];
        
        for (let i = 0; i < numBoxes; i++) {
            const scores = [
                output[4 * numBoxes + i],     // small-vehicle
                output[5 * numBoxes + i],     // large-vehicle
                output[6 * numBoxes + i]      // human
            ];
            
            const maxScore = Math.max(...scores);
            if (maxScore < threshold) continue;
            
            const box = boxToOriginal(
                output[i],
                output[numBoxes + i],
                output[2 * numBoxes + i],
                output[3 * numBoxes + i],
                letterbox
            );
            
            // A box centered in the gray padding is not on the actual frame.
            if (box.x < 0 || box.x > imgWidth || box.y < 0 || box.y > imgHeight) continue;
            
            detections.push({
                class: this.classNames[scores.indexOf(maxScore)],
                confidence: maxScore,
                x: box.x,
                y: box.y,
                width: box.width,
                height: box.height
            });
        }
        
        return this.applyNMS(detections, 0.45);
    }
    
    applyNMS(boxes, iouThreshold) {
        // Sort by confidence
        boxes.sort((a, b) => b.confidence - a.confidence);
        
        const keep = [];
        const suppressed = new Set();
        
        for (let i = 0; i < boxes.length; i++) {
            if (suppressed.has(i)) continue;
            
            keep.push(boxes[i]);
            
            for (let j = i + 1; j < boxes.length; j++) {
                if (suppressed.has(j)) continue;
                
                if (boxes[i].class === boxes[j].class) {
                    const iou = this.calculateIoU(boxes[i], boxes[j]);
                    if (iou > iouThreshold) {
                        suppressed.add(j);
                    }
                }
            }
        }
        
        return keep;
    }
    
    calculateIoU(box1, box2) {
        const x1_min = box1.x - box1.width / 2;
        const y1_min = box1.y - box1.height / 2;
        const x1_max = box1.x + box1.width / 2;
        const y1_max = box1.y + box1.height / 2;
        
        const x2_min = box2.x - box2.width / 2;
        const y2_min = box2.y - box2.height / 2;
        const x2_max = box2.x + box2.width / 2;
        const y2_max = box2.y + box2.height / 2;
        
        const inter_x_min = Math.max(x1_min, x2_min);
        const inter_y_min = Math.max(y1_min, y2_min);
        const inter_x_max = Math.min(x1_max, x2_max);
        const inter_y_max = Math.min(y1_max, y2_max);
        
        const inter_area = Math.max(0, inter_x_max - inter_x_min) * 
                          Math.max(0, inter_y_max - inter_y_min);
        
        const box1_area = box1.width * box1.height;
        const box2_area = box2.width * box2.height;
        const union_area = box1_area + box2_area - inter_area;
        
        return inter_area / union_area;
    }
    
    simulateDetections(width, height) {
        this.usedSimulation = true;
        const numDetections = Math.floor(Math.random() * 5) + 2;
        const detections = [];
        
        for (let i = 0; i < numDetections; i++) {
            detections.push({
                simulated: true,
                class: this.classNames[Math.floor(Math.random() * this.classNames.length)],
                confidence: 0.5 + Math.random() * 0.4,
                x: Math.random() * width,
                y: Math.random() * height,
                width: 50 + Math.random() * 100,
                height: 50 + Math.random() * 100
            });
        }
        
        return detections;
    }
}

export default ModelInference;
