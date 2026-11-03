# sunday_checks: free re-analyses of the rotation pilot and the depth comparison

Steps 0-3 make no API calls and read only files that already exist. Steps 4-5 call a model API (key from the environment only, a spend cap, every raw prompt and response saved in `output/*_raw_responses.jsonl`). Every bootstrap and permutation
uses `SEED = 20261025` (`common.py`). Run from the repo root with a Python that has numpy and scipy (the `dcenv` used for the
depth comparison does):

```bash
python sunday_checks/step0_survey.py            # finds the saved files, prints what is there, stops if something is missing
python sunday_checks/step1_rotation_bootstrap.py
python sunday_checks/step2_depth_followup.py
python sunday_checks/step3_fov_calibration.py
python sunday_checks/step4_feasibility.py       # NO API call: key check, crop feasibility, cost estimate
```

Outputs go to `sunday_checks/output/*.md`.

| Script | What |
|---|---|
| `common.py` | loaders and constants; reuses `pilot/vlm_rotation.py`'s own `load_rows` so rows are selected exactly as its reports do |
| `step0_survey.py` | file survey and consistency check |
| `step1_rotation_bootstrap.py` | cluster bootstrap (12 frames, 2,000 resamples) of spread, error, accuracy, answers changed, Spearman(confidence, error); checks the headline numbers |
| `step2_depth_followup.py` | depth bootstrap, the no-vehicle frames (Mann-Whitney on altitude, bunching permutation test), slope and r after trimming 3+3 altitude extremes |
| `step3_fov_calibration.py` | FOV that makes the adjacent bay 2.905 m, corrected truths through the real geometry, old vs corrected errors |
| `step4_feasibility.py` | no API call: key check, which distance questions fit a square crop, cost estimate |
| `step4_run.py`, `step4_analyze.py` | the paid step 4 (Claude Haiku 5.5 only): noise floor and square-crop rotation spread; results in `output/step4_results.md` |
| `step5_noise_floor.py` | repeat-to-repeat noise at temperature 0 for Haiku 4.5 and Sonnet 4.6 (paid) and Qwen (free, Ollama); results in `output/step5_results.md` |

Inputs taken from the brief and not recomputed: pipeline median adjacent-bay distance 3.33 m, satellite 2.905 m per bay.

Not committed: `output/step4_images/` (square crops rendered from AU-AIR frames, non-commercial licence). Step 5's Sonnet 4.6 result covers only 2 questions (budget); read it as a lead.
