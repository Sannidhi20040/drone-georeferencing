"""Step 3: what diagonal field of view makes the pipeline's adjacent-bay distance equal the satellite measurement?

Inputs from the brief (NOT recomputed here): pipeline median adjacent-bay distance 3.33 m at 80 deg diagonal FOV,
satellite 2.905 m per bay (17.43 m across 6 bays). The one pair of adjacent bays in the saved questions that I can see
(frame 2713, A-B) is listed as a spot check.

For a camera pointing straight down (gimbal -90, as in this pipeline) a ground distance is  d = altitude * pixel_offset / f,
so d scales as 1/f exactly. The corrected truths are nevertheless recomputed through the real geometry (vlm_rotation.pixel_to_gps
on the saved pixel positions and the flight-log poses) and compared with the 1/f shortcut.
"""
import itertools
import json
import math
import statistics
import sys

import numpy as np

from common import OUT, ROOT, RUNS, load_model_rows, question_table, vlm

W, H = 1920, 1080
OLD_FOV = 80.0
PIPELINE_BAY_M = 3.33
SATELLITE_BAY_M = 17.43 / 6          # 2.905


def focal_from_diag(diag_deg):
    return (math.hypot(W, H) / 2) / math.tan(math.radians(diag_deg) / 2)


def diag_from_focal(f):
    return 2 * math.degrees(math.atan((math.hypot(W, H) / 2) / f))


def hfov_from_diag(diag_deg):
    return 2 * math.degrees(math.atan((W / math.hypot(W, H)) * math.tan(math.radians(diag_deg) / 2)))


def main():
    lines = ["## a) Diagonal FOV that makes the adjacent-bay distance 2.905 m", ""]
    f_old = focal_from_diag(OLD_FOV)
    scale = SATELLITE_BAY_M / PIPELINE_BAY_M                       # d_new / d_old
    f_new = f_old / scale                                          # d is proportional to 1/f
    fov_new = diag_from_focal(f_new)
    lines += [
        f"1. Satellite bay width = 17.43 m / 6 = {SATELLITE_BAY_M:.4f} m. Pipeline adjacent-bay distance (from the brief) = {PIPELINE_BAY_M} m at {OLD_FOV:g} deg.",
        f"2. Focal length from the diagonal: f = (hypot(1920, 1080) / 2) / tan(FOV / 2). hypot = {math.hypot(W, H):.2f} px, so f(80 deg) = {math.hypot(W, H) / 2:.2f} / tan(40 deg) = {f_old:.2f} px.",
        f"3. Distances scale as 1/f, so the distance ratio must be {SATELLITE_BAY_M:.4f} / {PIPELINE_BAY_M} = {scale:.5f} and the focal length must grow by 1 / {scale:.5f} = {1 / scale:.5f}: f_new = {f_old:.2f} x {1 / scale:.5f} = {f_new:.2f} px.",
        f"4. FOV_new = 2 atan((hypot / 2) / f_new) = 2 atan({math.hypot(W, H) / 2:.2f} / {f_new:.2f}) = **{fov_new:.2f} deg diagonal** "
        f"(horizontal {hfov_from_diag(fov_new):.2f} deg; the 80 deg setting is {hfov_from_diag(OLD_FOV):.2f} deg horizontal).",
        "Note the two 72.4 values are a coincidence of numbers: 72.4 deg is the DIAGONAL field of view implied by the bays, "
        "and also (almost exactly) the HORIZONTAL field of view of the 80 deg diagonal setting.",
        "Step 3b checks the 1/f shortcut against the real pixel-to-GPS geometry.", ""]

    # b) recompute every distance truth through the real geometry
    qt = question_table()
    derived = {fr["index"]: fr for fr in json.load(open(ROOT / "data_check" / "derived" / "20190829091111.json"))["frames"]}
    focal_old = vlm.diag_fov_to_focal_px(W, H, OLD_FOV)
    focal_new = vlm.diag_fov_to_focal_px(W, H, fov_new)

    def distance(q, focal):
        fr = derived[q["frame"]]
        pose = {"lat": fr["lat"], "lon": fr["lon"], "altitude": fr["altitude"], "heading": fr["yaw"] % 360, "gimbal_pitch": -90.0}
        a, b = q["pair"]
        pts = []
        for label in (a, b):
            g = vlm.pixel_to_gps(*q["objects"][label]["pixel"], pose, focal, (W, H))
            pts.append((g[0], g[1]))
        return vlm.haversine_m(*pts)

    metric = {qid: q for qid, q in qt.items() if q["type"] == "metric"}
    new_truth, rows_out, worst = {}, [], 0.0
    for qid, q in sorted(metric.items()):
        d_old = distance(q, focal_old)
        d_new = distance(q, focal_new)
        worst = max(worst, abs(d_old - q["truth"]), abs(d_new - d_old * scale))
        new_truth[qid] = d_new
        rows_out.append((qid, q["truth"], d_old, d_new))
    ratios = [d_new / d_old for _, _, d_old, d_new in rows_out]
    lines += ["## b) Corrected ground truth for the 24 distance questions", "",
              f"Recomputed with pixel_to_gps at {OLD_FOV:g} deg: matches the saved truths to within {worst:.4f} m (saved values are rounded to 0.01 m, so up to 0.005 m). "
              f"New / old distance ratio across all 24 questions: min {min(ratios):.5f}, max {max(ratios):.5f} (expected {scale:.5f} for every one, because the camera looks straight down).", "",
              "| Question | Old truth (m) | Corrected truth (m) |", "|---|---|---|"]
    lines += [f"| {qid} | {old:.2f} | {new:.2f} |" for qid, old, _, new in rows_out]
    spot = [r for r in rows_out if r[0] == "f2713-met-AB"]
    if spot:
        lines += ["", f"Spot check, frame 2713 A-B (adjacent bays): {spot[0][1]:.2f} m old, {spot[0][3]:.2f} m corrected (satellite {SATELLITE_BAY_M:.3f} m)."]

    # comparison questions: ordering is invariant; the 3 m rule may not be
    cmp_q = [q for q in qt.values() if q["type"] == "comparison"]
    keep_rule = 0
    for q in cmp_q:
        a = q["anchor"]
        d = []
        for o in q["options"]:
            pair = {"frame": q["frame"], "pair": [a, o], "objects": q["objects"]}
            d.append(distance(pair, focal_new))
        keep_rule += vlm.comparison_is_valid(*d)
    lines += ["", f"Comparison questions ({len(cmp_q)}): the nearer option cannot change (every distance is multiplied by the same factor), so the "
                  f"truths and accuracies are unchanged. With corrected distances {keep_rule} of {len(cmp_q)} would still satisfy the original "
                  "'differ by >= 30 % and >= 3 m' rule (the 3 m part gets harder when distances shrink); no comparison question was changed or re-scored."]

    # model errors old vs new
    lines += ["", "## c) Each model's distance error, old vs corrected truth", "",
              "| Model | Median abs. error, old | Median abs. error, corrected | Median signed error, old | Median signed error, corrected | Median rotation spread (old = corrected) |",
              "|---|---|---|---|---|---|"]
    for label, folder, model in RUNS:
        rows = [r for r in load_model_rows(folder, model) if r["type"] == "metric" and r["answer"] is not None]
        old_abs = [abs(r["answer"] - r["truth"]) / r["truth"] * 100 for r in rows]
        old_sg = [(r["answer"] - r["truth"]) / r["truth"] * 100 for r in rows]
        new_abs = [abs(r["answer"] - new_truth[r["qid"]]) / new_truth[r["qid"]] * 100 for r in rows]
        new_sg = [(r["answer"] - new_truth[r["qid"]]) / new_truth[r["qid"]] * 100 for r in rows]
        by_q = {}
        for r in load_model_rows(folder, model):
            if r["type"] == "metric":
                by_q.setdefault(r["qid"], {})[r["rotation"]] = r["answer"]
        sp = [(max(v.values()) - min(v.values())) / statistics.median(v.values()) * 100
              for v in by_q.values() if len(v) == 4 and all(x is not None for x in v.values())]
        lines.append(f"| {label} | {statistics.median(old_abs):.1f}% | {statistics.median(new_abs):.1f}% | {statistics.median(old_sg):+.1f}% | "
                     f"{statistics.median(new_sg):+.1f}% | {statistics.median(sp):.1f}% |")
    lines += ["", "The rotation spread depends only on the models' own answers, so it cannot change; it is recomputed here from the answers and equals the step 1 value.",
              "", "**Circularity:** this calibration uses the bay width of the same car park the corrected truths are applied to, so it is a correction "
              "to the scale, not an independent check of the pipeline. It also assumes the brief's 3.33 m (pipeline median adjacent-bay distance) and "
              "satellite 2.905 m are right, and that one scale factor applies to every frame (the earlier landmark pilot found per-frame scale errors of about +-10 %)."]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "step3_fov_calibration.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
