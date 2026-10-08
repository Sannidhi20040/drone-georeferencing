// YOLOv8 is trained on letterboxed images (aspect ratio preserved, padded to a
// square), so frames are resized the same way and boxes mapped back afterwards.
export function computeLetterbox(width, height, size = 640) {
    const scale = Math.min(size / width, size / height);
    const newWidth = Math.round(width * scale);
    const newHeight = Math.round(height * scale);
    return {
        size,
        scale,
        newWidth,
        newHeight,
        padX: Math.floor((size - newWidth) / 2),
        padY: Math.floor((size - newHeight) / 2)
    };
}

// Converts a center-format box from letterboxed model space back to original image pixels.
export function boxToOriginal(cx, cy, w, h, letterbox) {
    return {
        x: (cx - letterbox.padX) / letterbox.scale,
        y: (cy - letterbox.padY) / letterbox.scale,
        width: w / letterbox.scale,
        height: h / letterbox.scale
    };
}
