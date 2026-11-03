"""Shared loaders and constants for the sunday_checks analyses. No API calls anywhere in this folder except the
optional step 4, which is NOT implemented here (step4_feasibility.py only counts and estimates)."""
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pilot"))
import vlm_rotation as vlm  # noqa: E402  (reuses its load_rows, geometry and haversine, unchanged)

SEED = 20261025          # every bootstrap / permutation in this folder uses this seed
N_BOOT = 2000
OUT = ROOT / "sunday_checks" / "output"

# (label, output folder under pilot/output, model id as saved in raw_responses.jsonl)
RUNS = [
    ("Haiku 5.5", "vlm_rotation_haiku55", "claude-haiku-5-5"),
    ("Sonnet 4.6", "vlm_rotation_claude46", "claude-sonnet-4-6"),
    ("Opus 4.6", "vlm_rotation_claude46", "claude-opus-4-6"),
    ("Haiku 4.5", "vlm_rotation", "claude-haiku-4-5"),
    ("Qwen2.5-VL 3B", "vlm_rotation", "qwen2.5vl:3b"),
]

# Headline numbers quoted in the brief, same model order as RUNS (whole percent).
HEADLINE = {
    "median distance spread %": [7, 69, 50, 97, 92],
    "comparison accuracy %": [100, 100, 99, 85, 57],
    "median distance error %": [15, 61, 36, 37, 42],
    "comparison answers changed %": [0, 0, 3, 33, 12],
}


def questions_path(folder):
    return ROOT / "pilot" / "output" / folder / "questions.json"


def raw_path(folder):
    return ROOT / "pilot" / "output" / folder / "raw_responses.jsonl"


def load_questions(folder):
    return json.loads(questions_path(folder).read_text())


def load_model_rows(folder, model):
    """Latest successful row per (question, rotation) for `model`, exactly as vlm_rotation's own report selects them."""
    return vlm.load_rows(raw_path(folder), model, load_questions(folder))


def question_table(folder="vlm_rotation"):
    """{qid: {...question..., 'objects': {label: {pixel, gps}}, 'scene': scene}}"""
    out = {}
    for scene in load_questions(folder)["scenes"]:
        objects = {o["label"]: o for o in scene["objects"]}
        for q in scene["questions"]:
            out[q["id"]] = dict(q, objects=objects, scene=scene)
    return out


def percentile_ci(values, lo=2.5, hi=97.5):
    arr = np.asarray(values, float)
    ok = arr[np.isfinite(arr)]
    if len(ok) == 0:
        return float("nan"), float("nan"), int(len(arr))
    return float(np.percentile(ok, lo)), float(np.percentile(ok, hi)), int(len(arr) - len(ok))


def fmt_ci(point, ci, nd=0, pct=False):
    lo, hi, _ = ci
    if point != point:
        return "n/a"
    suffix = "%" if pct else ""
    return f"{point:.{nd}f}{suffix} [{lo:.{nd}f}, {hi:.{nd}f}]"
