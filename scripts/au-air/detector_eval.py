"""Scores the app's ONNX detector on AU-AIR frames against the dataset's own boxes.

    python scripts/au-air/detector_eval.py --clip 20190829091111 --frames 150

Requires: numpy, pillow, onnxruntime  (pip install numpy pillow onnxruntime)

Uses the same preprocessing (letterbox to 640, gray 114 padding) and decoding
(channel-major [1, 7, 8400], class-wise NMS at 0.45) as the web app.
Class mapping: car/van -> small-vehicle; truck/bus/trailer -> large-vehicle;
human -> human; motorbike/bicycle have no model class and are ignored.

Two match rules are reported because they answer different questions:
  iou    - box overlap >= 0.5 (standard detection metric; harsh when box
           conventions differ, which they do here)
  center - the detection's centre lies inside the labelled box (what matters
           for georeferencing, which uses only the box centre)
"""
import argparse, collections, json, random, re, time
import numpy as np
from PIL import Image
import onnxruntime as ort

parser = argparse.ArgumentParser()
parser.add_argument('--data', default='data_check')
parser.add_argument('--model', default='public/models/aerial_yolov8.onnx')
parser.add_argument('--clip', default='20190829091111', help="clip id prefix, or 'all' (samples evenly across clips)")
parser.add_argument('--frames', type=int, default=150, help='frames to sample (per clip when --clip all)')
parser.add_argument('--seed', type=int, default=11)
parser.add_argument('--conf', type=float, nargs='+', default=[0.5, 0.25])
args = parser.parse_args()

MAP = {0: 2, 1: 0, 3: 0, 2: 1, 6: 1, 7: 1}      # AU-AIR class id -> model class id
NAMES = ['small-vehicle', 'large-vehicle', 'human']

session = ort.InferenceSession(args.model, providers=['CPUExecutionProvider'])
input_name = session.get_inputs()[0].name
annotations = json.load(open(f'{args.data}/annotations.json'))['annotations']

by_clip = collections.defaultdict(list)
for a in annotations:
    by_clip[re.match(r'frame_(\d{14})_', a['image_name']).group(1)].append(a)
random.seed(args.seed)
clips = list(by_clip) if args.clip == 'all' else [args.clip]
sample = [a for c in clips for a in random.sample(by_clip[c], min(args.frames, len(by_clip[c])))]


def letterbox(img, size=640):
    w, h = img.size
    s = min(size / w, size / h)
    nw, nh = round(w * s), round(h * s)
    px, py = (size - nw) // 2, (size - nh) // 2
    canvas = Image.new('RGB', (size, size), (114, 114, 114))
    canvas.paste(img.resize((nw, nh), Image.BILINEAR), (px, py))
    return np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0, s, px, py


def iou(a, b):
    inter = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0


def nms(dets, threshold=0.45):
    dets.sort(key=lambda d: -d['conf'])
    keep = []
    for d in dets:
        if all(k['cls'] != d['cls'] or iou(k['box'], d['box']) <= threshold for k in keep):
            keep.append(d)
    return keep


def detect(path, threshold):
    x, s, px, py = letterbox(Image.open(path).convert('RGB'))
    out = session.run(None, {input_name: x})[0][0]
    scores = out[4:7]
    cls, conf = scores.argmax(0), scores.max(0)
    dets = []
    for i in np.where(conf >= threshold)[0]:
        cx, cy, w, h = (out[0, i] - px) / s, (out[1, i] - py) / s, out[2, i] / s, out[3, i] / s
        dets.append({'cls': int(cls[i]), 'conf': float(conf[i]),
                     'box': (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)})
    return nms(dets)


def score(threshold, mode):
    tp, fp, fn, total = (collections.Counter() for _ in range(4))
    for a in sample:
        dets = detect(f"{args.data}/images/{a['image_name']}", threshold)
        gts = [{'cls': MAP.get(b['class']),
                'box': (b['left'], b['top'], b['left'] + b['width'], b['top'] + b['height'])} for b in a['bbox']]

        def hit(d, g):
            if mode == 'iou':
                return iou(d['box'], g['box']) >= 0.5
            cx, cy = (d['box'][0] + d['box'][2]) / 2, (d['box'][1] + d['box'][3]) / 2
            return g['box'][0] <= cx <= g['box'][2] and g['box'][1] <= cy <= g['box'][3]

        used = set()
        for d in sorted(dets, key=lambda d: -d['conf']):
            match = next((i for i, g in enumerate(gts)
                          if i not in used and (g['cls'] is None or g['cls'] == d['cls']) and hit(d, g)), None)
            if match is None:
                fp[d['cls']] += 1
            else:
                used.add(match)
                if gts[match]['cls'] is not None:
                    tp[d['cls']] += 1
        for i, g in enumerate(gts):
            if g['cls'] is not None:
                total[g['cls']] += 1
                fn[g['cls']] += i not in used
    for c in range(3):
        if total[c] == 0:
            continue
        t, f, n = tp[c], fp[c], fn[c]
        p = t / (t + f) if t + f else float('nan')
        r = t / (t + n) if t + n else float('nan')
        print(f'  {mode:6s} conf>={threshold:<4} {NAMES[c]:14s} GT={total[c]:5d} TP={t:5d} FP={f:5d} FN={n:5d}  precision={p:.2f} recall={r:.2f}')


print(f'{len(sample)} frames from {len(clips)} clip(s), seed {args.seed}')
t0 = time.time()
for threshold in args.conf:
    for mode in ('iou', 'center'):
        score(threshold, mode)
print(f'({time.time() - t0:.0f}s)  Frames from one hovering scene are highly correlated: treat n as small.')
