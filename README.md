# 🚁 Drone Georeferencing System

**🌐 [Live Demo](https://sannidhi20040.github.io/drone-georeferencing/)** | **📂 [GitHub](https://github.com/Sannidhi20040/drone-georeferencing)**

Browser-based vehicle and pedestrian detection from drone footage, with GPS georeferencing and interactive mapping. Everything runs client-side: no video is uploaded anywhere.

![System Demo](https://img.shields.io/badge/Status-Live-brightgreen)
![ML](https://img.shields.io/badge/ML-YOLOv8-blue)
![Map](https://img.shields.io/badge/Map-Leaflet.js-green)

## 🎯 Features

- **YOLOv8 Object Detection**: Aerial-trained model (VisDrone-style classes: small vehicle, large vehicle, pedestrian) running in the browser via ONNX Runtime Web. Frames are letterboxed (aspect ratio preserved, gray padding) to match how YOLOv8 is trained.
- **Pixel-to-GPS Transformation**: Maps detections to coordinates from camera FOV, altitude, heading and GPS position. This is a geometric estimate that has **not yet been validated against ground truth** (see limitations).
- **Flight Log Integration**: Parses CSV telemetry, sorts it, drops rows with missing/non-numeric values, and interpolates linearly between samples (heading along the shorter arc).
- **Configurable Camera & Timing**: Diagonal FOV, video frame rate, sampling interval and a video-to-log time offset are all adjustable in the UI.
- **Flight Path Visualization**: The drone's GPS track is drawn as soon as a flight log is loaded.
- **Detection Clustering**: Merges repeated sightings of the same object across frames using spatial proximity and a running weighted-average centroid.
- **Confidence-Coded Markers**: Marker color shows confidence; marker size shows how many times the object was sighted.
- **Simulation-Mode Safeguard**: If the model cannot load or run, the app shows a red "SIMULATION MODE" banner, and exported detections carry a `simulated` flag, so random placeholder detections cannot pass as real ones.
- **Export Tools**: GeoJSON and CSV export for GIS applications.

## 📊 Model Performance

| Metric | Value |
|--------|-------|
| mAP50 | 0.583 |
| mAP50-95 | 0.366 |
| Small Vehicle (mAP50) | 0.764 |
| Large Vehicle (mAP50) | 0.713 |
| Pedestrian (mAP50) | 0.272 |

## 🚀 Quick Start

```bash
git clone https://github.com/Sannidhi20040/drone-georeferencing.git
cd drone-georeferencing
npm install
npm run dev
```

The app is served under a base path, so open **http://localhost:5173/drone-georeferencing/** (the root URL will not load it).

## 🕹️ Using the App

1. Upload a drone video and its flight log (CSV with `timestamp, latitude, longitude, altitude, heading`; DJI-style `OSD.*` column names are also accepted).
2. Set the camera and timing options to match your footage:
   - **Camera diagonal FOV**: the camera's published diagonal field of view (default 84°).
   - **Video frame rate**: used to label frame numbers (default 30).
   - **Sample one frame every (s)**: how often a frame is analyzed (default 2 s). Sampling less often is faster but gives fewer repeat sightings of each object, so more real objects fall below *Min Detections to Show* and are dropped.
   - **Log time offset (s)**: aligns the clocks. Telemetry time = video time + offset. Use a positive value if the flight log started recording before the video did. There is no automatic synchronization; a visible event (takeoff, a sharp turn) can help you work out the offset.
3. Press **Process Video**, then review the map and export GeoJSON/CSV.

### Sample data

`test_data/` contains two flight logs, `sample_flight_log.csv` and `vidhana_soudha_flight_log.csv`. **Both are synthetic**: 10 hand-written rows with smoothly increasing values, with Bangalore-area coordinates as placeholders. They are not recordings of a real flight, and **no sample video is included** in the repository. They exist to exercise the pipeline, not to measure accuracy.

## 🧪 Testing

Unit tests cover the georeferencing math (FOV split, pixel-to-GPS projection), flight-log parsing and interpolation, letterbox coordinate mapping, and export formats:

```bash
npm test
```

The model-loading and inference path was checked manually in a browser (dev server and production build) using a synthetic video; that confirms the model loads and runs but says nothing about detection accuracy on real footage.

## 🛠️ Tech Stack

- **Frontend**: Vanilla JavaScript, Vite, Leaflet.js
- **ML/CV**: YOLOv8, ONNX Runtime Web
- **Geospatial**: Custom FOV transformation, Turf.js (rhumb destination), PapaParse
- **Testing**: Vitest

## ⚠️ Known Limitations

- **Not validated on real data**: the pipeline has been built and tested on synthetic flight logs and synthetic frames. There is no measured georeferencing error against surveyed ground truth, and no accuracy claim is made for the GPS positions.
- **Nadir-only georeferencing**: pixel-to-GPS math assumes a level, straight-down camera over flat ground. It does not compensate for gimbal pitch/roll or terrain elevation, so results will be off for angled footage or hilly terrain.
- **Heading source**: bearing is computed from the drone's flight-log heading, not gimbal yaw. If the camera can pan independently of the airframe, detections will be misplaced.
- **Manual time synchronization**: the video and flight log are aligned only by the offset you enter; a wrong offset directly shifts every detection.
- **Sparse sampling vs. filtering**: detections must be sighted in several sampled frames to be shown, which trades false positives against missed objects that are only visible briefly.
- **Weak pedestrian detection**: the model's pedestrian mAP50 (0.272) is much lower than for vehicles.
- **Clustering is not tracking**: sightings are merged by proximity, not tracked, so two distinct nearby objects can be merged and a fast-moving one can be counted several times.
- **Frame extraction speed**: frames are extracted via HTML `<video>` seeking, which is slow for long videos.
- **Main-thread inference**: inference runs on the UI thread (no Web Worker), so the page can stall briefly while processing.

## 🗺️ Roadmap

- Validate against surveyed ground-truth points and report georeferencing error
- Offload inference to a Web Worker
- Click-through from a map marker to its source video frame/timestamp
- Batch/multi-video processing
- Persist results locally (IndexedDB) so a page refresh doesn't lose detections
- Gimbal pitch/roll compensation for non-nadir footage
- A proper multi-object tracker (e.g. SORT) in place of proximity clustering

## 👨‍💻 Author

**Sannidhi Math**  
BTech Mechatronics Engineering, MIT Manipal  
[GitHub](https://github.com/Sannidhi20040) | [LinkedIn](https://www.linkedin.com/in/sannidhi-math-2b1aa3202)

## 📝 License

MIT License
