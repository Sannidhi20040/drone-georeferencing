## a) Bootstrap, 80 deg camera setting: 30 frames resampled with replacement, 2000 resamples, seed 20261025

Point estimate [95% percentile interval].

| Model | Median % error | Slope (m of depth per m of altitude) | Pearson r |
|---|---|---|---|
| DA3 (earlier run) | -56.4% [-60.0, -50.4] | 0.13 [-0.01, 0.28] | 0.34 [-0.03, 0.66] |
| UniDepthV2 | -9.9% [-13.8, -2.5] | 1.01 [0.58, 1.37] | 0.59 [0.31, 0.82] |
| MoGe-2 | -23.0% [-25.6, -17.7] | 0.84 [0.70, 0.98] | 0.88 [0.77, 0.95] |
| MoGe2-Aerial | 5.0% [1.3, 8.2] | 1.22 [0.79, 1.59] | 0.76 [0.54, 0.88] |

## b) The 8 frames with no labelled vehicle (vs the other 22)

Time = frame number / 5 fps, seconds from the start of the clip (frame numbering has a few gaps, so approximate); the clip's last frame is 3710 (about 742 s).

| Frame | Logged altitude (m) | Time into clip (s) | Position in clip |
|---|---|---|---|
| 256 | 15.5 | 51 | 7% |
| 1057 | 19.4 | 211 | 28% |
| 1124 | 19.4 | 225 | 30% |
| 1137 | 19.3 | 227 | 31% |
| 1163 | 19.5 | 233 | 31% |
| 2198 | 12.8 | 440 | 59% |
| 3449 | 23.6 | 690 | 93% |
| 3643 | 29.2 | 729 | 98% |

Median altitude: no-vehicle frames 19.4 m, other frames 21.2 m. Mann-Whitney U = 53, two-sided p = 0.107.
Bunching: the most no-vehicle frames within any 150-frame window (30 s) is 4; with the 8 labels shuffled over the 30 frames (10,000 permutations, seed 20261025) a stretch that dense or denser occurs with probability 0.027. Gaps between consecutive no-vehicle frames: 801, 67, 13, 26, 1035, 1251, 194 frames.

## c) Dropping the 3 lowest- and 3 highest-altitude frames (24 left; altitudes 17.5-27.6 m)

Dropped: lowest [2198, 179, 256] (12.8, 15.2, 15.5 m), highest [511, 3643, 3629] (27.9, 29.2, 29.4 m).

| Model | Slope, all 30 | Slope, 24 kept | Pearson r, all 30 | Pearson r, 24 kept |
|---|---|---|---|---|
| DA3 (earlier run) | 0.13 | 0.15 | 0.34 | 0.29 |
| UniDepthV2 | 1.01 | 0.66 | 0.59 | 0.30 |
| MoGe-2 | 0.84 | 0.75 | 0.88 | 0.75 |
| MoGe2-Aerial | 1.22 | 0.80 | 0.76 | 0.48 |

## d) Scene content vs altitude vs flight segment (added after a-c; exploratory)

Empty frames: the stretch of 4 frames [1057, 1124, 1137, 1163] (one hover at about 19.4 m, treat as one segment) and 4 isolated frames [256, 2198, 3449, 3643] (altitudes 15.5, 12.8, 23.6, 29.2 m, different parts of the flight). Altitude-matched frames with vehicles (19.0-20.0 m): [1831, 1944, 2055, 2087, 2135] (n = 5). Median % error per model:

| Model | All 8 empty | 4 in the one stretch | 4 isolated | Vehicle frames, 19-20 m | All 22 vehicle frames | Mann-Whitney p, empty vs vehicle (% error, 8 vs 22) |
|---|---|---|---|---|---|---|
| DA3 (earlier run) | -61% | -61% | -64% | -49% | -53% | 0.024 |
| UniDepthV2 | +48% | +60% | +30% | -14% | -13% | 0.000 |
| MoGe-2 | -9% | -8% | -17% | -25% | -24% | 0.001 |
| MoGe2-Aerial | +44% | +51% | +32% | +1% | +2% | 0.000 |

Per-frame % error on the 8 empty frames:

| Frame | Altitude (m) | DA3 (earlier run) | UniDepthV2 | MoGe-2 | MoGe2-Aerial |
|---|---|---|---|---|---|
| 256 | 15.5 | -56% | +32% | -7% | +33% |
| 1057 | 19.4 | -61% | +57% | -10% | +50% |
| 1124 | 19.4 | -62% | +72% | -2% | +53% |
| 1137 | 19.3 | -57% | +51% | -6% | +48% |
| 1163 | 19.5 | -64% | +62% | -9% | +52% |
| 2198 | 12.8 | -55% | -10% | -27% | +2% |
| 3449 | 23.6 | -72% | +46% | -21% | +30% |
| 3643 | 29.2 | -73% | +27% | -14% | +40% |
