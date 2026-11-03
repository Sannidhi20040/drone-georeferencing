| Model | Setting | n | Median % error | % error range | Slope (m/m) | Pearson r (p) | Spearman rho (p) | Median est/log |
|---|---|---|---|---|---|---|---|---|
| DA3-Metric-Large (earlier run) | camera given, 80 deg diag (72.4 deg H) | 30 | -56.4 | -73 to -43 | 0.13 | 0.34 (0.063) | 0.41 (0.023) | 0.44 |
| UniDepthV2 (ViT-L) | camera given, 80 deg diag (72.4 deg H) | 30 | -9.9 | -23 to +72 | 1.01 | 0.59 (0.001) | 0.54 (0.002) | 0.90 |
| UniDepthV2 (ViT-L) | no camera (model guesses) | 30 | -17.2 | -30 to +68 | 0.87 | 0.53 (0.003) | 0.50 (0.005) | 0.83 |
| UniDepthV2 (ViT-L) | camera given, 71 deg diag (63.7 deg H) | 30 | -3.6 | -18 to +83 | 1.08 | 0.60 (0.000) | 0.54 (0.002) | 0.96 |
| UniDepthV2 (ViT-L) | camera given, 94 deg diag (86.1 deg H) | 30 | -19.2 | -31 to +55 | 0.90 | 0.59 (0.001) | 0.54 (0.002) | 0.81 |
| MoGe-2 (ViT-L normal) | camera given, 80 deg diag (72.4 deg H) | 30 | -23.0 | -35 to -2 | 0.84 | 0.88 (0.000) | 0.75 (0.000) | 0.77 |
| MoGe-2 (ViT-L normal) | no camera (model guesses) | 30 | -30.7 | -43 to -10 | 0.72 | 0.88 (0.000) | 0.73 (0.000) | 0.69 |
| MoGe-2 (ViT-L normal) | camera given, 71 deg diag (63.7 deg H) | 30 | -11.2 | -26 to +15 | 0.95 | 0.87 (0.000) | 0.77 (0.000) | 0.89 |
| MoGe-2 (ViT-L normal) | camera given, 94 deg diag (86.1 deg H) | 30 | -36.9 | -49 to -23 | 0.72 | 0.90 (0.000) | 0.78 (0.000) | 0.63 |
| MoGe2-Aerial (LoRA) | camera given, 80 deg diag (72.4 deg H) | 30 | +5.0 | -14 to +53 | 1.22 | 0.76 (0.000) | 0.63 (0.000) | 1.05 |
| MoGe2-Aerial (LoRA) | no camera (model guesses) | 30 | +4.5 | -16 to +59 | 1.09 | 0.72 (0.000) | 0.57 (0.001) | 1.05 |
| MoGe2-Aerial (LoRA) | camera given, 71 deg diag (63.7 deg H) | 30 | +20.7 | -2 to +79 | 1.37 | 0.73 (0.000) | 0.60 (0.000) | 1.21 |
| MoGe2-Aerial (LoRA) | camera given, 94 deg diag (86.1 deg H) | 30 | -14.0 | -31 to +20 | 1.04 | 0.79 (0.000) | 0.66 (0.000) | 0.86 |
