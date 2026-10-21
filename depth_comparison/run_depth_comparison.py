#!/usr/bin/env python3
"""Run one monocular metric-depth model on the 30 clean AU-AIR frames in four camera settings.

    python depth_comparison/run_depth_comparison.py --model unidepth      --data data_check
    python depth_comparison/run_depth_comparison.py --model moge2         --data data_check
    python depth_comparison/run_depth_comparison.py --model moge2aerial   --data data_check

One model per process: plain MoGe-2 and MoGe2-Aerial ship Python packages that are both named `moge`
(microsoft/MoGe and the AerialMetric fork), so they cannot be imported together.

Settings (see README.md for the conversions):
  given_80  camera given, diagonal FOV 80 deg   (focal 1312.6 px at 1920x1080, horizontal FOV 72.36 deg)
  given_71  camera given, diagonal FOV 71 deg
  given_94  camera given, diagonal FOV 94 deg
  none      no camera given; the model predicts it (the predicted focal length / FOV is recorded)

Summary per frame = median depth over the centred box covering 30 % of the width and of the height,
exactly as pilot/da3_altitude.py did for Depth Anything 3 (CENTER_FRACTION = 0.30).

Outputs (output/ is git-ignored; AU-AIR is non-commercial, never publish frames or depth maps):
  output/<model>_raw.csv                      one row per (frame, setting)
  output/depth_maps/<model>/<setting>/frame_XXXX.npy   the model's raw depth map, float32, metres
Re-running skips rows already in the CSV, so an interrupted run resumes.
"""
import argparse
import csv
import math
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLIP = "20190829091111"
W, H = 1920, 1080
CENTER_FRACTION = 0.30
GIVEN_DIAG_FOV = {"given_80": 80.0, "given_71": 71.0, "given_94": 94.0}
SETTINGS = ["given_80", "none", "given_71", "given_94"]
CODE = {  # where each model's own code lives (cloned from the official repos; see README.md)
    "unidepth": "UniDepth",
    "moge2": "MoGe",
    "moge2aerial": "AerialMetric-ECCV2026/MoGe",
}
RAW_COLUMNS = ["model", "setting", "frame", "log_altitude_m", "depth_m", "assumed_diag_fov_deg", "assumed_hfov_deg",
               "assumed_focal_px", "pred_focal_px", "pred_hfov_deg", "pred_diag_fov_deg", "depth_map_shape", "seconds"]


def camera_from_diag_fov(diag_fov_deg, width=W, height=H):
    """Diagonal FOV -> (horizontal FOV deg, focal length px). fx = fy; principal point at the image centre."""
    diag = math.hypot(width, height)
    tan_half_h = (width / diag) * math.tan(math.radians(diag_fov_deg) / 2)
    hfov = 2 * math.degrees(math.atan(tan_half_h))
    return hfov, (width / 2) / tan_half_h


def hfov_from_focal(focal_px, width=W):
    """Horizontal FOV (degrees) of an image `width` px wide with this focal length."""
    return 2 * math.degrees(math.atan((width / 2) / focal_px))


def fov_from_focal(fx_px, fy_px, width=W, height=H):
    """(horizontal FOV, diagonal FOV) in degrees from focal lengths in pixels."""
    hfov = 2 * math.degrees(math.atan((width / 2) / fx_px))
    diag = 2 * math.degrees(math.atan(math.hypot((width / 2) / fx_px, (height / 2) / fy_px)))
    return hfov, diag


def central_median(depth, fraction=CENTER_FRACTION):
    """Identical to pilot/da3_altitude.py: median over the centred box of `fraction` x `fraction`."""
    import numpy as np
    h, w = depth.shape
    ch, cw = max(1, round(h * fraction)), max(1, round(w * fraction))
    y0, x0 = (h - ch) // 2, (w - cw) // 2
    window = depth[y0:y0 + ch, x0:x0 + cw]
    window = window[np.isfinite(window)]
    return float(np.median(window))


def pick_device(name):
    import torch
    if name:
        return torch.device(name)
    return torch.device("cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")


class UniDepthRunner:
    """UniDepthV2 ViT-L: model.infer(rgb 0-255 CHW, camera) -> depth, intrinsics (README, unidepthv2.py)."""

    def __init__(self, device, repo_root):
        sys.path.insert(0, str(repo_root))
        from unidepth.models import UniDepthV2
        self.model = UniDepthV2.from_pretrained("lpiccinelli/unidepth-v2-vitl14").to(device).eval()
        self.device = device

    def __call__(self, rgb_uint8_hwc, setting, focal_px):
        import numpy as np
        import torch
        rgb = torch.from_numpy(rgb_uint8_hwc).permute(2, 0, 1)
        camera = None
        if focal_px is not None:
            camera = torch.tensor([[focal_px, 0, W / 2], [0, focal_px, H / 2], [0, 0, 1]], dtype=torch.float32)
        with torch.inference_mode():
            out = self.model.infer(rgb, camera)
        depth = out["depth"].squeeze().float().cpu().numpy()
        k = out["intrinsics"].squeeze().float().cpu().numpy()
        return depth, float(k[0, 0]), float(k[1, 1])           # focal lengths in ORIGINAL-image pixels


class MoGeRunner:
    """MoGe-2 (plain, from microsoft/MoGe) or MoGe2-Aerial (LoRA, AerialMetric fork). Input is resized to a
    long side of 1022 px (a multiple of 14, as the AerialMetric benchmark does); MoGe then resizes to its own
    token budget, so this is the same effective resolution as the full-size image."""

    def __init__(self, which, device, repo_root):
        sys.path.insert(0, str(repo_root))
        import torch
        self.device = device
        self.torch = torch
        if which == "moge2":
            from moge.model.v2 import MoGeModel
            self.model = MoGeModel.from_pretrained("Ruicheng/moge-2-vitl-normal").to(device).eval()
        else:
            from huggingface_hub import hf_hub_download
            ckpt = hf_hub_download(repo_id="Kuiee/AerialMetric-ECCV2026", repo_type="dataset",
                                   filename="weights/Moge2-Aerial.pt")
            from moge.scripts.a_infer_lora96_norm import MogeLoRAEngine
            self.model = MogeLoRAEngine(ckpt, device=str(device), fp16=False, lora_rank=96).model   # strict state-dict load

    def __call__(self, rgb_uint8_hwc, setting, focal_px):
        import cv2
        import numpy as np
        torch = self.torch
        scale = 1024 / max(W, H)
        new_w, new_h = max(14, int(W * scale) // 14 * 14), max(14, int(H * scale) // 14 * 14)
        small = cv2.resize(rgb_uint8_hwc, (new_w, new_h), interpolation=cv2.INTER_AREA)
        tensor = torch.from_numpy(small).float().div(255.0).permute(2, 0, 1).to(self.device)
        kwargs = {"use_fp16": False}
        if focal_px is not None:
            kwargs["fov_x"] = hfov_from_focal(focal_px)
        with torch.inference_mode():
            out = self.model.infer(tensor, **kwargs)
        depth = out["depth"].squeeze().float().cpu().numpy()
        k = out["intrinsics"].squeeze().float().cpu().numpy()   # normalised: fx / width, fy / height
        return depth, float(k[0, 0]) * W, float(k[1, 1]) * H


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model", required=True, choices=list(CODE))
    ap.add_argument("--data", default="data_check", help="folder with images/")
    ap.add_argument("--code-root", default=None, help="folder holding the cloned repos (default: depth_comparison/repos)")
    ap.add_argument("--out", default=str(HERE / "output"))
    ap.add_argument("--device", default=None)
    ap.add_argument("--limit", type=int, default=None, help="only the first N frames (quick test)")
    ap.add_argument("--settings", nargs="+", default=SETTINGS, choices=SETTINGS)
    args = ap.parse_args(argv)

    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    import cv2
    import numpy as np
    frames = list(csv.DictReader(open(HERE / "clean_frames.csv")))[:args.limit]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    raw_path = out / f"{args.model}_raw.csv"
    done = set()
    if raw_path.exists():
        done = {(r["setting"], int(r["frame"])) for r in csv.DictReader(open(raw_path))}
    todo = [(s, f) for f in frames for s in args.settings if (s, int(f["frame"])) not in done]
    print(f"{args.model}: {len(frames)} frames x {len(args.settings)} settings; {len(todo)} to run, {len(done)} already done")
    if not todo:
        return 0

    device = pick_device(args.device)
    code_root = Path(args.code_root or HERE / "repos") / CODE[args.model]
    t0 = time.time()
    runner = UniDepthRunner(device, code_root) if args.model == "unidepth" else MoGeRunner(args.model, device, code_root)
    print(f"model loaded on {device} in {time.time() - t0:.0f}s")

    new_file = not raw_path.exists()
    with open(raw_path, "a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=RAW_COLUMNS)
        if new_file:
            writer.writeheader()
        for n, (setting, f) in enumerate(todo, 1):
            frame = int(f["frame"])
            image = cv2.cvtColor(cv2.imread(str(Path(args.data) / "images" / f"frame_{CLIP}_x_{frame:07d}.jpg")), cv2.COLOR_BGR2RGB)
            assert image.shape[:2] == (H, W), image.shape
            if setting == "none":
                hfov_a = diag_a = focal_a = None
            else:
                diag_a = GIVEN_DIAG_FOV[setting]
                hfov_a, focal_a = camera_from_diag_fov(diag_a)
            t1 = time.time()
            depth, fx, fy = runner(image, setting, focal_a)
            seconds = time.time() - t1
            hfov_p, diag_p = fov_from_focal(fx, fy)
            map_dir = out / "depth_maps" / args.model / setting
            map_dir.mkdir(parents=True, exist_ok=True)
            np.save(map_dir / f"frame_{frame:04d}.npy", depth.astype(np.float32))
            writer.writerow({
                "model": args.model, "setting": setting, "frame": frame, "log_altitude_m": f["log_altitude_m"],
                "depth_m": f"{central_median(depth):.4f}",
                "assumed_diag_fov_deg": "" if diag_a is None else f"{diag_a:g}",
                "assumed_hfov_deg": "" if hfov_a is None else f"{hfov_a:.3f}",
                "assumed_focal_px": "" if focal_a is None else f"{focal_a:.2f}",
                "pred_focal_px": f"{(fx + fy) / 2:.2f}", "pred_hfov_deg": f"{hfov_p:.3f}", "pred_diag_fov_deg": f"{diag_p:.3f}",
                "depth_map_shape": "x".join(map(str, depth.shape)), "seconds": f"{seconds:.2f}"})
            fh.flush()
            if n % 10 == 0 or n == len(todo):
                print(f"  {n}/{len(todo)}  last {seconds:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
