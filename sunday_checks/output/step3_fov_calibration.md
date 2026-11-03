## a) Diagonal FOV that makes the adjacent-bay distance 2.905 m

1. Satellite bay width = 17.43 m / 6 = 2.9050 m. Pipeline adjacent-bay distance (from the brief) = 3.33 m at 80 deg.
2. Focal length from the diagonal: f = (hypot(1920, 1080) / 2) / tan(FOV / 2). hypot = 2202.91 px, so f(80 deg) = 1101.45 / tan(40 deg) = 1312.66 px.
3. Distances scale as 1/f, so the distance ratio must be 2.9050 / 3.33 = 0.87237 and the focal length must grow by 1 / 0.87237 = 1.14630: f_new = 1312.66 x 1.14630 = 1504.70 px.
4. FOV_new = 2 atan((hypot / 2) / f_new) = 2 atan(1101.45 / 1504.70) = **72.41 deg diagonal** (horizontal 65.08 deg; the 80 deg setting is 72.36 deg horizontal).
Note the two 72.4 values are a coincidence of numbers: 72.4 deg is the DIAGONAL field of view implied by the bays, and also (almost exactly) the HORIZONTAL field of view of the 80 deg diagonal setting.
Step 3b checks the 1/f shortcut against the real pixel-to-GPS geometry.

## b) Corrected ground truth for the 24 distance questions

Recomputed with pixel_to_gps at 80 deg: matches the saved truths to within 0.0047 m (saved values are rounded to 0.01 m, so up to 0.005 m). New / old distance ratio across all 24 questions: min 0.87237, max 0.87237 (expected 0.87237 for every one, because the camera looks straight down).

| Question | Old truth (m) | Corrected truth (m) |
|---|---|---|
| f1619-met-AB | 17.35 | 15.13 |
| f1619-met-BD | 10.08 | 8.80 |
| f1706-met-AB | 3.29 | 2.87 |
| f1706-met-AC | 10.23 | 8.92 |
| f1809-met-AB | 3.33 | 2.90 |
| f1809-met-BC | 17.33 | 15.12 |
| f1949-met-AB | 10.58 | 9.23 |
| f1949-met-AC | 3.38 | 2.95 |
| f2071-met-AC | 10.75 | 9.38 |
| f2071-met-BC | 13.51 | 11.79 |
| f2340-met-AB | 3.15 | 2.75 |
| f2340-met-BC | 13.69 | 11.95 |
| f2639-met-AD | 19.30 | 16.84 |
| f2639-met-BD | 14.51 | 12.66 |
| f2713-met-AB | 3.33 | 2.90 |
| f2713-met-BD | 3.59 | 3.13 |
| f2784-met-AD | 3.87 | 3.38 |
| f2784-met-BC | 3.70 | 3.23 |
| f3061-met-BC | 3.51 | 3.07 |
| f3061-met-CD | 7.08 | 6.17 |
| f483-met-AB | 14.24 | 12.42 |
| f483-met-BC | 37.16 | 32.42 |
| f545-met-AC | 22.99 | 20.05 |
| f545-met-BC | 9.05 | 7.90 |

Spot check, frame 2713 A-B (adjacent bays): 3.33 m old, 2.90 m corrected (satellite 2.905 m).

Comparison questions (30): the nearer option cannot change (every distance is multiplied by the same factor), so the truths and accuracies are unchanged. With corrected distances 29 of 30 would still satisfy the original 'differ by >= 30 % and >= 3 m' rule (the 3 m part gets harder when distances shrink); no comparison question was changed or re-scored.

## c) Each model's distance error, old vs corrected truth

| Model | Median abs. error, old | Median abs. error, corrected | Median signed error, old | Median signed error, corrected | Median rotation spread (old = corrected) |
|---|---|---|---|---|---|
| Haiku 5.5 | 15.4% | 6.4% | -15.4% | -3.0% | 6.8% |
| Sonnet 4.6 | 61.4% | 85.0% | +61.4% | +85.0% | 69.0% |
| Opus 4.6 | 36.0% | 55.9% | +36.0% | +55.9% | 50.0% |
| Haiku 4.5 | 37.3% | 41.5% | -9.7% | +3.5% | 96.7% |
| Qwen2.5-VL 3B | 42.5% | 49.0% | +10.5% | +26.6% | 91.7% |

The rotation spread depends only on the models' own answers, so it cannot change; it is recomputed here from the answers and equals the step 1 value.

**Circularity:** this calibration uses the bay width of the same car park the corrected truths are applied to, so it is a correction to the scale, not an independent check of the pipeline. It also assumes the brief's 3.33 m (pipeline median adjacent-bay distance) and satellite 2.905 m are right, and that one scale factor applies to every frame (the earlier landmark pilot found per-frame scale errors of about +-10 %).
