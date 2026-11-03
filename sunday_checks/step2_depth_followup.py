"""Step 2: depth-comparison follow-up at the 80-degree setting (depth_comparison/output/*_raw.csv, setting given_80).

a) bootstrap 95 % intervals (resample the 30 frames, 2,000 times) for median % error, slope and Pearson r
b) the frames with no labelled vehicle: id, altitude, position in the flight; Mann-Whitney U on altitude;
   permutation test for whether they are bunched in time
c) slope and r again after dropping the 3 lowest- and 3 highest-altitude frames
"""
import csv
import json
import sys

import numpy as np
from scipy import stats

from common import N_BOOT, OUT, ROOT, SEED, fmt_ci, percentile_ci

DEPTH = ROOT / "depth_comparison"
MODELS = [("UniDepthV2", "unidepth"), ("MoGe-2", "moge2"), ("MoGe2-Aerial", "moge2aerial")]


def load_all():
    """{label: {frame: (altitude, depth)}} for the 80 deg setting; DA3 from the saved reference copy."""
    out = {"DA3 (earlier run)": {int(r["frame"]): (float(r["log_altitude_m"]), float(r["da3_depth_m"]))
                                 for r in csv.DictReader(open(DEPTH / "da3_reference_clean.csv"))}}
    for label, key in MODELS:
        rows = [r for r in csv.DictReader(open(DEPTH / "output" / f"{key}_raw.csv")) if r["setting"] == "given_80"]
        out[label] = {int(r["frame"]): (float(r["log_altitude_m"]), float(r["depth_m"])) for r in rows}
    return out


def fit_stats(alt, depth):
    alt, depth = np.asarray(alt, float), np.asarray(depth, float)
    err = 100 * (depth - alt) / alt
    slope = float(np.polyfit(alt, depth, 1)[0]) if len(set(alt)) > 1 else float("nan")
    r = float(np.corrcoef(alt, depth)[0, 1]) if len(set(alt)) > 1 and len(set(depth)) > 1 else float("nan")
    return float(np.median(err)), slope, r


def main():
    data = load_all()
    frames = sorted(next(iter(data.values())))
    assert all(sorted(d) == frames for d in data.values()) and len(frames) == 30, "frame sets differ or are not 30"
    rng = np.random.default_rng(SEED)
    draws = rng.integers(0, 30, size=(N_BOOT, 30))                       # shared by all models
    lines = []

    # a) bootstrap
    lines += [f"## a) Bootstrap, 80 deg camera setting: 30 frames resampled with replacement, {N_BOOT} resamples, seed {SEED}",
              "", "Point estimate [95% percentile interval].", "",
              "| Model | Median % error | Slope (m of depth per m of altitude) | Pearson r |", "|---|---|---|---|"]
    for label, d in data.items():
        alt = np.array([d[f][0] for f in frames]); dep = np.array([d[f][1] for f in frames])
        point = fit_stats(alt, dep)
        boots = np.array([fit_stats(alt[i], dep[i]) for i in draws])
        cis = [percentile_ci(boots[:, k]) for k in range(3)]
        lines.append(f"| {label} | {fmt_ci(point[0], cis[0], 1, True)} | {fmt_ci(point[1], cis[1], 2)} | {fmt_ci(point[2], cis[2], 2)} |")

    # b) frames with no labelled vehicle
    counts = {int(r["frame"]): int(r["vehicles"]) for r in csv.DictReader(open(DEPTH / "vehicle_counts.csv"))}
    alt_of = {f: data["DA3 (earlier run)"][f][0] for f in frames}
    empty = [f for f in frames if counts[f] == 0]
    other = [f for f in frames if counts[f] > 0]
    clip = json.load(open(ROOT / "data_check" / "derived" / "20190829091111.json"))["frames"]
    last = max(fr["index"] for fr in clip)
    lines += ["", f"## b) The {len(empty)} frames with no labelled vehicle (vs the other {len(other)})", "",
              "Time = frame number / 5 fps, seconds from the start of the clip (frame numbering has a few gaps, so approximate); "
              f"the clip's last frame is {last} (about {last / 5:.0f} s).", "",
              "| Frame | Logged altitude (m) | Time into clip (s) | Position in clip |", "|---|---|---|---|"]
    for f in empty:
        lines.append(f"| {f} | {alt_of[f]:.1f} | {f / 5:.0f} | {100 * f / last:.0f}% |")
    u = stats.mannwhitneyu([alt_of[f] for f in empty], [alt_of[f] for f in other], alternative="two-sided")
    lines += ["", f"Median altitude: no-vehicle frames {np.median([alt_of[f] for f in empty]):.1f} m, other frames "
                  f"{np.median([alt_of[f] for f in other]):.1f} m. Mann-Whitney U = {u.statistic:.0f}, two-sided p = {u.pvalue:.3f}."]
    window = 150
    nums = np.array(frames)
    def max_in_window(mask):
        pos = nums[mask]
        return max(int(((pos >= s) & (pos < s + window)).sum()) for s in pos)
    mask = np.array([counts[f] == 0 for f in frames])
    observed = max_in_window(mask)
    perm_rng = np.random.default_rng(SEED)
    perms = [max_in_window(perm_rng.permutation(mask)) for _ in range(10000)]
    p_bunch = (1 + sum(x >= observed for x in perms)) / (1 + len(perms))
    gaps_sorted = np.diff(sorted(empty))
    lines += [f"Bunching: the most no-vehicle frames within any {window}-frame window ({window / 5:.0f} s) is {observed}; "
              f"with the 8 labels shuffled over the 30 frames (10,000 permutations, seed {SEED}) a stretch that "
              f"dense or denser occurs with probability {p_bunch:.3f}. Gaps between consecutive no-vehicle frames: "
              f"{', '.join(str(int(g)) for g in gaps_sorted)} frames."]

    # c) trim
    order = sorted(frames, key=lambda f: alt_of[f])
    keep = order[3:-3]
    lines += ["", f"## c) Dropping the 3 lowest- and 3 highest-altitude frames ({len(keep)} left; altitudes {alt_of[keep[0]]:.1f}-{alt_of[keep[-1]]:.1f} m)",
              "", f"Dropped: lowest {order[:3]} ({', '.join(f'{alt_of[f]:.1f}' for f in order[:3])} m), "
                  f"highest {order[-3:]} ({', '.join(f'{alt_of[f]:.1f}' for f in order[-3:])} m).", "",
              "| Model | Slope, all 30 | Slope, 24 kept | Pearson r, all 30 | Pearson r, 24 kept |", "|---|---|---|---|---|"]
    for label, d in data.items():
        a30 = [d[f][0] for f in frames]; d30 = [d[f][1] for f in frames]
        a24 = [d[f][0] for f in keep]; d24 = [d[f][1] for f in keep]
        _, s30, r30 = fit_stats(a30, d30); _, s24, r24 = fit_stats(a24, d24)
        lines.append(f"| {label} | {s30:.2f} | {s24:.2f} | {r30:.2f} | {r24:.2f} |")

    # d) separating scene content from altitude / flight segment (added after seeing a-c: the trim in c) also removes 3 empty frames)
    bunched = [f for f in empty if 1000 <= f <= 1200]
    isolated = [f for f in empty if f not in bunched]
    matched = [f for f in other if 19.0 <= alt_of[f] <= 20.0]
    lines += ["", "## d) Scene content vs altitude vs flight segment (added after a-c; exploratory)", "",
              f"Empty frames: the stretch of {len(bunched)} frames {bunched} (one hover at about 19.4 m, treat as one segment) and "
              f"{len(isolated)} isolated frames {isolated} (altitudes {', '.join(f'{alt_of[f]:.1f}' for f in isolated)} m, different parts of the flight). "
              f"Altitude-matched frames with vehicles (19.0-20.0 m): {matched} (n = {len(matched)}). Median % error per model:", "",
              "| Model | All 8 empty | 4 in the one stretch | 4 isolated | Vehicle frames, 19-20 m | All 22 vehicle frames | Mann-Whitney p, empty vs vehicle (% error, 8 vs 22) |",
              "|---|---|---|---|---|---|---|"]
    for label, d in data.items():
        e = {f: 100 * (d[f][1] - d[f][0]) / d[f][0] for f in frames}
        med = lambda fs: np.median([e[f] for f in fs]) if fs else float("nan")
        p = stats.mannwhitneyu([e[f] for f in empty], [e[f] for f in other], alternative="two-sided").pvalue
        lines.append(f"| {label} | {med(empty):+.0f}% | {med(bunched):+.0f}% | {med(isolated):+.0f}% | {med(matched):+.0f}% | {med(other):+.0f}% | {p:.3f} |")
    lines += ["", "Per-frame % error on the 8 empty frames:", "", "| Frame | Altitude (m) | " + " | ".join(data) + " |", "|---|---|" + "---|" * len(data)]
    for f in empty:
        lines.append(f"| {f} | {alt_of[f]:.1f} | " + " | ".join(f"{100 * (d[f][1] - d[f][0]) / d[f][0]:+.0f}%" for d in data.values()) + " |")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "step2_depth_followup.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
