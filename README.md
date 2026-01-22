# 🚁 Drone Georeferencing System

Real-time vehicle and pedestrian detection from drone footage with GPS georeferencing and interactive mapping.

![System Demo](https://img.shields.io/badge/Status-Production%20Ready-success)
![ML](https://img.shields.io/badge/ML-YOLOv8-blue)
![Map](https://img.shields.io/badge/Map-Leaflet.js-green)

## 🎯 Features

- **YOLOv8 Object Detection**: Trained on 9,287 aerial images (VisDrone dataset)
- **Pixel-to-GPS Transformation**: Accurate coordinate mapping using camera FOV calculations
- **Flight Log Integration**: Parse and sync CSV telemetry data
- **Detection Clustering**: Merge duplicate detections using spatial proximity
- **Interactive Mapping**: Real-time visualization with OpenStreetMap
- **Export Tools**: GeoJSON and CSV export for GIS applications

## 📊 Model Performance

- **mAP50**: 0.583
- **mAP50-95**: 0.366

## 🚀 Quick Start

\`\`\`bash
git clone https://github.com/Sannidhi20040/drone-georeferencing.git
cd drone-georeferencing
npm install
npm run dev
\`\`\`

## 🛠️ Tech Stack

- Vanilla JavaScript + Vite
- YOLOv8 + ONNX Runtime
- Leaflet.js + OpenStreetMap
- Custom GPS transformation algorithms

## 👨‍💻 Author

Sannidhi Math - BTech Mechatronics Engineering, MIT Manipal
