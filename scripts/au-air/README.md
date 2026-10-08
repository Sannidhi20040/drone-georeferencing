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

### Landmark-based pilot (one car park, 7 landmarks, 4 frames)

Setup: clip `20190829091111`. Landmarks are permanent ground features (kerb corners, lane-dash ends, a
drain grate, a manhole cover) whose coordinates were read by hand from Google Maps satellite imagery
(newer than the 2019 footage, so any feature that changed adds error). They were observed in 4 frames
with drone body tilt of 1.5, 3, 25 and 26 degrees. Landmark files are in `results/landmarks_clip1*.json`
and every output below is regenerated in `results/pilot_outputs.txt`. Method: leave-pair-out
cross-validation (calibrate FOV and a heading offset on one landmark pair, score the others).

| | 4 landmarks, all within 9 m (2 frames) | all 7 landmarks, up to 18 m apart (4 frames) |
|---|---|---|
| Distance between landmark pairs in one frame (median of fold medians, range) | **2.6%** (2.1-17%) | **12%** (5.5-37%) |
| Absolute position error | 1.4 m (1.2-1.8) | 2.7 m (2.1-9.0) |
| Fitted FOV across folds | 84 deg (77.5-92) | 81 deg (71-94) |

Both columns are reported because they measure different things. The 4-landmark figure is limited by
landmark spacing: with landmarks 3-9 m apart, picking noise of only 0.1-0.2 m would already show 3-6%
for a perfect pipeline (simulated), so 2.6% cannot be resolved from noise. The 7-landmark figure
includes landmarks 11-18 m away, where small per-frame scale and rotation errors have a long lever arm.

What the error is made of (`error_geometry.mjs`, `per_frame.mjs`; geometry fitted on the 4 near landmarks):

- **Within a frame the layout is right to 0.2-0.4 m.** After a per-frame scale, rotation and shift, the
  residual is 0.21-0.37 m in every frame, including points 600-850 px from the image centre. There is
  no lens-distortion signature at that level.
- **Per-frame scale and rotation vary.** Scale (predicted / satellite) was 0.88 and 0.89 at tilt 1.5 and 3
  degrees but 1.10 and 1.09 at 26 and 25 degrees; rotation was +2.5, +4.6, -1.3 and -2.8 degrees. Errors of
  +-10% in scale and +-3-5 degrees in rotation, multiplied by range, give the 1-3 m errors on the far
  landmarks. Possible causes, not separated by this data: altitude error, an effective-FOV change under the
  camera's digital stabilisation (scale tracks tilt in these four frames), and yaw (compass) error.
- **Per-frame position offset is 0.6-3.9 m** (drone GPS and/or residual tilt).
- **Tilt is mostly compensated.** At about 25 degrees of tilt, positions shifted 2.7-3.9 m, versus roughly
  9-10 m (height x tan(tilt)) if the camera were rigidly fixed to the body.
- **No sign of a mis-identified landmark.** With a per-frame fit on the other six landmarks, each held-out
  landmark lands within 0.2-1.0 m of its satellite coordinate (largest: L6, 1.0 m).

Limits: one car park, one flight, four frames and seven landmarks picked by one person; the satellite
coordinates have their own error; per-frame fits use 4-14 points for 4 parameters, so every per-frame
statement above is suggestive, not established. This says nothing about other scenes, other drones or
oblique footage.

### Other checks (reproducible, clip 1 unless noted)

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
| `error_geometry.mjs` | Radial vs tangential error, plus a per-frame scale + rotation fit, to separate scale/distortion from yaw error |
| `self_consistency.mjs` | Repeatability of georeferenced boxes across frames (no satellite needed) |
| `detector_eval.py` | Detector precision/recall against the dataset's boxes (needs `numpy pillow onnxruntime`) |
| `results/` | The pilot's landmark files and every output, regenerated in `pilot_outputs.txt` |
| `lib.mjs`, `lib.test.js` | Shared logic and its tests (run with `npm test`) |
