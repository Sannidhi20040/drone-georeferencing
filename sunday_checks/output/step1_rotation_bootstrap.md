Cluster bootstrap over the 12 frames, 2000 resamples, seed 20261025; point estimate [95% percentile interval].

| Model | Median distance spread across rotations | Median distance error vs pipeline | Comparison accuracy | Comparison answers changed by rotation | Spearman: confidence vs abs distance error |
|---|---|---|---|---|---|
| Haiku 5.5 | 7% [6, 9] | 15% [12, 20] | 100% [100, 100] | 0% [0, 0] | 0.45 [0.16, 0.64] |
| Sonnet 4.6 | 69% [56, 88] | 61% [47, 85] | 100% [100, 100] | 0% [0, 0] | -0.46 [-0.55, -0.30] |
| Opus 4.6 | 50% [50, 75] | 36% [27, 48] | 99% [98, 100] | 3% [0, 10] | -0.38 [-0.64, -0.09] |
| Haiku 4.5 | 97% [80, 128] | 37% [30, 52] | 85% [75, 94] | 33% [13, 55] | -0.00 [-0.24, 0.16] |
| Qwen2.5-VL 3B | 92% [0, 164] | 42% [31, 170] | 57% [40, 74] | 12% [0, 23] | 0.44 [0.15, 0.62] |

Reproduction of the headline numbers (computed point estimate rounded to a whole percent vs the number in the brief):

| Statistic | Haiku 5.5 | Sonnet 4.6 | Opus 4.6 | Haiku 4.5 | Qwen2.5-VL 3B |
|---|---|---|---|---|---|
| median distance spread % | 6.8 vs 7 | 69.0 vs 69 | 50.0 vs 50 | 96.7 vs 97 | 91.7 vs 92 |
| comparison accuracy % | 100.0 vs 100 | 100.0 vs 100 | 99.2 vs 99 | 85.0 vs 85 | 56.7 vs 57 |
| median distance error % | 15.4 vs 15 | 61.4 vs 61 | 36.0 vs 36 | 37.3 vs 37 | 42.5 vs 42 |
| comparison answers changed % | 0.0 vs 0 | 0.0 vs 0 | 3.3 vs 3 | 33.3 vs 33 | 11.5 vs 12 |

All headline numbers reproduce.
