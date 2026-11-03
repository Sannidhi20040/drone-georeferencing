"""Step 1: cluster-bootstrap intervals for the rotation pilot (resample whole frames, 12 per resample, 2,000 resamples).

Definitions (identical to pilot/vlm_rotation.py's report, so the point estimates reproduce the headline numbers):
  spread      per distance question answered at all 4 rotations: (max - min) / median of the 4 answers; median over questions
  error       median over all answered distance rows of |answer - truth| / truth
  accuracy    correct / all comparison rows (an unparsed reply counts as wrong)
  changed     share of comparison questions, answered at all 4 rotations, whose answers are not all identical
  spearman    rank correlation of stated confidence vs |distance error| over answered distance rows with a confidence
Resampling: the same frame draws are used for every model and statistic (paired), seed common.SEED.
"""
import statistics
import sys

import numpy as np
from scipy import stats

from common import (HEADLINE, N_BOOT, OUT, RUNS, SEED, fmt_ci, load_model_rows, load_questions, percentile_ci)


def items(rows):
    """Per-frame arrays for each statistic. Everything is keyed by frame so a bootstrap draw can re-assemble it."""
    rotations = sorted({r["rotation"] for r in rows})
    out = {k: {} for k in ("spread", "error", "correct", "changed", "conf_err")}

    def add(key, frame, value):
        out[key].setdefault(frame, []).append(value)

    by_q = {}
    for r in rows:
        by_q.setdefault(r["qid"], {})[r["rotation"]] = r
    for qid, d in by_q.items():
        first = next(iter(d.values()))
        complete = set(d) == set(rotations) and all(x["answer"] is not None for x in d.values())
        if first["type"] == "metric" and complete:
            vals = [x["answer"] for x in d.values()]
            mid = statistics.median(vals)
            add("spread", first["frame"], (max(vals) - min(vals)) / mid * 100 if mid > 0 else float("inf"))
        if first["type"] == "comparison" and complete:
            add("changed", first["frame"], int(len({x["answer"] for x in d.values()}) > 1))
    for r in rows:
        if r["type"] == "metric" and r["answer"] is not None:
            err = abs(r["answer"] - r["truth"]) / r["truth"] * 100
            add("error", r["frame"], err)
            if r["confidence"] is not None:
                add("conf_err", r["frame"], (r["confidence"], err))
        if r["type"] == "comparison":
            add("correct", r["frame"], int(r["answer"] == r["truth"]))
    return out


def gather(d, frames):
    parts = [np.asarray(d.get(f, []), float) for f in frames]
    parts = [p for p in parts if p.size]
    return np.concatenate(parts, axis=0) if parts else np.empty(0)


def stat_values(it, frames):
    spread = gather(it["spread"], frames)
    err = gather(it["error"], frames)
    cor = gather(it["correct"], frames)
    chg = gather(it["changed"], frames)
    ce = gather(it["conf_err"], frames)
    if ce.size >= 3 and len(set(ce[:, 0])) > 1 and len(set(ce[:, 1])) > 1:
        rho = float(stats.spearmanr(ce[:, 0], ce[:, 1])[0])
    else:
        rho = float("nan")
    return {
        "spread": float(np.median(spread)) if spread.size else float("nan"),
        "error": float(np.median(err)) if err.size else float("nan"),
        "accuracy": 100 * float(cor.mean()) if cor.size else float("nan"),
        "changed": 100 * float(chg.mean()) if chg.size else float("nan"),
        "spearman": rho,
    }


def main():
    frames_all = sorted({s["frame"] for s in load_questions("vlm_rotation")["scenes"]})
    assert len(frames_all) == 12, frames_all
    rng = np.random.default_rng(SEED)
    draws = rng.integers(0, len(frames_all), size=(N_BOOT, len(frames_all)))    # shared by every model

    table, check = [], []
    names = ["spread", "error", "accuracy", "changed", "spearman"]
    results = {}
    for label, folder, model in RUNS:
        it = items(load_model_rows(folder, model))
        point = stat_values(it, frames_all)
        boots = {n: [] for n in names}
        for row in draws:
            v = stat_values(it, [frames_all[i] for i in row])
            for n in names:
                boots[n].append(v[n])
        ci = {n: percentile_ci(boots[n]) for n in names}
        results[label] = (point, ci)
        table.append(f"| {label} | {fmt_ci(point['spread'], ci['spread'], 0, True)} | {fmt_ci(point['error'], ci['error'], 0, True)} | "
                      f"{fmt_ci(point['accuracy'], ci['accuracy'], 0, True)} | {fmt_ci(point['changed'], ci['changed'], 0, True)} | "
                      f"{fmt_ci(point['spearman'], ci['spearman'], 2)} |")
        nan_resamples = {n: ci[n][2] for n in names if ci[n][2]}
        if nan_resamples:
            table[-1] += f"  <!-- resamples where undefined: {nan_resamples} -->"

    head = ["| Model | Median distance spread across rotations | Median distance error vs pipeline | Comparison accuracy | Comparison answers changed by rotation | Spearman: confidence vs abs distance error |",
            "|---|---|---|---|---|---|"]
    lines = [f"Cluster bootstrap over the 12 frames, {N_BOOT} resamples, seed {SEED}; point estimate [95% percentile interval].", ""] + head + table

    # reproduction check against the headline numbers in the brief
    keymap = {"median distance spread %": "spread", "comparison accuracy %": "accuracy",
              "median distance error %": "error", "comparison answers changed %": "changed"}
    lines += ["", "Reproduction of the headline numbers (computed point estimate rounded to a whole percent vs the number in the brief):", "",
              "| Statistic | " + " | ".join(l for l, _, _ in RUNS) + " |", "|---|" + "---|" * len(RUNS)]
    all_match = True
    for name, expected in HEADLINE.items():
        got = [results[l][0][keymap[name]] for l, _, _ in RUNS]
        cells = []
        for g, e in zip(got, expected):
            ok = round(g) == e
            all_match &= ok
            cells.append(f"{g:.1f} vs {e}" + ("" if ok else " **DIFFERENT**"))
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("All headline numbers reproduce." if all_match else "Some headline numbers differ; see the marked cells and the notes below.")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "step1_rotation_bootstrap.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
