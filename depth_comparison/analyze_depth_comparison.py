#!/usr/bin/env python3
"""Statistics, table and scatter plot for the depth-model comparison.

    python depth_comparison/analyze_depth_comparison.py

Reads output/<model>_raw.csv (from run_depth_comparison.py) and da3_reference_clean.csv (the earlier DA3 run on
the same 30 frames, copied read-only from da3_altitude.csv). Writes output/comparison_table.{md,csv},
output/predicted_camera_when_none_given.md and output/depth_vs_altitude.png. Nothing is estimated: every number is
computed from the saved per-frame depths.
"""
import csv
import statistics
import sys
from pathlib import Path

import numpy as np
from scipy import stats

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
MODELS = [("unidepth", "UniDepthV2 (ViT-L)"), ("moge2", "MoGe-2 (ViT-L normal)"), ("moge2aerial", "MoGe2-Aerial (LoRA)")]
SETTING_LABEL = {"given_80": "camera given, 80 deg diag (72.4 deg H)", "given_71": "camera given, 71 deg diag (63.7 deg H)",
                 "given_94": "camera given, 94 deg diag (86.1 deg H)", "none": "no camera (model guesses)"}
ORDER = ["given_80", "none", "given_71", "given_94"]


def load_da3():
    rows = list(csv.DictReader(open(HERE / "da3_reference_clean.csv")))
    return {int(r["frame"]): (float(r["log_altitude_m"]), float(r["da3_depth_m"])) for r in rows}


def load_model(key):
    path = OUT / f"{key}_raw.csv"
    if not path.exists():
        return {}
    by = {}
    for r in csv.DictReader(open(path)):
        by.setdefault(r["setting"], {})[int(r["frame"])] = (float(r["log_altitude_m"]), float(r["depth_m"]), r)
    return by


def vehicle_counts(data_dir="data_check"):
    """Labelled vehicles (car, truck, van, bus, trailer) per frame, from the AU-AIR annotations (counts only, no images).

    Cached in vehicle_counts.csv so the analysis also runs without the dataset.
    """
    cache = HERE / "vehicle_counts.csv"
    if cache.exists():
        return {int(r["frame"]): int(r["vehicles"]) for r in csv.DictReader(open(cache))}
    import json
    ann = {a["image_name"]: a for a in json.load(open(Path(data_dir) / "annotations.json"))["annotations"]}
    counts = {}
    for r in csv.DictReader(open(HERE / "clean_frames.csv")):
        boxes = ann[f"frame_20190829091111_x_{int(r['frame']):07d}.jpg"]["bbox"]
        counts[int(r["frame"])] = sum(b["class"] in (1, 2, 3, 6, 7) for b in boxes)
    with open(cache, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame", "vehicles"])
        w.writerows(sorted(counts.items()))
    return counts


def summarise(alt, est):
    alt, est = np.asarray(alt, float), np.asarray(est, float)
    err = 100 * (est - alt) / alt
    lr = stats.linregress(alt, est)
    pr, pp = stats.pearsonr(alt, est)
    sr, sp = stats.spearmanr(alt, est)
    return {"n": len(alt), "median_err": float(np.median(err)), "min_err": float(err.min()), "max_err": float(err.max()),
            "slope": float(lr.slope), "pearson": float(pr), "pearson_p": float(pp), "spearman": float(sr), "spearman_p": float(sp),
            "median_ratio": float(np.median(est / alt))}


def main():
    da3 = load_da3()
    rows = [("DA3-Metric-Large (earlier run)", "camera given, 80 deg diag (72.4 deg H)", summarise(*zip(*da3.values())), None)]
    series = {"DA3-Metric-Large (earlier run)": list(da3.values())}
    pred_rows = []
    for key, label in MODELS:
        by = load_model(key)
        for setting in ORDER:
            if setting not in by:
                continue
            frames = by[setting]
            if len(frames) != 30:
                print(f"WARNING: {key}/{setting} has {len(frames)} of 30 frames", file=sys.stderr)
            alt, est = zip(*[(v[0], v[1]) for v in frames.values()])
            rows.append((label, SETTING_LABEL[setting], summarise(alt, est), None))
            if setting == "given_80":
                series[label] = list(zip(alt, est))
            if setting == "none":
                f = [float(v[2]["pred_focal_px"]) for v in frames.values()]
                h = [float(v[2]["pred_hfov_deg"]) for v in frames.values()]
                d = [float(v[2]["pred_diag_fov_deg"]) for v in frames.values()]
                pred_rows.append((label, statistics.median(f), min(f), max(f), statistics.median(h), statistics.median(d), min(d), max(d)))

    cols = ["Model", "Setting", "n", "Median % error", "% error range", "Slope (m/m)", "Pearson r (p)", "Spearman rho (p)", "Median est/log"]
    table = [[m, s, str(x["n"]), f"{x['median_err']:+.1f}", f"{x['min_err']:+.0f} to {x['max_err']:+.0f}", f"{x['slope']:.2f}",
              f"{x['pearson']:.2f} ({x['pearson_p']:.3f})", f"{x['spearman']:.2f} ({x['spearman_p']:.3f})", f"{x['median_ratio']:.2f}"]
             for m, s, x, _ in rows]
    OUT.mkdir(exist_ok=True)
    with open(OUT / "comparison_table.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "setting", "n", "median_pct_error", "min_pct_error", "max_pct_error", "slope_m_per_m", "pearson_r",
                    "pearson_p", "spearman_rho", "spearman_p", "median_est_over_log"])
        for m, s, x, _ in rows:
            w.writerow([m, s, x["n"], f"{x['median_err']:.2f}", f"{x['min_err']:.2f}", f"{x['max_err']:.2f}", f"{x['slope']:.4f}",
                        f"{x['pearson']:.4f}", f"{x['pearson_p']:.4f}", f"{x['spearman']:.4f}", f"{x['spearman_p']:.4f}", f"{x['median_ratio']:.4f}"])
    md = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)] + ["| " + " | ".join(r) + " |" for r in table]
    (OUT / "comparison_table.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    if pred_rows:
        pm = ["| Model | median predicted focal (px @1920) | range | median H-FOV | median diag FOV | diag FOV range |", "|---|---|---|---|---|---|"]
        pm += [f"| {m} | {f:.0f} | {lo:.0f}-{hi:.0f} | {h:.1f} deg | {d:.1f} deg | {dlo:.1f}-{dhi:.1f} deg |" for m, f, lo, hi, h, d, dlo, dhi in pred_rows]
        pm.append(f"\nFor reference: assumed 80 deg diag = 1312.7 px / 72.4 deg H; landmark check 71-94 deg diag.")
        (OUT / "predicted_camera_when_none_given.md").write_text("\n".join(pm) + "\n")
        print("\n" + "\n".join(pm))
    split_by_scene_content(da3, load_model)
    plot(series)


def split_by_scene_content(da3, loader):
    """POST-HOC (found after the main results): do errors differ between frames with and without vehicles in view?"""
    counts = vehicle_counts()
    groups = {"no labelled vehicle in frame": lambda c: c == 0, "vehicles in frame": lambda c: c > 0}
    out = ["Post hoc, not pre-specified: the same statistics split by whether the frame contains any labelled vehicle.",
           "Small groups (see n): read the medians, not the p-values.", "",
           "| Model | Setting | Frames | n | Median % error | Slope (m/m) | Pearson r (p) |", "|---|---|---|---|---|---|---|"]
    sources = [("DA3-Metric-Large (earlier run)", "given_80", {f: (a, d) for f, (a, d) in da3.items()})]
    for key, label in MODELS:
        by = loader(key)
        for setting in ("given_80", "none"):
            if setting in by:
                sources.append((label, setting, {f: (v[0], v[1]) for f, v in by[setting].items()}))
    for label, setting, data in sources:
        for gname, test in groups.items():
            pts = [v for f, v in data.items() if test(counts[f])]
            if len(pts) < 4:
                continue
            x = summarise(*zip(*pts))
            out.append(f"| {label} | {SETTING_LABEL[setting]} | {gname} | {x['n']} | {x['median_err']:+.1f} | {x['slope']:.2f} | {x['pearson']:.2f} ({x['pearson_p']:.3f}) |")
    (OUT / "comparison_by_scene_content.md").write_text("\n".join(out) + "\n")
    print("\n" + "\n".join(out))


def plot(series):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    surface, ink, ink2, grid = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
    colours = {"DA3-Metric-Large (earlier run)": "#8a8985", "UniDepthV2 (ViT-L)": "#2a78d6",
               "MoGe-2 (ViT-L normal)": "#eb6834", "MoGe2-Aerial (LoRA)": "#1baf7a"}
    markers = {"DA3-Metric-Large (earlier run)": "s", "UniDepthV2 (ViT-L)": "o", "MoGe-2 (ViT-L normal)": "^", "MoGe2-Aerial (LoRA)": "D"}
    fig, ax = plt.subplots(figsize=(8.2, 6.4), dpi=160, facecolor=surface)
    ax.set_facecolor(surface)
    top = max(max(e for _, e in pts) for pts in series.values())
    lim = np.ceil(max(top, 30) / 5) * 5
    ax.plot([0, lim], [0, lim], linestyle="--", linewidth=1.2, color=ink2, zorder=1, label="y = x  (depth equals altitude)")
    for name, pts in series.items():
        a, e = np.array(pts).T
        ax.scatter(a, e, s=34, marker=markers[name], color=colours[name], edgecolor=surface, linewidth=0.8, alpha=0.95, zorder=3,
                   label=f"{name}  (slope {np.polyfit(a, e, 1)[0]:.2f})")
        k, b = np.polyfit(a, e, 1)
        xs = np.array([a.min(), a.max()])
        ax.plot(xs, k * xs + b, color=colours[name], linewidth=1.3, alpha=0.8, zorder=2)
    ax.set_xlim(10, 31)
    ax.set_ylim(0, lim)
    ax.set_xlabel("Logged altitude (m)", color=ink2)
    ax.set_ylabel("Estimated depth, median of central 30% (m)", color=ink2)
    ax.set_title("Metric depth vs flight-log altitude, 30 near-nadir AU-AIR frames\n(camera given: 80 deg diagonal FOV)", color=ink, fontsize=11, loc="left")
    ax.grid(True, color=grid, linewidth=0.7)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(grid)
    ax.tick_params(colors=ink2)
    leg = ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=ink)
    fig.tight_layout()
    fig.savefig(OUT / "depth_vs_altitude.png", facecolor=surface)
    print(f"wrote {OUT / 'depth_vs_altitude.png'}")


if __name__ == "__main__":
    sys.exit(main())
