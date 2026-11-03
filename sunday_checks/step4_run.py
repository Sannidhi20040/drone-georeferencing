"""Step 4 (paid, Claude Haiku 5.5 only): noise floor and square-crop rotation spread for the 24 distance questions.

    export ANTHROPIC_API_KEY=...           # environment only; never written to disk
    python sunday_checks/step4_run.py --dry-run     # plan + cost estimate, no API call
    python sunday_checks/step4_run.py               # the run (resumes if interrupted)

Noise floor: every distance question asked 4 times on the UNROTATED image (the exact image bytes and prompt used in the
pilot, checked by SHA-1), same settings as the pilot (no temperature sent; Haiku 5.5 rejects temperature 0), except
max_tokens 2048 instead of 1024 (2 of 96 replies were cut off at 1024 in an earlier run).
Square crops: a fixed 1080x1080 square centred on the frame (x 420-1500, y 0-1080) for each question whose two labelled
objects both lie inside it; crop first, rotate, then draw the markers, so labels stay upright. Questions that cannot fit
are listed and skipped. Each fitting question is asked at 0/90/180/270 degrees.
Spend is tracked from the reported token usage; the run stops before exceeding --cap (default US$0.30).
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from common import OUT, ROOT, load_model_rows, question_table, vlm

MODEL = "claude-haiku-5-5"
PRICE_IN, PRICE_OUT = 0.10 / 1e6, 0.50 / 1e6
X0, X1, Y0, Y1, SIDE = 420, 1500, 0, 1080, 1080
RAW = OUT / "step4_raw_responses.jsonl"
IMG_DIR = OUT / "step4_images"


def build_jobs():
    qt = question_table("vlm_rotation_haiku55")
    metric = {k: q for k, q in qt.items() if q["type"] == "metric"}
    pilot = {(r["qid"], r["rotation"]): r for r in load_model_rows("vlm_rotation_haiku55", MODEL) if r["type"] == "metric"}
    jobs, skipped = [], []
    for qid, q in sorted(metric.items()):
        prompt = pilot[(qid, 0)]["prompt"]
        jobs += [{"kind": "noise", "qid": qid, "rotation": 0, "repeat": k, "frame": q["frame"], "prompt": prompt,
                  "image_path": ROOT / "pilot" / "output" / "vlm_rotation_haiku55" / "images" / f"{qid}_rot0.jpg",
                  "expect_sha1": pilot[(qid, 0)]["image_sha1"]} for k in range(4)]
        pts = {l: q["objects"][l]["pixel"] for l in q["pair"]}
        if all(X0 <= x <= X1 and Y0 <= y <= Y1 for x, y in pts.values()):
            jobs += [{"kind": "square", "qid": qid, "rotation": rot, "repeat": 0, "frame": q["frame"], "prompt": prompt,
                      "frame_image": q["scene"]["image"], "points": pts} for rot in (0, 90, 180, 270)]
        else:
            skipped.append(qid)
    return jobs, skipped


def image_bytes(job, data_dir):
    if job["kind"] == "noise":
        data = Path(job["image_path"]).read_bytes()
        assert hashlib.sha1(data).hexdigest() == job["expect_sha1"], f"{job['qid']}: saved image differs from the pilot's"
        return data
    from PIL import Image
    img = Image.open(Path(data_dir) / "images" / job["frame_image"]).convert("RGB")
    crop = img.crop((X0, Y0, X0 + SIDE, Y0 + SIDE))
    shifted = {l: (x - X0, y - Y0) for l, (x, y) in job["points"].items()}
    view = vlm.render_view(crop, shifted, job["rotation"], max_edge=vlm.DEFAULT_MAX_EDGE)    # rotate first, then draw markers
    data = vlm.jpeg_bytes(view)
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    (IMG_DIR / f"{job['qid']}_square_rot{job['rotation']}.jpg").write_bytes(data)
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cap", type=float, default=0.30, help="stop before spending more than this many US$ (default 0.30)")
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--data", default=str(ROOT / "data_check"))
    args = ap.parse_args()
    jobs, skipped = build_jobs()
    done = {}
    if RAW.exists():
        for line in RAW.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if not r.get("error"):
                    done[(r["kind"], r["qid"], r["rotation"], r["repeat"])] = r
    todo = [j for j in jobs if (j["kind"], j["qid"], j["rotation"], j["repeat"]) not in done]
    pilot_rows = [r for r in load_model_rows("vlm_rotation_haiku55", MODEL) if r["type"] == "metric"]
    est = sum(r["usage"]["input_tokens"] * PRICE_IN + r["usage"]["output_tokens"] * PRICE_OUT for r in pilot_rows) / len(pilot_rows)
    print(f"{len(jobs)} calls planned ({sum(j['kind'] == 'noise' for j in jobs)} noise-floor, {sum(j['kind'] == 'square' for j in jobs)} square-crop); "
          f"{len(done)} already done, {len(todo)} to run; skipped (do not fit a square): {len(skipped)}")
    print(f"estimated cost of the remaining calls: US${len(todo) * est:.3f} (mean US${est:.4f}/call from the pilot's own usage); cap US${args.cap:.2f}")
    if args.dry_run or not todo:
        return 0

    provider = vlm.AnthropicProvider(MODEL, temperature=None, max_tokens=args.max_tokens)
    spent = sum(r["usage"].get("input_tokens", 0) * PRICE_IN + r["usage"].get("output_tokens", 0) * PRICE_OUT for r in done.values())
    OUT.mkdir(parents=True, exist_ok=True)
    stopped = False
    with open(RAW, "a") as fh:
        for n, job in enumerate(todo, 1):
            if spent + 3 * est > args.cap:                       # leave room for a worse-than-average call
                print(f"STOP: spent US${spent:.4f}, next call could pass the US${args.cap:.2f} cap")
                stopped = True
                break
            data = image_bytes(job, args.data)
            t0 = time.time()
            error = None
            try:
                reply = provider.ask(data, job["prompt"])
            except Exception as e:                                # recorded; a re-run retries it
                reply, error = {"text": "", "stop_reason": None, "usage": {}, "response": None}, f"{type(e).__name__}: {e}"
            answer, conf, perr = vlm.parse_response(reply["text"], {"type": "metric"}) if not error else (None, None, error)
            cost = reply["usage"].get("input_tokens", 0) * PRICE_IN + reply["usage"].get("output_tokens", 0) * PRICE_OUT
            spent += cost
            fh.write(json.dumps({"kind": job["kind"], "qid": job["qid"], "frame": job["frame"], "rotation": job["rotation"],
                                 "repeat": job["repeat"], "model": MODEL, "temperature": None, "max_tokens": args.max_tokens,
                                 "prompt": job["prompt"], "image_sha1": hashlib.sha1(data).hexdigest(),
                                 "raw_text": reply["text"], "stop_reason": reply["stop_reason"], "usage": reply["usage"],
                                 "response": reply["response"], "answer": answer, "confidence": conf, "parse_error": perr,
                                 "error": error, "cost_usd": round(cost, 6), "seconds": round(time.time() - t0, 2),
                                 "time": time.strftime("%Y-%m-%dT%H:%M:%S%z")}) + "\n")
            fh.flush()
            if n % 20 == 0 or n == len(todo):
                print(f"  {n}/{len(todo)}  spent so far US${spent:.4f}", flush=True)
    print(f"done{' (stopped early)' if stopped else ''}: spent US${spent:.4f} this and earlier sessions; raw responses in {RAW}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
