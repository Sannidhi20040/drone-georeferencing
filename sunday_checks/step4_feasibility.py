"""Step 4 pre-check (NO API CALLS): is the key set, which distance questions fit a square centre crop, what would the run cost?

The paid run itself is deliberately not implemented here; it waits for an explicit "yes".

Square crop: the largest square that fits a 1920x1080 frame is 1080x1080. "Centre crop" = centred on the image centre
(960, 540), so it spans x in [420, 1500] and y in [0, 1080]. A question is feasible only if both labelled objects are inside it.
(A smaller crop can only hold fewer pairs, so the full 1080 square is the best case.)
"""
import os
import statistics
import sys

from common import OUT, RUNS, load_model_rows, question_table

PRICE_IN, PRICE_OUT = 0.10, 0.50          # US$ per million tokens, Claude Haiku 5.5, prompts <= 100K tokens (pricing page)
X0, X1, Y0, Y1 = 420, 1500, 0, 1080


def main():
    key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    qt = question_table()
    metric = {k: q for k, q in qt.items() if q["type"] == "metric"}
    ok, bad = [], []
    for qid, q in sorted(metric.items()):
        pts = [q["objects"][l]["pixel"] for l in q["pair"]]
        inside = all(X0 <= x <= X1 and Y0 <= y <= Y1 for x, y in pts)
        (ok if inside else bad).append((qid, pts))
    rows = [r for r in load_model_rows("vlm_rotation_haiku55", "claude-haiku-5-5") if r["type"] == "metric"]
    tin = statistics.mean(r["usage"]["input_tokens"] for r in rows)
    tout = statistics.mean(r["usage"]["output_tokens"] for r in rows)
    per_call = tin / 1e6 * PRICE_IN + tout / 1e6 * PRICE_OUT
    n_noise = len(metric) * 4
    n_crop = len(ok) * 4
    lines = [f"ANTHROPIC_API_KEY: {'set (value not shown)' if key else 'NOT set'}", "",
             f"Distance questions: {len(metric)}. Fit entirely inside the centred 1080x1080 square: {len(ok)}. Cannot fit: {len(bad)}.", ""]
    if bad:
        lines += ["Cannot fit (object pixel positions in the 1920x1080 frame):"] + [f"  {qid}: {pts}" for qid, pts in bad]
    lines += ["", f"Saved Haiku 5.5 distance calls: mean {tin:.0f} input / {tout:.0f} output tokens per call -> about US${per_call:.4f} per call at "
                  f"${PRICE_IN}/${PRICE_OUT} per million tokens.",
              f"Noise floor: {len(metric)} questions x 4 repeats = {n_noise} calls -> about US${n_noise * per_call:.3f}.",
              f"Square crops: {len(ok)} questions x 4 rotations = {n_crop} calls -> about US${n_crop * per_call:.3f} (the crop has fewer pixels than the 1568x882 frames, so this is if anything high).",
              f"Total about US${(n_noise + n_crop) * per_call:.3f}; hard stop at US$1.00."]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "step4_feasibility.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
