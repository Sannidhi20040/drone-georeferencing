Noise floor of the temperature-0 models: 4 repeats on the unrotated image, pilot prompt and settings. Median distance spread [95% cluster-bootstrap over frames, 2000 resamples, seed 20261025].

| Model | Questions | Repeat-to-repeat spread (noise floor) | Pilot rotation spread, same questions | Questions with 4 identical repeats | Repeats equal to the pilot's 0 deg answer |
|---|---|---|---|---|---|
| Haiku 4.5 | 24 (12 frames) | 0% [0, 0] | 97% [80, 128] | 24 of 24 | 96 of 96 |
| Sonnet 4.6 | 2 (2 frames) | 29% [28, 30] | 54% [37, 71] | 0 of 2 | 0 of 8 |
| Qwen2.5-VL 3B | 24 (12 frames) | 0% [0, 0] | 92% [0, 164] | 24 of 24 | 96 of 96 |

API/Ollama errors: 0. Spend recorded: US$0.2571 over 200 calls.
