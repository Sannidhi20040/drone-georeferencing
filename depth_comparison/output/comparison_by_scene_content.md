Post hoc, not pre-specified: the same statistics split by whether the frame contains any labelled vehicle.
Small groups (see n): read the medians, not the p-values.

| Model | Setting | Frames | n | Median % error | Slope (m/m) | Pearson r (p) |
|---|---|---|---|---|---|---|
| DA3-Metric-Large (earlier run) | camera given, 80 deg diag (72.4 deg H) | no labelled vehicle in frame | 8 | -61.1 | 0.09 | 0.56 (0.152) |
| DA3-Metric-Large (earlier run) | camera given, 80 deg diag (72.4 deg H) | vehicles in frame | 22 | -53.0 | 0.04 | 0.14 (0.520) |
| UniDepthV2 (ViT-L) | camera given, 80 deg diag (72.4 deg H) | no labelled vehicle in frame | 8 | +48.5 | 1.47 | 0.86 (0.006) |
| UniDepthV2 (ViT-L) | camera given, 80 deg diag (72.4 deg H) | vehicles in frame | 22 | -13.4 | 1.26 | 0.97 (0.000) |
| UniDepthV2 (ViT-L) | no camera (model guesses) | no labelled vehicle in frame | 8 | +42.3 | 1.38 | 0.82 (0.013) |
| UniDepthV2 (ViT-L) | no camera (model guesses) | vehicles in frame | 22 | -19.4 | 1.09 | 0.96 (0.000) |
| MoGe-2 (ViT-L normal) | camera given, 80 deg diag (72.4 deg H) | no labelled vehicle in frame | 8 | -9.3 | 0.86 | 0.95 (0.000) |
| MoGe-2 (ViT-L normal) | camera given, 80 deg diag (72.4 deg H) | vehicles in frame | 22 | -23.7 | 0.97 | 0.95 (0.000) |
| MoGe-2 (ViT-L normal) | no camera (model guesses) | no labelled vehicle in frame | 8 | -19.4 | 0.76 | 0.94 (0.000) |
| MoGe-2 (ViT-L normal) | no camera (model guesses) | vehicles in frame | 22 | -31.7 | 0.80 | 0.93 (0.000) |
| MoGe2-Aerial (LoRA) | camera given, 80 deg diag (72.4 deg H) | no labelled vehicle in frame | 8 | +44.3 | 1.56 | 0.95 (0.000) |
| MoGe2-Aerial (LoRA) | camera given, 80 deg diag (72.4 deg H) | vehicles in frame | 22 | +2.5 | 1.40 | 0.92 (0.000) |
| MoGe2-Aerial (LoRA) | no camera (model guesses) | no labelled vehicle in frame | 8 | +41.0 | 1.48 | 0.92 (0.001) |
| MoGe2-Aerial (LoRA) | no camera (model guesses) | vehicles in frame | 22 | +0.7 | 1.21 | 0.87 (0.000) |
