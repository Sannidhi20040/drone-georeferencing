"""Step 5 (paid for Anthropic models, free for Qwen): repeat-to-repeat noise of the temperature-0 models.

    export ANTHROPIC_API_KEY=...
    python sunday_checks/step5_noise_floor.py --dry-run
    python sunday_checks/step5_noise_floor.py --models haiku45 sonnet46      # paid
    python sunday_checks/step5_noise_floor.py --models qwen                  # free, needs `ollama serve`
    python sunday_checks/step5_noise_floor.py --analyze

Each distance question is asked again, 4 times, on the UNROTATED image with the pilot's own prompt, the same saved image bytes
(SHA-1 checked), the pilot's settings (temperature 0, max_tokens 1024; Qwen: temperature 0, seed 0, format json).
Fixed in advance: Haiku 4.5 and Qwen get all 24 questions; Sonnet 4.6 gets every 12th question in sorted order (2 questions: 8 calls),
because its distance calls cost about US$0.010 each (first planned as every 8th = 3 questions, cut for cost before any call was made). Spend is tracked from reported usage; the run stops before exceeding --cap.
"""
import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

from common import N_BOOT, OUT, ROOT, SEED, fmt_ci, load_model_rows, percentile_ci, question_table, vlm
from step4_analyze import boot, per_question, spread

RAW = OUT / "step5_raw_responses.jsonl"
MODELS = {   # key -> (label, pilot folder, model id, provider, $/M input, $/M output, question stride)
    "haiku45": ("Haiku 4.5", "vlm_rotation", "claude-haiku-4-5", "anthropic", 1.0, 5.0, 1),
    "sonnet46": ("Sonnet 4.6", "vlm_rotation_claude46", "claude-sonnet-4-6", "anthropic", 3.0, 15.0, 12),
    "qwen": ("Qwen2.5-VL 3B", "vlm_rotation", "qwen2.5vl:3b", "ollama", 0.0, 0.0, 1),
}
REPEATS = 4


def jobs_for(key):
    label, folder, model, provider, pin, pout, stride = MODELS[key]
    qt = question_table(folder)
    qids = sorted(q for q, v in qt.items() if v["type"] == "metric")[::stride]
    pilot = {(r["qid"], r["rotation"]): r for r in load_model_rows(folder, model) if r["type"] == "metric"}
    out = []
    for qid in qids:
        p = pilot[(qid, 0)]
        out += [{"key": key, "qid": qid, "frame": qt[qid]["frame"], "repeat": k, "prompt": p["prompt"],
                 "image_path": ROOT / "pilot" / "output" / folder / "images" / p["image"], "expect_sha1": p["image_sha1"],
                 "pilot_rot0_answer": p["answer"]} for k in range(REPEATS)]
    return out


def mean_cost(key):
    label, folder, model, provider, pin, pout, stride = MODELS[key]
    rows = [r for r in load_model_rows(folder, model) if r["type"] == "metric"]
    return statistics.mean(r["usage"].get("input_tokens", 0) * pin / 1e6 + r["usage"].get("output_tokens", 0) * pout / 1e6 for r in rows)


def run(keys, dry, cap):
    done = {}
    if RAW.exists():
        for line in RAW.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if not r["error"]:
                    done[(r["key"], r["qid"], r["repeat"])] = r
    spent = sum(r["cost_usd"] for r in done.values())
    plan = {k: [j for j in jobs_for(k) if (k, j["qid"], j["repeat"]) not in done] for k in keys}
    for k in keys:
        est = mean_cost(k)
        print(f"{MODELS[k][0]:14s} {len(plan[k]):3d} calls to run, about US${len(plan[k]) * est:.3f} (mean US${est:.4f}/call from its pilot usage)")
    total = sum(len(plan[k]) * mean_cost(k) for k in keys)
    print(f"estimated total US${total:.3f}; cap US${cap:.2f}; already spent in earlier sessions of this step US${spent:.4f}")
    if dry:
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    with open(RAW, "a") as fh:
        for k in keys:
            label, folder, model, provider, pin, pout, stride = MODELS[k]
            if not plan[k]:
                continue
            if provider == "anthropic":
                prov = vlm.AnthropicProvider(model, temperature=0.0, max_tokens=1024)
            else:
                prov = vlm.OllamaProvider(model, temperature=0.0, max_tokens=1024)
                prov.check()
            est = mean_cost(k)
            for n, job in enumerate(plan[k], 1):
                if spent + 3 * est > cap:
                    print(f"STOP at US${spent:.4f}: next call could pass the US${cap:.2f} cap")
                    return 0
                data = Path(job["image_path"]).read_bytes()
                assert hashlib.sha1(data).hexdigest() == job["expect_sha1"], f"{job['qid']}: image differs from the pilot's"
                t0, error = time.time(), None
                try:
                    reply = prov.ask(data, job["prompt"])
                except Exception as e:
                    reply, error = {"text": "", "stop_reason": None, "usage": {}, "response": None}, f"{type(e).__name__}: {e}"
                answer, conf, perr = vlm.parse_response(reply["text"], {"type": "metric"}) if not error else (None, None, error)
                u = reply["usage"]
                cost = (u.get("input_tokens") or 0) * pin / 1e6 + (u.get("output_tokens") or 0) * pout / 1e6
                spent += cost
                fh.write(json.dumps({"key": k, "model": model, "qid": job["qid"], "frame": job["frame"], "repeat": job["repeat"],
                                     "rotation": 0, "temperature": 0.0, "max_tokens": 1024, "prompt": job["prompt"],
                                     "image_sha1": job["expect_sha1"], "pilot_rot0_answer": job["pilot_rot0_answer"],
                                     "raw_text": reply["text"], "stop_reason": reply["stop_reason"], "usage": u,
                                     "response": reply["response"], "answer": answer, "confidence": conf, "parse_error": perr,
                                     "error": error, "cost_usd": round(cost, 6), "seconds": round(time.time() - t0, 2),
                                     "time": time.strftime("%Y-%m-%dT%H:%M:%S%z")}) + "\n")
                fh.flush()
                if n % 20 == 0 or n == len(plan[k]):
                    print(f"  {label}: {n}/{len(plan[k])}  total spent US${spent:.4f}", flush=True)
    print(f"done; total spent on this step US${spent:.4f}")
    return 0


def analyze():
    raw = [json.loads(l) for l in open(RAW) if l.strip()]
    ok = [r for r in raw if not r["error"]]
    lines = [f"Noise floor of the temperature-0 models: 4 repeats on the unrotated image, pilot prompt and settings. "
             f"Median distance spread [95% cluster-bootstrap over frames, {N_BOOT} resamples, seed {SEED}].", "",
             "| Model | Questions | Repeat-to-repeat spread (noise floor) | Pilot rotation spread, same questions | Questions with 4 identical repeats | Repeats equal to the pilot's 0 deg answer |",
             "|---|---|---|---|---|---|"]
    for k, (label, folder, model, provider, *_rest) in MODELS.items():
        rows = [r for r in ok if r["key"] == k]
        if not rows:
            continue
        nz, dropped = per_question(rows, lambda r: r["repeat"])
        pilot = [r for r in load_model_rows(folder, model) if r["type"] == "metric" and r["qid"] in {r2["qid"] for r2 in rows}]
        orig, _ = per_question(pilot, lambda r: r["rotation"])
        orig = {q: v for q, v in orig.items() if q in nz}
        p1, ci1, n1, f1 = boot(nz)
        p2, ci2, n2, f2 = boot(orig)
        ident = sum(len(set(v[1])) == 1 for v in nz.values())
        same_as_pilot = sum(r["answer"] == r["pilot_rot0_answer"] for r in rows)
        lines.append(f"| {label} | {n1} ({f1} frames) | {fmt_ci(p1, ci1, 0, True)} | {fmt_ci(p2, ci2, 0, True)} | {ident} of {n1} | {same_as_pilot} of {len(rows)} |")
        if dropped:
            lines.append(f"<!-- {label}: questions dropped for unparsed answers: {dropped} -->")
    lines += ["", f"API/Ollama errors: {sum(bool(r['error']) for r in raw)}. Spend recorded: US${sum(r['cost_usd'] for r in raw):.4f} over {len(raw)} calls."]
    (OUT / "step5_results.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", choices=list(MODELS), default=["haiku45", "sonnet46"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--analyze", action="store_true")
    ap.add_argument("--cap", type=float, default=0.30)
    args = ap.parse_args()
    return analyze() if args.analyze else run(args.models, args.dry_run, args.cap)


if __name__ == "__main__":
    sys.exit(main())
