# Validating on AU-AIR (public drone data)

Tools for measuring this project's georeferencing and detector on real footage from the
[AU-AIR dataset](https://bozcani.github.io/AU-AIR-dataset.html) (Parrot Bebop 2, traffic at an
intersection in Aarhus, 10-30 m altitude, per-frame GPS/altitude/attitude and labelled boxes).

The dataset is **not in this repository** (2.3 GB; `data_check/` is git-ignored). Download it from the
dataset page and place `annotations.json` and `images/` in `data_check/`. The annotation file lists
*Attribution-NonCommercial* licences; check the dataset page for the exact terms before redistributing
anything, and cite the AU-AIR paper given there.

## What the data is (checked, not assumed)

- 8 clips, 32,823 frames, 1920x1080, ~5 frames/s, every frame has an image and metadata.
- `altitude` is in **millimetres**; `angle_*` are **radians**.
- **Only clip `20190829091111` (2,592 frames) looks straight down** (a car park). The other seven are
  oblique (roughly 45-60 degrees below the horizon, often with sky visible) and the camera tilt is **not logged**, so
  they cannot be georeferenced with this pipeline's pitch handling without estimating the pitch.
- Frame numbering has gaps (14 in clip 1, up to 44 s). The drone really moves across them, so GPS
  "jumps" of up to 9 m between neighbouring *files* are movement, not glitches. Within a continuous
  run the largest raw GPS step is about 2 m.
- Camera FOV and the yaw reference are not documented.

## Workflow

```bash
# 1. clean per-frame table (mm -> m, radians -> degrees, per-run GPS smoothing)
node scripts/au-air/prepare.mjs

# 2. pick landmarks: run the dev server and open the picker
npm run dev
#    http://localhost:5173/drone-georeferencing/scripts/au-air/picker.html
#    Create landmarks, click the same ground point in a frame, paste the satellite
#    "lat, lon" (Google Maps: right-click the point). Export, then move the file to
#    data_check/derived/landmarks.json

# 4. does error grow with drone tilt? (needs landmarks picked in frames with different roll/pitch)
node scripts/au-air/per_frame.mjs --heading-fit

# 3. score
node scripts/au-air/evaluate.mjs --calibrate L1,L2 --heading-fit   # calibrate on a pair, test on the rest
node scripts/au-air/evaluate.mjs --cv --heading-fit                # leave-pair-out cross-validation
```

**Choosing landmarks:** sharp, flat, permanent points such as lane-marking ends and kerb corners.
Avoid cars (they move) and anything tall (its top is not where its base is). Check that the satellite
image still shows the same markings as in 2019. Pick **several landmarks in the same frame**; the
FOV calibration and the relative metric both need pairs seen together. Aim for 6-10 landmarks over a
few frames.

## What the numbers mean

- **Distance between landmark pairs (same frame, in %):** the most trustworthy number. Two landmarks
  in one frame share the drone's GPS error and heading error, so those cancel, leaving the geometry
  (scale/FOV, altitude, projection).
- **Absolute position error (m):** predicted vs satellite position. It **includes the drone's own
  GPS error and the satellite image's offset**, which are likely metres each (not measured here), so it is a ceiling on
  accuracy, not a measurement of the geometry alone.
- **FOV is fitted** (on pair distances) and, with `--heading-fit`, so is a constant heading offset (on
  absolute error; this absorbs some GPS bias, so treat it as approximate). Only the **held-out** landmarks
  count as accuracy; the in-sample block is printed for transparency and labelled as optimistic.
  Because altitude and FOV both scale the image on the ground, the fitted FOV is really an effective
  scale: it will absorb any consistent altitude bias.
- The pipeline assumes flat ground and ignores the drone's body roll/pitch (the Bebop stabilises
  its video digitally; this is an assumption, not checked). Within clip 1 the body tilt is
  mostly within +-8 degrees but reaches +-24.

The evaluator was checked on synthetic landmarks built from real poses: it recovers a planted FOV
and heading offset exactly, scores zero held-out error with no noise, and, with a simulated per-frame GPS
bias of 1.5-3.5 m, reports about 2 m absolute error but 0% pair-distance error (`lib.test.js` covers the
same logic).

## Results so far

**No landmark-based accuracy has been measured yet.** What exists (reproducible, clip 1 unless noted):

| Check | Result | Caveats |
|---|---|---|
| Detector, near-straight-down clip, 150 frames, conf 0.5 (`detector_eval.py`) | cars: precision 0.81, recall 0.92 (IoU 0.5). People: 0.84 / 0.52 (centre-in-box; 0.40 / 0.25 by IoU) | One hovering scene, so frames are highly correlated. The clip contains only 1 large vehicle, so that class is untested. |
| Detector, all 8 clips, 25 frames each, conf 0.5 | cars: precision 0.26, recall 0.43 (IoU), 0.47 / 0.77 (centre-in-box) | Mostly oblique views, which the model was not trained for. Varies with the random sample. |
| Self-consistency of georeferenced ground-truth boxes (`self_consistency.mjs`) | same parked car seen 10 s apart lands a median 0.7 m apart at FOV 55-65, about 73% of cars matched within 4 m | Relative repeatability only. FOV and yaw convention were chosen on this same data, the 4 m radius biases toward small numbers, and it hardly constrains FOV. `heading = +yaw` was the most consistent convention. |

## Files

| File | Purpose |
|---|---|
| `prepare.mjs` | Annotations -> `data_check/derived/<clip>.json` and a flight-log CSV in this app's format |
| `picker.html` | Click landmarks, enter satellite coordinates, export `landmarks.json` |
| `evaluate.mjs` | Calibrate FOV/heading and report held-out absolute and pair-distance error |
| `per_frame.mjs` | Per-frame offset and scatter next to the drone's tilt, to test whether error grows with tilt |
| `self_consistency.mjs` | Repeatability of georeferenced boxes across frames (no satellite needed) |
| `detector_eval.py` | Detector precision/recall against the dataset's boxes (needs `numpy pillow onnxruntime`) |
| `lib.mjs`, `lib.test.js` | Shared logic and its tests (run with `npm test`) |
