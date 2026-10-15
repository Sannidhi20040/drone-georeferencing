#!/usr/bin/env python3
"""Does a vision-language model keep its spatial answers when a drone frame is rotated?

For ~12 near-nadir frames of AU-AIR clip 20190829091111 this script

  1. runs the app's ONNX detector on the frame and georeferences each detection with the app's
     pixel -> GPS geometry (a Python port of src/geoConverter.js; test_vlm_rotation.py checks it
     against the JavaScript when node is available),
  2. picks 3-4 well-separated objects and computes their true pairwise ground distances from
     those GPS positions,
  3. writes comparison questions ("Which is closer to A: B or C?"), kept only when the two
     distances differ by >= 30 % and >= 3 m, and metric questions ("approximately how many
     metres apart are A and B?"),
  4. renders the frame at 0, 90, 180 and 270 degrees (clockwise) and draws the A/B/C/D markers
     AFTER rotating, so the labels stay upright and only the scene orientation changes,
  5. asks a model for {"answer": ..., "confidence": 0-100} at temperature 0 and saves every raw
     prompt and response,
  6. reports comparison accuracy, median % error on the metric questions, how often the answer
     changes with rotation, and accuracy for confidence >= 80 vs < 80.

Setup (the AU-AIR frames and `node scripts/au-air/prepare.mjs` output must exist locally):

    pip install numpy pillow onnxruntime anthropic
    export ANTHROPIC_API_KEY=...          # read from the environment only; never written to disk

    python pilot/vlm_rotation.py --select-only                       # build + inspect, no API calls
    python pilot/vlm_rotation.py --provider mock                     # whole pipeline, fake model
    python pilot/vlm_rotation.py --model claude-haiku-4-5            # real run (costs money)
    python pilot/vlm_rotation.py --provider ollama --model qwen2.5vl:3b   # free, local (needs `ollama serve`)
    python pilot/vlm_rotation.py --analyze-only --model claude-haiku-4-5

A re-run skips every (question, rotation) already answered in raw_responses.jsonl, so an
interrupted run resumes without paying twice.

Choosing the model:
  * --model is required for a live run; there is no default, so nothing is spent on a model you
    did not pick. Providers: anthropic (Messages API), ollama (local, free) and mock (no model).
    Another API is one more class with the same `ask` method.
  * temperature 0 is sent as asked. Per the Claude API docs, Opus 4.7 and later reject any request that
    carries a temperature, and Sonnet 5 / 5.5 reject non-default values, so those models cannot be run at
    temperature 0; the 4.6 / 4.5 generation (Opus 4.6, Sonnet 4.6, Haiku 4.5, ...) accepts it. If the API
    rejects it the script stops and says so. --temperature omit leaves it out (the run is then NOT
    temperature 0, and the report says "None").

What the "true" distances are, and are not:
  * They come from this app's georeferencing, not from a survey. The pilot in scripts/au-air
    measured ~2.6-12 % error on distances between points in one frame and per-frame scale errors
    of about +-10 %. That error is common to all distances in a frame, so it barely moves the
    ordering in a comparison question, but it does move the metric answers: treat metric errors
    below ~10-15 % as indistinguishable from the ground truth's own error.
  * Detections are also the model's, so a detector false positive can be a "car" in a question.
    Every scene is saved (questions.json plus the rendered images) for a visual check.

AU-AIR is licensed non-commercial. Rendered frames go to pilot/output/ (git-ignored); do not
commit them. Keys are never read from files or printed.
"""
import argparse
import base64
import csv
import hashlib
import io
import itertools
import json
import math
import os
import random
import statistics
import sys
import time
from pathlib import Path

CLIP = "20190829091111"
MODEL_PATH = "public/models/aerial_yolov8.onnx"
CLASS_NAMES = ["small-vehicle", "large-vehicle", "human"]    # order of the model's score channels
IMAGE_W, IMAGE_H = 1920, 1080
EARTH_RADIUS_M = 6371008.8                                   # @turf/helpers earthRadius, as used by rhumbDestination
DEFAULT_DIAG_FOV_DEG = 80.0                                  # as in da3_altitude.py; the app default is 84
MIN_DEPRESSION_DEG = 5.0

N_FRAMES = 12
TILT_LIMIT_DEG = 5.0
CONF_THRESHOLD = 0.5                                         # the app's default
MIN_REL_DIFF = 0.30                                          # "differ by >= 30 %": larger >= 1.30 x smaller
MIN_ABS_DIFF_M = 3.0
MIN_SEP_M = 3.0                                              # chosen objects at least this far apart on the ground
MIN_SEP_PX = 120.0                                           # ... and this far apart in the image, so markers do not collide
MAX_CANDIDATES = 12                                          # detections considered per frame when choosing objects
ROTATIONS = (0, 90, 180, 270)                                # degrees clockwise
LABELS = "ABCD"
CONFIDENCE_SPLIT = 80
DEFAULT_MAX_EDGE = 1568                                      # long side sent to the model (larger gets downscaled by the API anyway)
OUT_DIR = Path("pilot/output/vlm_rotation")


# --------------------------------------------------------------------------------------
# Geometry: Python port of src/geoConverter.js (pixelToGPS) and @turf/rhumb-destination
# --------------------------------------------------------------------------------------

def diag_fov_to_focal_px(width, height, diag_fov_deg):
    """Pinhole focal length in pixels, derived exactly as GeoConverter.calculateFOV does."""
    diag = math.hypot(width, height)
    tan_half = math.tan(math.radians(diag_fov_deg) / 2)
    fov_h = 2 * math.atan((width / diag) * tan_half)
    fov_v = 2 * math.atan((height / diag) * tan_half)
    return (width / 2) / math.tan(fov_h / 2), (height / 2) / math.tan(fov_v / 2)


def rhumb_destination(lat, lon, distance_m, bearing_deg):
    """@turf/rhumb-destination: point `distance_m` from (lat, lon) along a constant bearing."""
    delta = distance_m / EARTH_RADIUS_M
    phi1 = math.radians(lat)
    theta = math.radians(bearing_deg)
    dphi = delta * math.cos(theta)
    phi2 = phi1 + dphi
    if abs(phi2) > math.pi / 2:
        phi2 = math.copysign(math.pi - abs(phi2), phi2)
    dpsi = math.log(math.tan(phi2 / 2 + math.pi / 4) / math.tan(phi1 / 2 + math.pi / 4))
    q = dphi / dpsi if abs(dpsi) > 1e-12 else math.cos(phi1)
    dlambda = delta * math.sin(theta) / q
    lam2 = math.radians(lon) + dlambda
    return math.degrees(phi2), (math.degrees(lam2) + 540) % 360 - 180


def pixel_to_gps(x, y, pose, focal_xy, size=(IMAGE_W, IMAGE_H), min_depression_deg=MIN_DEPRESSION_DEG):
    """Cast the pixel's ray onto flat ground `pose['altitude']` m below the camera.

    pose: lat, lon, altitude (m above ground), heading (deg), gimbal_pitch (deg, -90 = straight down).
    Returns (lat, lon, distance_from_drone_m) or None when the ray does not reach the ground.
    """
    altitude = pose["altitude"]
    if not altitude > 0:
        return None
    pitch = pose.get("gimbal_pitch", -90.0)
    ray_x = (x - size[0] / 2) / focal_xy[0]
    ray_y = (y - size[1] / 2) / focal_xy[1]
    depression = math.radians(-pitch)
    forward = math.cos(depression) - ray_y * math.sin(depression)
    right = ray_x
    down = math.sin(depression) + ray_y * math.cos(depression)
    ray_length = math.sqrt(forward ** 2 + right ** 2 + down ** 2)
    if down / ray_length < math.sin(math.radians(min_depression_deg)):
        return None
    scale = altitude / down
    metres_x, metres_y = right * scale, forward * scale
    distance = math.hypot(metres_x, metres_y)
    angle = 0.0 if distance == 0 else math.degrees(math.atan2(metres_x, metres_y))
    bearing = (pose["heading"] + angle + 360) % 360
    lat, lon = rhumb_destination(pose["lat"], pose["lon"], distance, bearing)
    return lat, lon, distance


def haversine_m(p, q):
    """Great-circle distance in metres between (lat, lon) points."""
    phi1, phi2 = math.radians(p[0]), math.radians(q[0])
    a = (math.sin((phi2 - phi1) / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(math.radians(q[1] - p[1]) / 2) ** 2)
    return 2 * EARTH_RADIUS_M * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# --------------------------------------------------------------------------------------
# Detector: the app's ONNX model, same preprocessing and decoding as src/modelInference.js
# --------------------------------------------------------------------------------------

def letterbox(img, size=640):
    import numpy as np
    from PIL import Image
    w, h = img.size
    s = min(size / w, size / h)
    nw, nh = round(w * s), round(h * s)
    px, py = (size - nw) // 2, (size - nh) // 2
    canvas = Image.new("RGB", (size, size), (114, 114, 114))
    canvas.paste(img.resize((nw, nh), Image.BILINEAR), (px, py))
    return np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0, s, px, py


def box_iou(a, b):
    inter = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def nms(dets, threshold=0.45):
    """Class-aware NMS, highest confidence first."""
    keep = []
    for d in sorted(dets, key=lambda d: -d["conf"]):
        if all(k["cls"] != d["cls"] or box_iou(k["box"], d["box"]) <= threshold for k in keep):
            keep.append(d)
    return keep


def detect(session, image, conf=CONF_THRESHOLD):
    """Detections of a PIL image: dicts with cls (name), conf, box (x0, y0, x1, y1) and centre (x, y)."""
    import numpy as np
    width, height = image.size
    x, s, px, py = letterbox(image.convert("RGB"))
    out = session.run(None, {session.get_inputs()[0].name: x})[0][0]      # [7, 8400]
    scores = out[4:7]
    cls, best = scores.argmax(0), scores.max(0)
    dets = []
    for i in np.where(best >= conf)[0]:
        cx, cy = float((out[0, i] - px) / s), float((out[1, i] - py) / s)
        w, h = float(out[2, i] / s), float(out[3, i] / s)
        if not (0 <= cx <= width and 0 <= cy <= height):     # centred in the grey padding
            continue
        dets.append({"cls": int(cls[i]), "conf": float(best[i]),
                     "box": (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)})
    return [{"cls": CLASS_NAMES[d["cls"]], "conf": d["conf"], "box": d["box"],
             "x": (d["box"][0] + d["box"][2]) / 2, "y": (d["box"][1] + d["box"][3]) / 2}
            for d in nms(dets)]


# --------------------------------------------------------------------------------------
# Scenes and questions
# --------------------------------------------------------------------------------------

def relative_gap(d1, d2):
    """How much larger the bigger distance is than the smaller (0.3 = 30 % larger)."""
    lo, hi = sorted((d1, d2))
    return math.inf if lo == 0 else hi / lo - 1.0


def comparison_is_valid(d1, d2, min_rel=MIN_REL_DIFF, min_abs=MIN_ABS_DIFF_M):
    return relative_gap(d1, d2) >= min_rel and abs(d1 - d2) >= min_abs


def pairwise_distances(objects):
    """{(i, j): metres} for i < j, from the objects' GPS positions."""
    return {(i, j): haversine_m(objects[i]["gps"], objects[j]["gps"])
            for i, j in itertools.combinations(range(len(objects)), 2)}


def _dist(d, i, j):
    return d[(i, j)] if i < j else d[(j, i)]


def count_valid_comparisons(objects, min_rel=MIN_REL_DIFF, min_abs=MIN_ABS_DIFF_M):
    d = pairwise_distances(objects)
    n = len(objects)
    return sum(comparison_is_valid(_dist(d, a, b), _dist(d, a, c), min_rel, min_abs)
               for a in range(n) for b, c in itertools.combinations([i for i in range(n) if i != a], 2))


def choose_objects(candidates, k=4, min_sep_m=MIN_SEP_M, min_sep_px=MIN_SEP_PX,
                   max_candidates=MAX_CANDIDATES, min_rel=MIN_REL_DIFF, min_abs=MIN_ABS_DIFF_M):
    """The k (else 3) well-separated objects that allow the most valid comparison questions.

    candidates: dicts with pixel x, y, gps (lat, lon) and conf. Only the max_candidates most
    confident are considered. Deterministic: ties go to the higher total confidence.
    """
    pool = sorted(candidates, key=lambda c: -c["conf"])[:max_candidates]
    for size in dict.fromkeys((k, 3)):
        best, best_key = None, None
        for combo in itertools.combinations(range(len(pool)), size):
            objs = [pool[i] for i in combo]
            if any(haversine_m(a["gps"], b["gps"]) < min_sep_m
                   or math.hypot(a["x"] - b["x"], a["y"] - b["y"]) < min_sep_px
                   for a, b in itertools.combinations(objs, 2)):
                continue
            key = (count_valid_comparisons(objs, min_rel, min_abs), sum(o["conf"] for o in objs))
            if best_key is None or key > best_key:
                best, best_key = objs, key
        if best is not None and best_key[0] > 0:
            return best
    return None


def build_questions(frame_id, objects, rng, max_comparisons=3, max_metric=2,
                    min_rel=MIN_REL_DIFF, min_abs=MIN_ABS_DIFF_M):
    """Questions for one scene. `objects` already carry their letter in o['label'].

    Comparison: anchor A, options B and C, answer = the option with the smaller ground distance
    to the anchor. The order the options are listed in is randomised so "always the first one"
    scores about 50 %. Metric: a pair, answer = their ground distance in metres.
    """
    by_label = {o["label"]: o for o in objects}
    labels = sorted(by_label)

    def dist(a, b):
        return haversine_m(by_label[a]["gps"], by_label[b]["gps"])

    comparisons = []
    for anchor in labels:
        others = [l for l in labels if l != anchor]
        for b, c in itertools.combinations(others, 2):
            db, dc = dist(anchor, b), dist(anchor, c)
            if not comparison_is_valid(db, dc, min_rel, min_abs):
                continue
            first, second = (b, c) if rng.random() < 0.5 else (c, b)
            comparisons.append({
                "id": f"f{frame_id}-cmp-{anchor}-{first}{second}",
                "frame": frame_id, "type": "comparison",
                "anchor": anchor, "options": [first, second],
                "prompt_body": f"Which is closer to {anchor}: {first} or {second}?",
                "truth": b if db < dc else c,
                "distances_m": {b: round(db, 2), c: round(dc, 2)},
                "relative_gap": round(relative_gap(db, dc), 3),
                "markers": [anchor, first, second],
            })
    # keep a spread of anchors rather than the first few in alphabetical order
    rng.shuffle(comparisons)
    seen, picked = set(), []
    for q in sorted(comparisons, key=lambda q: (q["anchor"] in seen, rng.random())):
        if len(picked) < max_comparisons:
            picked.append(q)
            seen.add(q["anchor"])

    pairs = [(a, b) for a, b in itertools.combinations(labels, 2) if dist(a, b) >= min_abs]
    rng.shuffle(pairs)
    metrics = [{
        "id": f"f{frame_id}-met-{a}{b}", "frame": frame_id, "type": "metric",
        "pair": [a, b],
        "prompt_body": f"Approximately how many metres apart are {a} and {b}?",
        "truth": round(dist(a, b), 2), "markers": [a, b],
    } for a, b in pairs[:max_metric]]
    return sorted(picked, key=lambda q: q["id"]) + sorted(metrics, key=lambda q: q["id"])


def build_prompt(question):
    """Identical for every rotation of the same question."""
    markers = ", ".join(question["markers"])
    if question["type"] == "comparison":
        fmt = (f'Respond with only a JSON object: {{"answer": "<{question["options"][0]} or '
               f'{question["options"][1]}>", "confidence": <integer 0-100>}}')
    else:
        fmt = ('Respond with only a JSON object: {"answer": <number of metres>, '
               '"confidence": <integer 0-100>}')
    return (f"This is an aerial photograph taken by a drone. Some ground objects are marked "
            f"with labelled circles ({markers}).\n\n{question['prompt_body']}\n\n"
            f"{fmt}\nThe confidence is how sure you are, from 0 (guess) to 100 (certain).")


# --------------------------------------------------------------------------------------
# Rotation and drawing
# --------------------------------------------------------------------------------------

def rotate_point(x, y, width, height, degrees_cw):
    """Where pixel (x, y) of a width x height image lands after rotating the image clockwise."""
    degrees_cw %= 360
    if degrees_cw == 0:
        return x, y
    if degrees_cw == 90:
        return height - y, x
    if degrees_cw == 180:
        return width - x, height - y
    if degrees_cw == 270:
        return y, width - x
    raise ValueError("rotation must be a multiple of 90")


def rotate_image(image, degrees_cw):
    from PIL import Image
    ops = {0: None, 90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180,
           270: Image.Transpose.ROTATE_90}                    # PIL rotates counter-clockwise
    op = ops[degrees_cw % 360]
    return image if op is None else image.transpose(op)


def _font(size):
    from PIL import ImageFont
    try:
        return ImageFont.load_default(size=size)
    except TypeError:                                         # Pillow < 10.1
        return ImageFont.load_default()


def render_view(image, points, degrees_cw, max_edge=DEFAULT_MAX_EDGE):
    """Rotate first, then draw the markers, so the letters are always upright.

    points: {label: (x, y)} in the ORIGINAL image's pixel coordinates. Returns a PIL image.
    """
    from PIL import ImageDraw
    width, height = image.size
    scale = min(1.0, max_edge / max(width, height))
    base = image.convert("RGB")
    if scale < 1.0:
        base = base.resize((round(width * scale), round(height * scale)))
    sw, sh = base.size
    view = rotate_image(base, degrees_cw).copy()
    draw = ImageDraw.Draw(view)
    radius = max(14, round(0.014 * max(sw, sh)))
    font = _font(max(18, round(1.6 * radius)))
    for label, (x, y) in points.items():
        rx, ry = rotate_point(x * sw / width, y * sh / height, sw, sh, degrees_cw)
        draw.ellipse([rx - radius, ry - radius, rx + radius, ry + radius], outline=(255, 40, 40), width=3)
        draw.ellipse([rx - 2, ry - 2, rx + 2, ry + 2], fill=(255, 40, 40))
        tx, ty = rx + radius + 3, ry - radius - 3
        box = draw.textbbox((tx, ty), label, font=font)
        draw.rectangle([box[0] - 3, box[1] - 2, box[2] + 3, box[3] + 2], fill=(255, 230, 0))
        draw.text((tx, ty), label, fill=(0, 0, 0), font=font)
    return view


def jpeg_bytes(image, quality=90):
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


# --------------------------------------------------------------------------------------
# Model providers
# --------------------------------------------------------------------------------------

class AnthropicProvider:
    """Anthropic Messages API. The key comes from ANTHROPIC_API_KEY (or the SDK's own credential chain)."""

    name = "anthropic"

    def __init__(self, model, temperature=0.0, max_tokens=1024, client=None):
        import anthropic
        self.anthropic = anthropic
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = client or anthropic.Anthropic(max_retries=5)

    def ask(self, image_jpeg, prompt, question=None):
        kwargs = dict(
            model=self.model, max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                             "data": base64.b64encode(image_jpeg).decode()}},
                {"type": "text", "text": prompt}]}])
        if self.temperature is not None:
            # anthropic 1.x dropped sampling parameters from the typed signature; the API still takes them
            kwargs["extra_body"] = {"temperature": self.temperature}
        try:
            response = self.client.messages.create(**kwargs)
        except self.anthropic.BadRequestError as e:
            if self.temperature is not None and "temperature" in str(e).lower():
                raise SystemExit(f"{self.model} rejected temperature={self.temperature}: {e}\n"
                                 f"Use a model that accepts it, or --temperature omit (not temperature 0).")
            raise
        text = "".join(b.text for b in response.content if b.type == "text")
        return {"text": text, "stop_reason": response.stop_reason,
                "usage": {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens},
                "response": response.model_dump(mode="json")}


class OllamaProvider:
    """A local model served by Ollama (https://ollama.com): free, no key, nothing leaves the machine.

    Uses Ollama's native /api/chat with `format: "json"`, which constrains the reply to valid JSON
    (the Anthropic path relies on the prompt alone, so small local models get a little extra help).
    The host comes from --ollama-host or the OLLAMA_HOST environment variable.
    """

    name = "ollama"

    def __init__(self, model, host=None, temperature=0.0, max_tokens=1024, timeout=900):
        self.model = model
        self.host = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
        if "://" not in self.host:
            self.host = "http://" + self.host
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def _post(self, path, payload=None, timeout=None):
        import urllib.request
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(self.host + path, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
            return json.loads(resp.read())

    def check(self):
        """Fail fast, with the fix, if the server is down or the model is not pulled."""
        import urllib.error
        try:
            tags = self._post("/api/tags", timeout=10)
        except (urllib.error.URLError, OSError) as e:
            raise SystemExit(f"cannot reach Ollama at {self.host} ({e}). Start it with `ollama serve`.")
        names = {m.get("name") for m in tags.get("models", [])} | {m.get("model") for m in tags.get("models", [])}
        if self.model not in names and f"{self.model}:latest" not in names:
            raise SystemExit(f"model {self.model!r} is not pulled. Run `ollama pull {self.model}` "
                             f"(installed: {sorted(n for n in names if n)})")

    def ask(self, image_jpeg, prompt, question=None):
        options = {"num_predict": self.max_tokens, "seed": 0}
        if self.temperature is not None:
            options["temperature"] = self.temperature
        reply = self._post("/api/chat", {
            "model": self.model, "stream": False, "format": "json", "options": options,
            "messages": [{"role": "user", "content": prompt,
                          "images": [base64.b64encode(image_jpeg).decode()]}]})
        return {"text": reply.get("message", {}).get("content", ""), "stop_reason": reply.get("done_reason"),
                "usage": {"input_tokens": reply.get("prompt_eval_count"), "output_tokens": reply.get("eval_count")},
                "response": {k: v for k, v in reply.items() if k != "context"}}


class MockProvider:
    """A stand-in that needs no API: answers correctly most of the time, worse when rotated.

    It reads the question's ground truth, so it is a test double for exercising the pipeline and
    the report. Its numbers say nothing about any model.
    """

    name = "mock"
    model = "mock"
    temperature = 0.0

    def __init__(self, seed=0):
        self.seed = seed

    def ask(self, image_jpeg, prompt, question):
        rng = random.Random(f"{self.seed}-{question['id']}-{question.get('rotation')}")
        rotated = question.get("rotation", 0) in (90, 270)
        confidence = rng.choice([40, 60, 85, 95])
        if question["type"] == "comparison":
            wrong = [o for o in question["options"] if o != question["truth"]][0]
            answer = question["truth"] if rng.random() < (0.7 if rotated else 0.9) else wrong
            payload = {"answer": answer, "confidence": confidence}
        else:
            payload = {"answer": round(question["truth"] * rng.uniform(0.6, 1.5), 1), "confidence": confidence}
        text = json.dumps(payload)
        return {"text": text, "stop_reason": "end_turn", "usage": {}, "response": {"mock": True, "text": text}}


# --------------------------------------------------------------------------------------
# Parsing and analysis
# --------------------------------------------------------------------------------------

def parse_response(text, question):
    """Pull {"answer", "confidence"} out of the reply. Returns (answer, confidence, error).

    answer is an option letter (comparison) or a float in metres (metric); either is None if the
    reply cannot be used. confidence is an int 0-100 or None.
    """
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None, None, "no JSON object in reply"
    try:
        obj = json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        return None, None, f"invalid JSON: {e}"
    if not isinstance(obj, dict) or "answer" not in obj:
        return None, None, "no 'answer' key"
    confidence = obj.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence):
        confidence = None
    else:
        confidence = int(round(min(100, max(0, confidence))))
    raw = obj["answer"]
    if question["type"] == "comparison":
        letter = str(raw).strip().strip(".").upper()
        if letter not in question["options"]:
            return None, confidence, f"answer {raw!r} is not one of {question['options']}"
        return letter, confidence, None
    if isinstance(raw, bool):
        return None, confidence, f"answer {raw!r} is not a number"
    if isinstance(raw, str):
        digits = "".join(ch for ch in raw if ch in "0123456789.-")
        try:
            raw = float(digits)
        except ValueError:
            return None, confidence, f"answer {raw!r} is not a number"
    if not isinstance(raw, (int, float)) or not math.isfinite(raw) or raw < 0:
        return None, confidence, f"answer {raw!r} is not a usable distance"
    return float(raw), confidence, None


def wilson_interval(k, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return centre - half, centre + half


def _median(values):
    return statistics.median(values) if values else float("nan")


def _comparison_stats(rows):
    n = len(rows)
    k = sum(r["correct"] for r in rows)
    return {"n": n, "correct": k, "accuracy": k / n if n else float("nan")}


def _metric_stats(rows):
    errs = [abs(r["answer"] - r["truth"]) / r["truth"] * 100 for r in rows if r["answer"] is not None]
    signed = [(r["answer"] - r["truth"]) / r["truth"] * 100 for r in rows if r["answer"] is not None]
    return {"n": len(errs), "median_abs_pct_error": _median(errs), "median_signed_pct_error": _median(signed)}


def summarise(rows):
    """rows: one dict per answered (question, rotation) with type, qid, rotation, truth, answer
    (None if unparsed), confidence (None if absent) and, for comparisons, correct and options.

    Unparsed comparison answers count as wrong (and are tallied); unparsed metric answers are left
    out of the error statistics (and are tallied).
    """
    cmp_rows = [dict(r, correct=(r["answer"] == r["truth"])) for r in rows if r["type"] == "comparison"]
    met_rows = [r for r in rows if r["type"] == "metric"]
    out = {
        "comparison": _comparison_stats(cmp_rows),
        "metric": _metric_stats(met_rows),
        "unparsed": {"comparison": sum(r["answer"] is None for r in cmp_rows),
                     "metric": sum(r["answer"] is None for r in met_rows)},
    }
    lo, hi = wilson_interval(out["comparison"]["correct"], out["comparison"]["n"])
    out["comparison"]["wilson95"] = [lo, hi]
    out["comparison"]["chance"] = 0.5
    out["comparison"]["picked_first_listed"] = (
        sum(r["answer"] == r["options"][0] for r in cmp_rows if r["answer"] is not None)
        / max(1, sum(r["answer"] is not None for r in cmp_rows)))

    out["by_rotation"] = {}
    for rot in sorted({r["rotation"] for r in rows}):
        out["by_rotation"][rot] = {
            "comparison": _comparison_stats([r for r in cmp_rows if r["rotation"] == rot]),
            "metric": _metric_stats([r for r in met_rows if r["rotation"] == rot])}

    # Flip rate: does the answer to the same question change when only the rotation changes?
    flips = {"comparison": {"questions": 0, "flipped": 0, "vs_0deg": {}},
             "metric": {"questions": 0, "median_spread_pct": float("nan"), "share_over_25pct": float("nan")}}
    by_q = {}
    for r in rows:
        by_q.setdefault(r["qid"], {})[r["rotation"]] = r
    rotations = sorted({r["rotation"] for r in rows})
    complete = [q for q in by_q.values() if set(q) == set(rotations) and all(r["answer"] is not None for r in q.values())]
    cmp_complete = [q for q in complete if next(iter(q.values()))["type"] == "comparison"]
    met_complete = [q for q in complete if next(iter(q.values()))["type"] == "metric"]
    flips["comparison"]["questions"] = len(cmp_complete)
    flips["comparison"]["flipped"] = sum(len({r["answer"] for r in q.values()}) > 1 for q in cmp_complete)
    if 0 in rotations:
        for rot in rotations:
            if rot:
                flips["comparison"]["vs_0deg"][rot] = (
                    sum(q[rot]["answer"] != q[0]["answer"] for q in cmp_complete) / len(cmp_complete)
                    if cmp_complete else float("nan"))
    spreads = []
    for q in met_complete:
        vals = [r["answer"] for r in q.values()]
        mid = statistics.median(vals)
        spreads.append((max(vals) - min(vals)) / mid * 100 if mid > 0 else float("inf"))
    flips["metric"]["questions"] = len(met_complete)
    if spreads:
        flips["metric"]["median_spread_pct"] = _median(spreads)
        flips["metric"]["share_over_25pct"] = sum(s > 25 for s in spreads) / len(spreads)
    flips["comparison"]["flip_rate"] = (flips["comparison"]["flipped"] / len(cmp_complete)
                                        if cmp_complete else float("nan"))
    out["flips"] = flips

    # Calibration-style split on the model's stated confidence.
    def split(rows_, keep):
        return [r for r in rows_ if r["confidence"] is not None and keep(r["confidence"])]
    out["by_confidence"] = {}
    for name, keep in ((f">={CONFIDENCE_SPLIT}", lambda c: c >= CONFIDENCE_SPLIT),
                       (f"<{CONFIDENCE_SPLIT}", lambda c: c < CONFIDENCE_SPLIT)):
        out["by_confidence"][name] = {"comparison": _comparison_stats(split(cmp_rows, keep)),
                                      "metric": _metric_stats(split(met_rows, keep))}
    out["no_confidence"] = {"comparison": sum(r["confidence"] is None for r in cmp_rows),
                            "metric": sum(r["confidence"] is None for r in met_rows)}
    return out


def _pct(x):
    return "n/a" if x != x else f"{100 * x:.0f}%"


def _num(x, spec=".0f", suffix=""):
    return "n/a" if x != x else f"{x:{spec}}{suffix}"


def format_report(summary, header_lines=()):
    s = summary
    c, m, f = s["comparison"], s["metric"], s["flips"]
    lines = list(header_lines)
    lines += [
        "",
        f"Comparison questions: {c['correct']}/{c['n']} correct = {_pct(c['accuracy'])} "
        f"(95% Wilson {_pct(c['wilson95'][0])}-{_pct(c['wilson95'][1])}; chance 50%; "
        f"picked the first-listed option {_pct(c['picked_first_listed'])} of the time)",
        f"Metric questions:     median |error| {_num(m['median_abs_pct_error'], '.0f', '%')}, "
        f"median signed error {_num(m['median_signed_pct_error'], '+.0f', '%')} (n={m['n']}; "
        f"the ground truth itself is good to roughly 10-15%)",
        f"Unparsed replies:     {s['unparsed']['comparison']} comparison (counted wrong), "
        f"{s['unparsed']['metric']} metric (excluded)",
        "",
        "By rotation (clockwise):",
    ]
    for rot, r in s["by_rotation"].items():
        lines.append(f"  {rot:>3} deg  comparison {_pct(r['comparison']['accuracy']):>4} "
                     f"({r['comparison']['correct']}/{r['comparison']['n']})   "
                     f"metric median |error| {_num(r['metric']['median_abs_pct_error'], '.0f', '%')} (n={r['metric']['n']})")
    lines += [
        "",
        f"Flip rate (comparison; answer differs between any two rotations of the same question): "
        f"{_pct(f['comparison']['flip_rate'])} of {f['comparison']['questions']} questions answered at every rotation",
    ]
    if f["comparison"]["vs_0deg"]:
        lines.append("  disagreement with the 0 deg answer: " + ", ".join(
            f"{rot} deg {_pct(v)}" for rot, v in f["comparison"]["vs_0deg"].items()))
    lines.append(f"Metric answers across rotations: median spread (max-min)/median = "
                 f"{_num(f['metric']['median_spread_pct'], '.0f', '%')}; "
                 f"{_pct(f['metric']['share_over_25pct'])} of {f['metric']['questions']} questions vary by more than 25%")
    lines += ["", f"Stated confidence >= {CONFIDENCE_SPLIT} vs < {CONFIDENCE_SPLIT}:"]
    for name, r in s["by_confidence"].items():
        lines.append(f"  confidence {name:>4}: comparison {_pct(r['comparison']['accuracy']):>4} "
                     f"({r['comparison']['correct']}/{r['comparison']['n']}), "
                     f"metric median |error| {_num(r['metric']['median_abs_pct_error'], '.0f', '%')} (n={r['metric']['n']})")
    if s["no_confidence"]["comparison"] or s["no_confidence"]["metric"]:
        lines.append(f"  (no usable confidence: {s['no_confidence']['comparison']} comparison, "
                     f"{s['no_confidence']['metric']} metric)")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------------------

def load_clip_frames(data_dir, clip, tilt_limit):
    path = Path(data_dir) / "derived" / f"{clip}.json"
    if not path.exists():
        sys.exit(f"{path} not found; run: node scripts/au-air/prepare.mjs")
    frames = json.loads(path.read_text())["frames"]
    for fr in frames:
        fr["tilt_deg"] = math.hypot(fr["rollDeg"], fr["pitchDeg"])
    return sorted((fr for fr in frames if fr["tilt_deg"] < tilt_limit and fr["altitude"] > 0),
                  key=lambda fr: fr["index"])


def spread_select(scenes, n, min_gap):
    """Up to n scenes spread over the clip: start nearest its middle, then repeatedly add the scene
    farthest (in frame number) from those already chosen, stopping when none is >= min_gap away.

    The drone hovers over the same cars for long stretches, so neighbouring frames are near-duplicates.
    """
    if not scenes:
        return []
    scenes = sorted(scenes, key=lambda s: s["frame"])
    middle = (scenes[0]["frame"] + scenes[-1]["frame"]) / 2
    chosen = [min(scenes, key=lambda s: abs(s["frame"] - middle))]
    while len(chosen) < n:
        best = max((s for s in scenes if s not in chosen),
                   key=lambda s: min(abs(s["frame"] - c["frame"]) for c in chosen), default=None)
        if best is None or min(abs(best["frame"] - c["frame"]) for c in chosen) < min_gap:
            break
        chosen.append(best)
    return sorted(chosen, key=lambda s: s["frame"])


def make_scene(frame, session, data_dir, focal_xy, rng, args, classes):
    """Detect, georeference and choose objects for one frame. Returns a scene dict or None."""
    from PIL import Image
    image = Image.open(Path(data_dir) / "images" / frame["image"]).convert("RGB")
    pose = {"lat": frame["lat"], "lon": frame["lon"], "altitude": frame["altitude"],
            "heading": ((frame["yaw"] % 360) + 360) % 360, "gimbal_pitch": -90.0}
    candidates = []
    for d in detect(session, image, args.conf):
        if d["cls"] not in classes:
            continue
        g = pixel_to_gps(d["x"], d["y"], pose, focal_xy, image.size)
        if g is None:
            continue
        candidates.append({**d, "gps": (g[0], g[1]), "range_m": g[2]})
    chosen = choose_objects(candidates, k=args.objects, min_sep_m=args.min_sep_m,
                            min_rel=args.min_rel_diff, min_abs=args.min_abs_diff_m)
    if not chosen:
        return None
    labels = list(LABELS[:len(chosen)])
    rng.shuffle(labels)
    objects = [dict(o, label=l) for o, l in zip(chosen, labels)]
    questions = build_questions(frame["index"], objects, rng, args.max_comparisons, args.max_metric,
                                args.min_rel_diff, args.min_abs_diff_m)
    if not any(q["type"] == "comparison" for q in questions):
        return None
    return {"frame": frame["index"], "image": frame["image"], "altitude_m": round(frame["altitude"], 2),
            "tilt_deg": round(frame["tilt_deg"], 2), "n_detections": len(candidates),
            "objects": [{"label": o["label"], "class": o["cls"], "conf": round(o["conf"], 3),
                         "pixel": [round(o["x"], 1), round(o["y"], 1)],
                         "gps": [o["gps"][0], o["gps"][1]]} for o in sorted(objects, key=lambda o: o["label"])],
            "questions": questions, "_image": image,
            "_points": {o["label"]: (o["x"], o["y"]) for o in objects}}


def select_scenes(args):
    import onnxruntime as ort
    frames = load_clip_frames(args.data, args.clip, args.tilt_limit)
    session = ort.InferenceSession(args.model_path, providers=["CPUExecutionProvider"])
    focal_xy = diag_fov_to_focal_px(IMAGE_W, IMAGE_H, args.diag_fov)
    classes = set(args.classes.split(","))
    scanned = frames[::args.scan_stride]
    print(f"scanning {len(scanned)} of {len(frames)} frames with body tilt < {args.tilt_limit} deg ...")
    scenes = []
    for frame in scanned:
        rng = random.Random(f"{args.seed}-{frame['index']}")     # a frame's scene does not depend on scan order
        scene = make_scene(frame, session, args.data, focal_xy, rng, args, classes)
        if scene:
            scenes.append(scene)
    chosen = spread_select(scenes, args.frames, args.min_frame_gap)
    print(f"{len(scenes)} frames can host a scene; using {len(chosen)} at least {args.min_frame_gap} frames apart")
    if len(chosen) < args.frames:
        print(f"WARNING: wanted {args.frames} frames, only {len(chosen)} qualify. Lower --min-frame-gap or "
              f"--scan-stride, or loosen --tilt-limit / --conf / --min-sep-m, if you need more.")
    return chosen


def run(args):
    out = Path(args.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    scenes = select_scenes(args)
    if not scenes:
        sys.exit("no scenes could be built (no frames with enough separated detections)")

    jobs = []
    for scene in scenes:
        for q in scene["questions"]:
            q["prompt"] = build_prompt(q)
        for q in scene["questions"]:
            # only the markers the question names are drawn, so the image never shows an unexplained label
            points = {label: scene["_points"][label] for label in q["markers"]}
            for rot in args.rotations:
                data = jpeg_bytes(render_view(scene["_image"], points, rot, args.max_edge))
                img_name = f"{q['id']}_rot{rot}.jpg"
                (out / "images" / img_name).write_bytes(data)
                jobs.append({"scene": scene, "q": dict(q, rotation=rot), "image_name": img_name, "jpeg": data})

    public_scenes = [{k: v for k, v in s.items() if not k.startswith("_")} for s in scenes]
    manifest = {"clip": args.clip, "diag_fov_deg": args.diag_fov, "conf": args.conf, "seed": args.seed,
                "rotations": list(args.rotations), "min_rel_diff": args.min_rel_diff,
                "min_abs_diff_m": args.min_abs_diff_m, "scenes": public_scenes}
    (out / "questions.json").write_text(json.dumps(manifest, indent=2))
    n_cmp = sum(q["type"] == "comparison" for s in scenes for q in s["questions"])
    n_met = sum(q["type"] == "metric" for s in scenes for q in s["questions"])
    print(f"{len(scenes)} frames (altitude {min(s['altitude_m'] for s in scenes):.1f}-"
          f"{max(s['altitude_m'] for s in scenes):.1f} m), {n_cmp} comparison + {n_met} metric questions, "
          f"x {len(args.rotations)} rotations = {len(jobs)} model calls; images and questions.json in {out}")
    for s in scenes:
        gaps = [q["relative_gap"] for q in s["questions"] if q["type"] == "comparison"]
        print(f"  frame {s['frame']:>4}  alt {s['altitude_m']:>5.1f} m  tilt {s['tilt_deg']:.1f}  "
              f"{len(s['objects'])} objects  {sum(q['type'] == 'comparison' for q in s['questions'])} cmp "
              f"(gap {min(gaps):.0%}-{max(gaps):.0%})  {sum(q['type'] == 'metric' for q in s['questions'])} metric")
    if args.select_only:
        return 0

    provider = make_provider(args)
    raw_path = out / "raw_responses.jsonl"
    done = {}
    if raw_path.exists():
        for line in raw_path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                if not row.get("error"):
                    done[(row["qid"], row["rotation"], row["model"], row["prompt_sha1"], row["image_sha1"])] = row
    todo = []
    for j in jobs:
        key = (j["q"]["id"], j["q"]["rotation"], provider.model, hashlib.sha1(j["q"]["prompt"].encode()).hexdigest(),
               hashlib.sha1(j["jpeg"]).hexdigest())
        if key not in done:
            todo.append((key, j))
    print(f"{len(jobs) - len(todo)} already answered, {len(todo)} to ask ({provider.name}: {provider.model}, "
          f"temperature {provider.temperature if provider.temperature is not None else 'omitted'})")
    with open(raw_path, "a") as fh:
        for n, (key, j) in enumerate(todo, 1):
            t0 = time.time()
            try:
                reply = provider.ask(j["jpeg"], j["q"]["prompt"], j["q"])
                error = None
            except SystemExit:
                raise
            except Exception as e:           # network / rate limit after the SDK's own retries; retried on re-run
                reply, error = {"text": "", "stop_reason": None, "usage": {}, "response": None}, f"{type(e).__name__}: {e}"
            answer, confidence, parse_error = parse_response(reply["text"], j["q"]) if not error else (None, None, error)
            row = {"qid": j["q"]["id"], "frame": j["q"]["frame"], "type": j["q"]["type"], "rotation": j["q"]["rotation"],
                   "provider": provider.name, "model": provider.model,
                   "temperature": provider.temperature, "max_tokens": getattr(provider, "max_tokens", None),
                   "prompt": j["q"]["prompt"], "prompt_sha1": hashlib.sha1(j["q"]["prompt"].encode()).hexdigest(),
                   "image": j["image_name"], "image_sha1": hashlib.sha1(j["jpeg"]).hexdigest(),
                   "truth": j["q"]["truth"], "options": j["q"].get("options"),
                   "raw_text": reply["text"], "stop_reason": reply["stop_reason"], "usage": reply["usage"],
                   "response": reply["response"], "answer": answer, "confidence": confidence,
                   "parse_error": parse_error, "error": error, "seconds": round(time.time() - t0, 2),
                   "time": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            if n % 10 == 0 or n == len(todo):
                print(f"  {n}/{len(todo)}")
    return analyse(args, scenes_manifest=manifest)


def make_provider(args):
    if args.provider == "mock":
        return MockProvider(args.seed)
    if args.provider == "ollama":
        if not args.model:
            sys.exit("--model is required for --provider ollama, e.g. --model qwen2.5vl:3b")
        provider = OllamaProvider(args.model, args.ollama_host,
                                  None if args.temperature == "omit" else float(args.temperature), args.max_tokens)
        provider.check()
        return provider
    if not args.model:
        sys.exit("--model is required for --provider anthropic (there is no default; see the docstring)")
    if not os.environ.get("ANTHROPIC_API_KEY") and not args.allow_profile_auth:
        sys.exit("ANTHROPIC_API_KEY is not set. Export it (it is read from the environment only), "
                 "or pass --allow-profile-auth to use the SDK's other credentials (e.g. `ant auth login`).")
    temperature = None if args.temperature == "omit" else float(args.temperature)
    return AnthropicProvider(args.model, temperature, args.max_tokens)


def load_rows(raw_path, model, questions):
    """Latest successful row per (question, rotation) for `model`, restricted to the current question set."""
    qinfo = {q["id"]: q for s in questions["scenes"] for q in s["questions"]}
    latest = {}
    for line in Path(raw_path).read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("error") or r["model"] != model or r["qid"] not in qinfo:
            continue
        if r["rotation"] not in questions["rotations"]:
            continue
        if r["truth"] != qinfo[r["qid"]]["truth"]:       # question set changed since this reply was recorded
            continue
        latest[(r["qid"], r["rotation"])] = r
    return list(latest.values())


def analyse(args, scenes_manifest=None):
    out = Path(args.out)
    questions = scenes_manifest or json.loads((out / "questions.json").read_text())
    raw_path = out / "raw_responses.jsonl"
    if not raw_path.exists():
        sys.exit(f"{raw_path} not found; nothing to analyse")
    model = "mock" if args.provider == "mock" else args.model
    if not model:
        models = sorted({json.loads(l)["model"] for l in raw_path.read_text().splitlines() if l.strip()})
        sys.exit(f"--model is required to choose which responses to analyse; present in {raw_path.name}: {models}")
    rows = load_rows(raw_path, model, questions)
    if not rows:
        sys.exit(f"no answered rows for model {model!r} in {raw_path}")
    summary = summarise(rows)
    temps = sorted({str(r["temperature"]) for r in rows})
    header = [f"VLM rotation pilot -- clip {questions['clip']}, model {model}, temperature {', '.join(temps)}"
              + ("   ** MOCK PROVIDER: NOT A MODEL, pipeline check only **" if model == "mock" else ""),
              f"{len(questions['scenes'])} frames, {len(rows)} answered (question, rotation) pairs; "
              f"comparisons need the two distances to differ by >= {questions['min_rel_diff']:.0%} and "
              f">= {questions['min_abs_diff_m']:g} m"]
    report = format_report(summary, header)
    print("\n" + report)
    with open(out / f"results_{model}.csv", "w", newline="") as fh:
        cols = ["qid", "frame", "type", "rotation", "truth", "answer", "confidence", "parse_error"]
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["qid"], r["rotation"])))
    (out / f"summary_{model}.json").write_text(json.dumps(summary, indent=2, default=str))
    (out / f"report_{model}.txt").write_text(report + "\n")
    print(f"\nwrote results_{model}.csv, summary_{model}.json, report_{model}.txt to {out}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", default="data_check", help="folder with images/ and derived/ (from prepare.mjs)")
    ap.add_argument("--clip", default=CLIP)
    ap.add_argument("--out", default=str(OUT_DIR), help="output folder (keep it git-ignored)")
    ap.add_argument("--model-path", default=MODEL_PATH, help="the app's ONNX detector")
    ap.add_argument("--frames", type=int, default=N_FRAMES, help="number of frames (10-15 requested)")
    ap.add_argument("--scan-stride", type=int, default=10, help="try every Nth near-level frame")
    ap.add_argument("--min-frame-gap", type=int, default=40, help="chosen frames are at least this many frame numbers apart")
    ap.add_argument("--tilt-limit", type=float, default=TILT_LIMIT_DEG, help="max body tilt, degrees")
    ap.add_argument("--diag-fov", type=float, default=DEFAULT_DIAG_FOV_DEG, help="assumed diagonal FOV, degrees")
    ap.add_argument("--conf", type=float, default=CONF_THRESHOLD, help="detector confidence threshold")
    ap.add_argument("--classes", default="small-vehicle,large-vehicle", help="detector classes to use as objects")
    ap.add_argument("--objects", type=int, default=4, choices=(3, 4), help="objects per frame (falls back to 3)")
    ap.add_argument("--min-rel-diff", type=float, default=MIN_REL_DIFF)
    ap.add_argument("--min-abs-diff-m", type=float, default=MIN_ABS_DIFF_M)
    ap.add_argument("--min-sep-m", type=float, default=MIN_SEP_M)
    ap.add_argument("--max-comparisons", type=int, default=3, help="comparison questions per frame")
    ap.add_argument("--max-metric", type=int, default=2, help="metric questions per frame")
    ap.add_argument("--rotations", type=int, nargs="+", default=list(ROTATIONS), choices=ROTATIONS)
    ap.add_argument("--max-edge", type=int, default=DEFAULT_MAX_EDGE, help="long side of the images sent, pixels")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--provider", choices=("anthropic", "ollama", "mock"), default="anthropic")
    ap.add_argument("--model", default=None, help="model id for the provider (required for a live run)")
    ap.add_argument("--ollama-host", default=None, help="Ollama server (default: $OLLAMA_HOST or http://localhost:11434)")
    ap.add_argument("--temperature", default="0", help="sampling temperature, or 'omit' to not send one")
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--allow-profile-auth", action="store_true",
                    help="run without ANTHROPIC_API_KEY, using the SDK's other credential sources")
    ap.add_argument("--select-only", action="store_true", help="build scenes, questions and images; make no API calls")
    ap.add_argument("--analyze-only", action="store_true", help="recompute the report from raw_responses.jsonl")
    args = ap.parse_args(argv)
    if args.temperature != "omit":
        try:
            float(args.temperature)
        except ValueError:
            ap.error("--temperature must be a number or 'omit'")
    if args.analyze_only:
        return analyse(args)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
