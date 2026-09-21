# 🚁 Drone Georeferencing System

**🌐 [Live Demo](https://sannidhi20040.github.io/drone-georeferencing/)** | **📂 [GitHub](https://github.com/Sannidhi20040/drone-georeferencing)**

Real-time vehicle and pedestrian detection from drone footage with GPS georeferencing and interactive mapping.

![System Demo](https://img.shields.io/badge/Status-Live-brightgreen)
![ML](https://img.shields.io/badge/ML-YOLOv8-blue)
![Map](https://img.shields.io/badge/Map-Leaflet.js-green)

## 🎯 Features

- **YOLOv8 Object Detection**: Trained on 9,287 aerial images (VisDrone dataset)
- **Pixel-to-GPS Transformation**: Accurate coordinate mapping using camera FOV calculations
- **Flight Log Integration**: Parse and sync CSV telemetry data, with linear interpolation between samples for smoother tracking between sparse log entries
- **Flight Path Visualization**: The drone's GPS track is drawn on the map as soon as a flight log is loaded
- **Detection Clustering**: Merge duplicate detections using spatial proximity, with a running weighted-average centroid so clusters converge to the true position
- **Confidence-Coded Markers**: Detection markers are colored and sized by confidence/detection count
- **Interactive Mapping**: Real-time visualization with OpenStreetMap
- **Export Tools**: GeoJSON and CSV export for GIS applications

## 📊 Model Performance

| Metric | Value |
|--------|-------|
| mAP50 | 0.583 |
| mAP50-95 | 0.366 |
| Small Vehicle (mAP50) | 0.764 |
| Large Vehicle (mAP50) | 0.713 |
| Pedestrian (mAP50) | 0.272 |

## 🚀 Quick Start

\`\`\`bash
git clone https://github.com/Sannidhi20040/drone-georeferencing.git
cd drone-georeferencing
npm install
npm run dev
\`\`\`

## 🧪 Testing

Unit tests cover the georeferencing math (FOV split, pixel-to-GPS projection) and flight-log parsing/interpolation:

\`\`\`bash
npm test
\`\`\`

## 🛠️ Tech Stack

- **Frontend**: Vanilla JavaScript, Vite, Leaflet.js
- **ML/CV**: YOLOv8, ONNX Runtime Web
- **Geospatial**: Custom FOV transformation, PapaParse
- **Testing**: Vitest

## ⚠️ Known Limitations

- **Nadir-only georeferencing**: pixel-to-GPS math assumes a level, straight-down camera. It does not compensate for gimbal pitch/roll, so results will be off for angled (non-nadir) footage.
- **Heading source**: bearing is computed from the drone's flight-log heading, not gimbal yaw — if the camera can pan independently of the airframe, detections will be misplaced.
- **Frame extraction speed**: frames are extracted via HTML `<video>` seeking (`currentTime` + `seeked`), which is slow for long videos. A WebCodecs-based decoder or server-side extraction (ffmpeg) would be significantly faster.
- **Main-thread inference**: model inference runs on the UI thread (no Web Worker yet), so the page can stall briefly during processing.
- **No accuracy validation**: there's currently no way to overlay ground-truth points to sanity-check the georeferencing offset against real-world measurements.

## 🗺️ Roadmap

- Offload inference to a Web Worker
- Click-through from a map marker to its source video frame/timestamp
- Batch/multi-video processing
- Persist results locally (IndexedDB) so a page refresh doesn't lose detections
- Gimbal pitch/roll compensation for non-nadir footage

## 👨‍💻 Author

**Sannidhi Math**  
BTech Mechatronics Engineering, MIT Manipal  
[GitHub](https://github.com/Sannidhi20040) | [LinkedIn](https://www.linkedin.com/in/sannidhi-math-2b1aa3202)

## 📝 License

MIT License - see [LICENSE](LICENSE) file for details
