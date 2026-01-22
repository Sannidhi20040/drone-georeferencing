# 🚁 Drone Georeferencing System

**🌐 [Live Demo](https://sannidhi20040.github.io/drone-georeferencing/)** | **📂 [GitHub](https://github.com/Sannidhi20040/drone-georeferencing)**

Real-time vehicle and pedestrian detection from drone footage with GPS georeferencing and interactive mapping.

![System Demo](https://img.shields.io/badge/Status-Live-brightgreen)
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

## 🛠️ Tech Stack

- **Frontend**: Vanilla JavaScript, Vite, Leaflet.js
- **ML/CV**: YOLOv8, ONNX Runtime Web
- **Geospatial**: Custom FOV transformation, PapaParse

## 👨‍💻 Author

**Sannidhi Math**  
BTech Mechatronics Engineering, MIT Manipal  
[GitHub](https://github.com/Sannidhi20040) | [LinkedIn](https://www.linkedin.com/in/sannidhi-math-2b1aa3202)

## 📝 License

MIT License - see [LICENSE](LICENSE) file for details
