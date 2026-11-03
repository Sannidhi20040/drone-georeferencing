# Depth-model comparison on the 30 clean AU-AIR frames

Compares UniDepthV2, MoGe-2 and MoGe2-Aerial with the earlier Depth Anything 3 result (`pilot/da3_altitude.py`) on the
same 30 near-nadir frames of clip `20190829091111`: estimated depth of the ground at the image centre vs the flight-log
altitude (13-29 m, relative to take-off).

| File | What |
|---|---|
| `run_depth_comparison.py` | runs one model, four camera settings, 30 frames; saves a row and a depth map per run |
| `analyze_depth_comparison.py` | statistics, tables, scatter plot |
| `clean_frames.csv`, `da3_reference_clean.csv` | the 30 frames and the earlier DA3 numbers, copied read-only from `da3_altitude.csv` (never modified) |
| `vehicle_counts.csv` | labelled vehicles per frame (counts only), used for the post-hoc split |
| `output/` | `*_raw.csv` (every frame, model, setting, predicted focal/FOV), `comparison_table.{md,csv}`, `comparison_by_scene_content.md`, `predicted_camera_when_none_given.md`, `depth_vs_altitude.png`. `output/depth_maps/` (the raw `.npy` depth maps, float32 metres, 1.5 GB) is git-ignored: AU-AIR is non-commercial, do not publish it. |

## How the depth is summarised (same as DA3)
Median over the centred box covering 30 % of the width and 30 % of the height of the model's depth map
(`CENTER_FRACTION = 0.30` in `pilot/da3_altitude.py`; not 50 %).

## Camera settings and conversions
1920x1080, fx = fy, principal point at the image centre. For a diagonal FOV `d`:
`tan(hfov/2) = (1920 / hypot(1920, 1080)) * tan(d/2)`, `focal = 960 / tan(hfov/2)`.

| Diagonal FOV | Horizontal FOV | Focal length |
|---|---|---|
| 71 deg | 63.74 deg | 1544.2 px |
| 80 deg | 72.36 deg | 1312.7 px |
| 94 deg | 86.13 deg | 1027.1 px |

* UniDepthV2: `model.infer(rgb, camera)` with `camera = K` (3x3 pinhole, above focal, centre principal point), or
  `model.infer(rgb)` for no camera.
* MoGe-2 / MoGe2-Aerial: `model.infer(image, fov_x=<horizontal FOV in degrees>)`, or without `fov_x` for no camera.
  The image is resized to 1022x574 first (long side 1022, a multiple of 14, as the AerialMetric benchmark does);
  MoGe then resizes to its own token budget.
* "No camera": the model's own predicted focal length / FOV is recorded (`pred_*` columns; see
  `output/predicted_camera_when_none_given.md`). For UniDepth the `pred_*` columns of the *given* settings are its internal
  prediction and ignore the supplied camera; read them for `none` only.

## Which model each result is
| Key | Model | Source |
|---|---|---|
| `unidepth` | UniDepthV2 ViT-L | `lpiccinelli/unidepth-v2-vitl14`, code lpiccinelli-eth/UniDepth @ 8d8cfe4 |
| `moge2` | plain MoGe-2 ViT-L (normal) | `Ruicheng/moge-2-vitl-normal`, code microsoft/MoGe @ 74fbce0 |
| `moge2aerial` | **MoGe2-Aerial**, the real aerial fine-tune (LoRA rank 96) | `weights/Moge2-Aerial.pt` (1.48 GB) in the Hugging Face dataset repo `Kuiee/AerialMetric-ECCV2026`, loaded with that repo's own `MogeLoRAEngine` (strict state-dict load) @ kuieless/AerialMetric-ECCV2026 895ce09 |

MoGe2-Aerial is derived from MoGe-2; the AerialMetric authors ask that the AerialMetric paper (arXiv 2606.29716) be
cited when using it.

## Reproduce
```bash
git clone --depth 1 https://github.com/lpiccinelli-eth/UniDepth.git        repos/UniDepth
git clone --depth 1 https://github.com/microsoft/MoGe.git                  repos/MoGe
git clone --depth 1 https://github.com/kuieless/AerialMetric-ECCV2026.git  repos/AerialMetric-ECCV2026
pip install torch torchvision numpy scipy opencv-python-headless pillow matplotlib einops timm huggingface_hub \
    safetensors peft click tqdm pandas wandb h5py termcolor tabulate trimesh imageio protobuf
pip install "git+https://github.com/EasternJournalist/utils3d.git@3fab839f0be9931dac7c8488eb0e1600c236e183"
for m in unidepth moge2 moge2aerial; do python depth_comparison/run_depth_comparison.py --model $m --data data_check; done
python depth_comparison/analyze_depth_comparison.py
```
The code is imported straight from the clones (no `pip install -e`); UniDepth needs neither xformers nor its CUDA ops
for V2 inference. The original run used `--code-root` pointing at wherever the clones were.

## How it was run
Apple GPU (PyTorch MPS), float32, models at their own default resolutions. Inference time was 18 minutes in total
(UniDepth 8 min, MoGe-2 4.6 min, MoGe2-Aerial 5.4 min), plus about 90 s of model loading each and first-time weight downloads.
No Kaggle notebook was needed.

## Caveats
* Log altitude is relative to take-off, so it equals height above the ground under the drone only where the ground is level
  and at take-off height.
* Depth maps are z-depth (distance along the optical axis), which equals altitude at the image centre for a nadir camera.
* The camera FOV of the AU-AIR drone is not published: 80 deg is an assumption, 71-94 deg comes from the landmark check.
* The vehicle split in `comparison_by_scene_content.md` was found after seeing the main results; it is exploratory.
