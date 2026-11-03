"""Step 4 analysis (no API): original rotation spread vs noise-floor spread vs square-crop rotation spread, Claude Haiku 5.5.

Spread of a question = (max - min) / median of its 4 answers (4 rotations, or 4 repeats at 0 degrees). Reported statistic = median
over questions. Intervals: cluster bootstrap over frames (resample the frames that contribute questions, 2,000 times, seed
common.SEED); every question of a resampled frame comes along. Questions with any unparsed answer are left out and counted.
"""
import json
import statistics
import sys

import numpy as np

from common import N_BOOT, OUT, SEED, fmt_ci, load_model_rows, percentile_ci

MODEL = "claude-haiku-5-5"


def spread(values):
    mid = statistics.median(values)
    return (max(values) - min(values)) / mid * 100 if mid > 0 else float("inf")


def per_question(rows, key):
    """{qid: (frame, [answers])} keeping only questions whose 4 answers all parsed."""
    d, frame = {}, {}
    for r in rows:
        d.setdefault(r["qid"], {})[key(r)] = r["answer"]
        frame[r["qid"]] = r["frame"]
    out, dropped = {}, []
    for qid, v in d.items():
        if len(v) == 4 and all(x is not None for x in v.values()):
            out[qid] = (frame[qid], list(v.values()))
        else:
            dropped.append(qid)
    return out, dropped


def boot(items):
    """items {qid: (frame, answers)} -> point estimate and 95% interval of the median spread, cluster bootstrap by frame."""
    by_frame = {}
    for qid, (f, ans) in items.items():
        by_frame.setdefault(f, []).append(spread(ans))
    frames = sorted(by_frame)
    point = float(np.median([s for v in by_frame.values() for s in v]))
    rng = np.random.default_rng(SEED)
    vals = []
    for _ in range(N_BOOT):
        pick = rng.integers(0, len(frames), len(frames))
        vals.append(float(np.median([s for i in pick for s in by_frame[frames[i]]])))
    return point, percentile_ci(vals), len(items), len(frames)


def main():
    pilot = [r for r in load_model_rows("vlm_rotation_haiku55", MODEL) if r["type"] == "metric"]
    raw = [json.loads(l) for l in open(OUT / "step4_raw_responses.jsonl") if l.strip()]
    ok = [r for r in raw if not r["error"]]
    noise = [r for r in ok if r["kind"] == "noise"]
    square = [r for r in ok if r["kind"] == "square"]
    errors = [r for r in raw if r["error"]]
    orig, d_orig = per_question(pilot, lambda r: r["rotation"])
    nz, d_nz = per_question(noise, lambda r: r["repeat"])
    sq, d_sq = per_question(square, lambda r: r["rotation"])
    crop_qids = set(sq) | set(d_sq)
    orig10 = {q: v for q, v in orig.items() if q in crop_qids}
    nz10 = {q: v for q, v in nz.items() if q in crop_qids}

    rows = [("Original rotation spread, all distance questions", orig), ("Noise floor (4 repeats, unrotated), all distance questions", nz),
            ("Original rotation spread, the square-crop questions only", orig10), ("Noise floor, the square-crop questions only", nz10),
            ("Square-crop rotation spread", sq)]
    lines = [f"Claude Haiku 5.5, median distance spread [95% cluster-bootstrap interval over frames, {N_BOOT} resamples, seed {SEED}].", "",
             "| Measure | Median spread | Questions | Frames |", "|---|---|---|---|"]
    res = {}
    for name, items in rows:
        p, ci, nq, nf = boot(items)
        res[name] = p
        lines.append(f"| {name} | {fmt_ci(p, ci, 0, True)} | {nq} | {nf} |")
    lines += ["", f"Questions dropped for an unparsed answer: noise floor {d_nz}, square crop {d_sq}. API errors: {len(errors)}.",
              f"Stop reasons: {sorted({r['stop_reason'] for r in ok})}. Spend recorded: US${sum(r['cost_usd'] for r in raw):.4f} over {len(raw)} calls.",
              "", "Like-for-like (the 10 square-crop questions): "
              f"original {res['Original rotation spread, the square-crop questions only']:.1f}% | noise floor {res['Noise floor, the square-crop questions only']:.1f}% | "
              f"square-crop rotations {res['Square-crop rotation spread']:.1f}%."]
    # how big is the repeat noise relative to the rotation effect, per question
    lines += ["", "Per square-crop question (spread %): original rotations | noise floor | square-crop rotations", "",
              "| Question | Original | Noise floor | Square crop |", "|---|---|---|---|"]
    for q in sorted(crop_qids):
        cell = lambda d: f"{spread(d[q][1]):.0f}" if q in d else "n/a"
        lines.append(f"| {q} | {cell(orig)} | {cell(nz)} | {cell(sq)} |")
    (OUT / "step4_results.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
