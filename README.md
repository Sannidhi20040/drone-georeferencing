# 🚁 Drone Georeferencing System

**🌐 [Live Demo](https://sannidhi20040.github.io/drone-georeferencing/)** | **📂 [GitHub](https://github.com/Sannidhi20040/drone-georeferencing)**

Browser-based vehicle and pedestrian detection from drone footage, with GPS georeferencing and interactive mapping. Everything runs client-side: no video is uploaded anywhere.

![System Demo](https://img.shields.io/badge/Status-Live-brightgreen)
![ML](https://img.shields.io/badge/ML-YOLOv8-blue)
![Map](https://img.shields.io/badge/Map-Leaflet.js-green)

## 🎯 Features

- **YOLOv8 Object Detection**: Aerial-trained model (VisDrone-style classes: small vehicle, large vehicle, pedestrian) running in the browser via ONNX Runtime Web. Frames are letterboxed (aspect ratio preserved, gray padding) to match how YOLOv8 is trained.
- **Pixel-to-GPS Transformation**: Casts each pixel's viewing ray onto a flat ground plane using the camera FOV, height above ground, heading, GPS position and **gimbal pitch** (so tilted footage works, not just straight-down). This is a geometric estimate that has **not yet been measured against real ground truth** (see limitations).
- **Flight Log Integration**: Parses CSV telemetry, sorts it, drops rows with missing/non-numeric values, and interpolates linearly between samples (heading along the shorter arc).
- **Configurable Camera & Timing**: Diagonal FOV, video frame rate, sampling interval and a video-to-log time offset are all adjustable in the UI.
- **Flight Path Visualization**: The drone's GPS track is drawn as soon as a flight log is loaded.
- **Stationary or Moving Objects**: *Stationary* mode merges repeated sightings by proximity (running weighted-average centroid). *Moving* mode runs a lightweight SORT-style tracker (per-class constant-velocity prediction, nearest-first one-to-one matching) that reports a track id, speed and path per object.
- **Accuracy Validation Tool**: Upload surveyed ground-truth points and the app reports matched/missed/extra detections, precision/recall, and mean/median/RMSE/max position error in meters.
- **Altitude Handling**: Treat the log altitude as height above ground, or as above-sea-level (subtract the takeoff sample), plus a manual offset.
- **Confidence-Coded Markers**: Marker color shows confidence; marker size shows how many times the object was sighted.
- **Simulation-Mode Safeguard**: If the model cannot load or run, the app shows a red "SIMULATION MODE" banner, and exported detections carry a `simulated` flag, so random placeholder detections cannot pass as real ones.
- **Export Tools**: GeoJSON and CSV export for GIS applications. Exports contain exactly the detections drawn on the map, including track id/speed for tracked objects and the `simulated` flag.
- **Map Legend & Cancel**: A legend explains marker colors and sizes; long runs can be cancelled.

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
   - **Gimbal pitch (°)**: used when the log has no pitch column (0 = horizon, −90 = straight down). A log column named `gimbalPitch`, `gimbal_pitch`, `gimbal.pitch` or `OSD.gimbalPitch` takes precedence and is interpolated like the other telemetry. Pitch is assumed to be measured from the horizon; check this against your drone's log format.
   - **Log time offset (s)**: aligns the clocks. Telemetry time = video time + offset. Use a positive value if the flight log started recording before the video did. There is no automatic synchronization; a visible event (takeoff, a sharp turn) can help you work out the offset.
3. Choose how altitude and objects are interpreted:
   - **Log altitude is…**: *height above ground* (use as-is) or *above sea level* (subtract the first sample, which assumes takeoff from ground level), plus an **extra offset** for rooftop takeoffs or raised terrain. Positions need height above ground, so a wrong choice here scales every distance.
   - **Objects are…**: *stationary* (merge nearby sightings) or *moving* (track between frames). Tracking needs dense sampling (about 0.5 s or less); with sparse sampling, nearby vehicles can swap identities.
4. Press **Process Video**, then review the map and export GeoJSON/CSV.

### Validating accuracy

To measure real georeferencing error you need a flight whose **video and log are synchronized**, and a few objects (cars, markers on the ground) whose true positions you surveyed:

1. Write the surveyed positions to a CSV: `latitude,longitude` and optionally `class` (`small-vehicle`, `large-vehicle`, `human`).
2. Upload it as **Ground Truth** and process the flight.
3. The sidebar reports matched/missed/extra counts, precision/recall, and mean/median/RMSE/max error in meters, and the map draws the ground-truth points and the match lines. Detections within the **match radius** (default 10 m) of a ground-truth point are matched one-to-one, nearest first.

The reported error combines detector localization error and georeferencing error. **No such measurement has been made yet**; this tool exists so one can be.

### Testing on public drone data

`scripts/au-air/` contains tools for scoring the detector and the georeferencing on the public AU-AIR dataset: a landmark picker, a calibrate-then-test evaluator, and a detector evaluation. See [scripts/au-air/README.md](scripts/au-air/README.md). **No landmark-based accuracy has been measured yet**; that file records exactly which checks have been run and what they do and do not show.

### Sample data

`test_data/` contains two flight logs, `sample_flight_log.csv` and `vidhana_soudha_flight_log.csv`. **Both are synthetic**: 10 hand-written rows with smoothly increasing values, with Bangalore-area coordinates as placeholders. They are not recordings of a real flight, and **no sample video is included** in the repository. They exist to exercise the pipeline, not to measure accuracy.

## 🧪 Testing

Unit tests cover the georeferencing math (FOV split, nadir regression values, tilted-camera geometry against closed-form answers), flight-log parsing and interpolation, clustering, the tracker, ground-truth validation, altitude handling, letterbox mapping and export formats. GitHub Actions runs them, plus a production build, on every push:

```bash
npm test
```

The model-loading and inference path was checked manually in a browser (dev server and production build) using a synthetic video; that confirms the model loads and runs but says nothing about detection accuracy on real footage.

## 🚢 Deployment

`.github/workflows/deploy.yml` tests, builds and publishes `dist` to the `gh-pages` branch whenever `main` changes, so the live site tracks `main`. `npm run deploy` still publishes manually from the working tree.

## 🛠️ Tech Stack

- **Frontend**: Vanilla JavaScript, Vite, Leaflet.js
- **ML/CV**: YOLOv8, ONNX Runtime Web
- **Geospatial**: Custom FOV transformation, Turf.js (rhumb destination), PapaParse
- **Testing/CI**: Vitest, GitHub Actions

## ⚠️ Known Limitations

- **Not validated on real data**: the pipeline has been built and tested on synthetic flight logs and synthetic frames. There is no measured georeferencing error against surveyed ground truth, and no accuracy claim is made for the GPS positions.
- **Flat ground, no roll**: positions assume a flat ground plane at the given height above ground. Terrain elevation, gimbal roll, drone body tilt and lens distortion are not modelled, and rays within 5° of the horizon are discarded as unreliable. Angled footage works only if the pitch is known.
- **Heading source**: bearing is computed from the drone's flight-log heading, not gimbal yaw. If the camera can pan independently of the airframe, detections will be misplaced.
- **Manual time synchronization**: the video and flight log are aligned only by the offset you enter; a wrong offset directly shifts every detection.
- **Sparse sampling vs. filtering**: detections must be sighted in several sampled frames to be shown, which trades false positives against missed objects that are only visible briefly.
- **Weak pedestrian detection**: the model's pedestrian mAP50 (0.272) is much lower than for vehicles.
- **Tracking is simple**: the tracker has no appearance model and uses fixed per-class speed limits, so identities can swap in dense traffic or with sparse sampling. Stationary mode merges by proximity only and counts a moving object several times.
- **Model file in git history**: the 43 MB model is committed, so the repository is large to clone. It is served directly from GitHub Pages, so Git LFS (which Pages does not serve) is deliberately not used.
- **Dev-tooling advisories**: `npm audit` reports vulnerabilities in the Vite dev server and the `gh-pages` helper. They affect development tooling, not the deployed site, and fixing them needs a Vite major upgrade.
- **Frame extraction speed**: frames are extracted via HTML `<video>` seeking, which is slow for long videos.
- **Main-thread inference**: inference runs on the UI thread (no Web Worker), so the page can stall briefly while processing.

## 🗺️ Roadmap

- Run the validation tool on a real, synchronized flight and publish the measured error
- Offload inference to a Web Worker
- Click-through from a map marker to its source video frame/timestamp
- Batch/multi-video processing
- Persist results locally (IndexedDB) so a page refresh doesn't lose detections
- Gimbal roll and terrain-elevation (DEM) compensation
- Automatic video/log synchronization

## 👨‍💻 Author

**Sannidhi Math**  
BTech Mechatronics Engineering, MIT Manipal  
[GitHub](https://github.com/Sannidhi20040) | [LinkedIn](https://www.linkedin.com/in/sannidhi-math-2b1aa3202)

## 📝 License

MIT License - see [LICENSE](LICENSE).
