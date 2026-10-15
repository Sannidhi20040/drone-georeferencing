#!/usr/bin/env python3
"""Does Depth Anything 3's metric depth agree with the AU-AIR flight-log altitude?

For ~30 near-level frames of AU-AIR clip 20190829091111, plus the four frames used in the
satellite-landmark test (172, 391, 2130, 2300), this takes the median metric depth over the
central 30% of the image and compares it with the logged altitude.

Which model, and how depth becomes metres (from the official README, section FAQ, and
src/depth_anything_3/utils/alignment.py in bytedance-seed/depth-anything-3):

  * Model: DA3METRIC-LARGE ("depth-anything/DA3METRIC-LARGE", Apache-2.0), the monocular metric model.
  * Its raw output is NOT metres. The README says:
        metric_depth = focal * net_output / 300.
    where focal is the focal length in pixels, the mean of fx and fy of the intrinsic matrix.
  * Standalone DA3METRIC-LARGE estimates no camera, so prediction.intrinsics is not provided.
    (Only the nested model derives the focal length from its own camera branch.) The focal length
    therefore has to be supplied here, in pixels at the PROCESSED resolution, i.e. the size of the
    returned depth map (default: long side 504), not the 1920x1080 original. It is derived from an
    assumed diagonal FOV, which AU-AIR does not publish; the implied FOV is reported as a check.

Setup in Kaggle / Colab (GPU runtime, internet on), commands from the repo README:

    !git clone https://github.com/ByteDance-Seed/Depth-Anything-3
    %cd Depth-Anything-3
    !pip install xformers "torch>=2" torchvision
    !pip install -e .
    # annotations.json + the selected images (see --select-only) in a folder, then:
    !python pilot/da3_altitude.py --data /kaggle/input/au-air-subset

To list which frames to upload, so the 2.3 GB dataset never has to move (run anywhere, no GPU):

    python pilot/da3_altitude.py --data data_check --select-only

Notes on the data:
  * AU-AIR altitude is in MILLIMETRES, relative to take-off (read from the altimeter).
  * AU-AIR logs the drone body's roll and pitch, not the camera tilt. "Tilt" here is
    hypot(roll, pitch) of the body, the only angle available; the Bebop 2 stabilises its video.
  * AU-AIR is licensed non-commercial. Do not commit its frames; only this script and the
    derived CSV are meant to be kept.
"""
import argparse
import csv
import json
import math
import re
import statistics
import sys
from pathlib import Path

CLIP = "20190829091111"
MODEL_ID = "depth-anything/DA3METRIC-LARGE"
PROCESS_RES = 504            # inference() default: the long side is resized to this
METRIC_DIVISOR = 300.0       # README FAQ: metric_depth = focal * net_output / 300
CENTER_FRACTION = 0.30       # central 30% of the width and of the height
TILT_LIMIT_DEG = 5.0
N_CLEAN = 30
DEFAULT_DIAG_FOV_DEG = 80.0  # no published FOV for this camera; pilot calibrations gave ~71-94 deg, median ~81

# The four frames of the landmark test and the per-frame scale (predicted / satellite) measured there.
LANDMARK_SCALES = {172: 0.877, 391: 0.889, 2130: 1.103, 2300: 1.092}


def load_frames(data_dir, clip=CLIP):
    """Per-frame metadata for one clip: file name, frame number, altitude in metres, body tilt."""
    with open(Path(data_dir) / "annotations.json") as f:
        annotations = json.load(f)["annotations"]
    frames = []
    for a in annotations:
        m = re.match(rf"frame_{clip}_x+_(\d+)\.jpg$", a["image_name"])
        if not m:
            continue
        roll = math.degrees(a["angle_phi"])
        pitch = math.degrees(a["angle_theta"])
        frames.append({
            "image": a["image_name"],
            "frame": int(m.group(1)),
            "altitude_m": a["altitude"] / 1000.0,    # millimetres -> metres
            "roll_deg": roll,
            "pitch_deg": pitch,
            "tilt_deg": math.hypot(roll, pitch),
        })
    frames.sort(key=lambda r: r["frame"])
    return frames


def select_clean_frames(frames, n=N_CLEAN, tilt_limit=TILT_LIMIT_DEG, exclude=(), min_gap=10):
    """n near-level frames spread over the clip's altitude range.

    Targets evenly spaced altitude quantiles and takes the closest eligible frame to each, skipping
    frames within `min_gap` frame numbers of one already chosen so neighbours are not near-duplicates.
    """
    eligible = [r for r in frames if r["tilt_deg"] < tilt_limit and r["frame"] not in set(exclude)]
    if len(eligible) < n:
        raise ValueError(f"only {len(eligible)} frames with tilt < {tilt_limit} deg, need {n}")
    by_alt = sorted(r["altitude_m"] for r in eligible)
    chosen = []
    for k in range(n):
        target = by_alt[round(k * (len(by_alt) - 1) / (n - 1))]
        for r in sorted(eligible, key=lambda r: abs(r["altitude_m"] - target)):
            if all(abs(r["frame"] - c["frame"]) >= min_gap for c in chosen):
                chosen.append(r)
                break
    return sorted(chosen, key=lambda r: r["frame"])


def focal_px_from_diag_fov(width, height, diag_fov_deg):
    """Pinhole focal length (pixels) of a width x height image with the given diagonal FOV."""
    return (math.hypot(width, height) / 2) / math.tan(math.radians(diag_fov_deg) / 2)


def processed_focal_px(focal_px, width, height, proc_w, proc_h):
    """Focal length at the processed resolution: mean of fx and fy after the resize."""
    return (focal_px * proc_w / width + focal_px * proc_h / height) / 2


def central_median(depth, fraction=CENTER_FRACTION):
    """Median over the centred box covering `fraction` of the width and of the height."""
    import numpy as np
    h, w = depth.shape
    ch, cw = max(1, round(h * fraction)), max(1, round(w * fraction))
    y0, x0 = (h - ch) // 2, (w - cw) // 2
    window = depth[y0:y0 + ch, x0:x0 + cw]
    window = window[np.isfinite(window)]
    return float(np.median(window))


def to_metres(net_output, focal_proc_px):
    """README: metric_depth = focal * net_output / 300."""
    return focal_proc_px * net_output / METRIC_DIVISOR


def implied_diag_fov_deg(net_median, altitude_m, width, height, proc_w, proc_h):
    """Diagonal FOV that would make DA3's depth equal the logged altitude (frame by frame)."""
    focal_proc = METRIC_DIVISOR * altitude_m / net_median
    focal_px = focal_proc / ((proc_w / width + proc_h / height) / 2)
    return math.degrees(2 * math.atan((math.hypot(width, height) / 2) / focal_px))


def pct_error(estimate, reference):
    return 100.0 * (estimate - reference) / reference


def pearson(x, y):
    mx, my = statistics.fmean(x), statistics.fmean(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    return sxy / math.sqrt(sxx * syy)


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    for rank, i in enumerate(order):
        out[i] = float(rank)
    return out


def spearman(x, y):
    return pearson(ranks(x), ranks(y))


def slope(x, y):
    """Least-squares slope of y on x."""
    mx, my = statistics.fmean(x), statistics.fmean(y)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / sum((a - mx) ** 2 for a in x)


def run_da3(model, image_paths, batch_size):
    """Raw network output (N, H, W) from DA3METRIC-LARGE, in chunks.

    The metric model's config disables cross-view attention, so views are independent and chunking
    does not change the result.
    """
    import numpy as np
    outputs = []
    for i in range(0, len(image_paths), batch_size):
        prediction = model.inference([str(p) for p in image_paths[i:i + batch_size]], process_res=PROCESS_RES)
        outputs.append(np.asarray(prediction.depth, dtype=np.float32))
    return np.concatenate(outputs, axis=0), prediction


def fmt(x, nd=1, sign=False):
    return f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", default="data_check", help="folder with annotations.json and images/")
    ap.add_argument("--clip", default=CLIP)
    ap.add_argument("--out", default="pilot/output", help="where to write the CSV")
    ap.add_argument("--n", type=int, default=N_CLEAN, help="number of near-level frames")
    ap.add_argument("--tilt-limit", type=float, default=TILT_LIMIT_DEG)
    ap.add_argument("--diag-fov", type=float, default=DEFAULT_DIAG_FOV_DEG,
                    help="assumed diagonal FOV in degrees (sets the focal length)")
    ap.add_argument("--focal-px", type=float, default=None,
                    help="focal length in pixels at the ORIGINAL resolution (overrides --diag-fov)")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--device", default=None, help="cuda | mps | cpu (default: best available)")
    ap.add_argument("--model", default=MODEL_ID)
    ap.add_argument("--select-only", action="store_true", help="only list the frames to upload, no model")
    args = ap.parse_args(argv)

    frames = load_frames(args.data, args.clip)
    by_number = {r["frame"]: r for r in frames}
    missing = [n for n in LANDMARK_SCALES if n not in by_number]
    if missing:
        sys.exit(f"landmark frames not found in clip {args.clip}: {missing}")
    clean = select_clean_frames(frames, args.n, args.tilt_limit, exclude=LANDMARK_SCALES)
    landmark = [by_number[n] for n in LANDMARK_SCALES]
    rows = [dict(r, group="clean") for r in clean] + [dict(r, group="landmark") for r in landmark]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    listing = out_dir / "da3_selected_frames.txt"
    listing.write_text("\n".join(r["image"] for r in rows) + "\n")
    print(f"{len(clean)} near-level frames (body tilt < {args.tilt_limit} deg, altitude "
          f"{min(r['altitude_m'] for r in clean):.1f}-{max(r['altitude_m'] for r in clean):.1f} m) "
          f"+ {len(landmark)} landmark frames; list written to {listing}")
    if args.select_only:
        return 0

    import numpy as np
    import torch
    from PIL import Image
    from depth_anything_3.api import DepthAnything3

    device = torch.device(args.device or ("cuda" if torch.cuda.is_available()
                                          else "mps" if torch.backends.mps.is_available() else "cpu"))
    if device.type != "cuda":
        print(f"WARNING: running on {device.type}; this is meant for a GPU and will be slow")
    model = DepthAnything3.from_pretrained(args.model).to(device=device)

    paths = [Path(args.data) / "images" / r["image"] for r in rows]
    absent = [p.name for p in paths if not p.exists()]
    if absent:
        sys.exit(f"{len(absent)} images missing from {Path(args.data) / 'images'}, e.g. {absent[:3]}. "
                 f"Upload the files listed in {listing}")
    width, height = Image.open(paths[0]).size
    focal_px = args.focal_px or focal_px_from_diag_fov(width, height, args.diag_fov)

    net, prediction = run_da3(model, paths, args.batch)
    proc_h, proc_w = net.shape[1:]
    focal_proc = processed_focal_px(focal_px, width, height, proc_w, proc_h)
    print(f"original {width}x{height}, processed {proc_w}x{proc_h}; focal {focal_px:.0f} px original "
          f"-> {focal_proc:.0f} px processed (assumed diagonal FOV {args.diag_fov:g} deg"
          f"{', overridden by --focal-px' if args.focal_px else ''})")
    if getattr(prediction, "intrinsics", None) is not None:
        print("note: the model returned its own intrinsics; they are NOT used, the assumed focal length is")

    for r, depth in zip(rows, net):
        r["net_median"] = central_median(depth)
        r["da3_depth_m"] = to_metres(r["net_median"], focal_proc)
        r["pct_error"] = pct_error(r["da3_depth_m"], r["altitude_m"])
        r["ratio"] = r["da3_depth_m"] / r["altitude_m"]
        r["implied_fov"] = implied_diag_fov_deg(r["net_median"], r["altitude_m"], width, height, proc_w, proc_h)

    csv_path = out_dir / "da3_altitude.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame", "log_altitude_m", "da3_depth_m", "pct_error", "group", "tilt_deg",
                    "da3_over_log", "implied_diag_fov_deg", "da3_net_median"])
        for r in rows:
            w.writerow([r["frame"], f"{r['altitude_m']:.3f}", f"{r['da3_depth_m']:.3f}", f"{r['pct_error']:.2f}",
                        r["group"], f"{r['tilt_deg']:.2f}", f"{r['ratio']:.4f}", f"{r['implied_fov']:.2f}",
                        f"{r['net_median']:.5f}"])
    print(f"wrote {csv_path}")

    cl = [r for r in rows if r["group"] == "clean"]
    errs = [r["pct_error"] for r in cl]
    fovs = [r["implied_fov"] for r in cl]
    median_ratio = statistics.median(r["ratio"] for r in cl)
    print(f"\n== {len(cl)} near-level frames: DA3 depth (centre {CENTER_FRACTION:.0%}) vs logged altitude ==")
    print(f"% error  median {fmt(statistics.median(errs), 1, True)}%   range {fmt(min(errs), 1, True)}% to "
          f"{fmt(max(errs), 1, True)}%   median |error| {fmt(statistics.median(abs(e) for e in errs))}%")
    print(f"DA3 / log altitude   median {median_ratio:.3f}")
    print(f"diagonal FOV that would make DA3 equal the log: median {statistics.median(fovs):.1f} deg, "
          f"range {min(fovs):.1f}-{max(fovs):.1f} deg  (assumed {args.diag_fov:g})")
    alts = [r["altitude_m"] for r in cl]
    depths = [r["da3_depth_m"] for r in cl]
    print(f"DA3 depth {min(depths):.1f}-{max(depths):.1f} m (median {statistics.median(depths):.1f}) vs log altitude "
          f"{min(alts):.1f}-{max(alts):.1f} m (median {statistics.median(alts):.1f})")
    print(f"does DA3 track altitude?  Pearson r {pearson(alts, depths):.2f}, Spearman {spearman(alts, depths):.2f}, "
          f"slope {slope(alts, depths):.2f} m of DA3 depth per m of altitude "
          f"(a focal-length/FOV error rescales all depths and cannot change r)")

    print("\n== Landmark-test frames: measured scale vs DA3 / log altitude ==")
    print("scale = predicted / satellite distances (yours). If the altitude reading were the cause, DA3/log "
          "would track 1/scale.\n'relative' divides by the median DA3/log of the near-level frames, which "
          "cancels a constant focal-length (FOV) error.")
    print(f"{'frame':>6} {'tilt':>5} {'log alt':>8} {'DA3':>7} {'DA3/log':>8} {'relative':>9} {'1/scale':>8} "
          f"{'your scale':>10} {'implied FOV':>11}")
    for r in rows:
        if r["group"] != "landmark":
            continue
        s = LANDMARK_SCALES[r["frame"]]
        print(f"{r['frame']:>6} {r['tilt_deg']:>5.1f} {r['altitude_m']:>8.2f} {r['da3_depth_m']:>7.2f} "
              f"{r['ratio']:>8.3f} {r['ratio'] / median_ratio:>9.3f} {1 / s:>8.3f} {s:>10.3f} {r['implied_fov']:>11.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
