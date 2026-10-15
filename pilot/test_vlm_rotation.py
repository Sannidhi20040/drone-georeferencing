"""Tests for the pure logic in vlm_rotation.py (no API, no detector, no AU-AIR frames).  Run: python -m pytest pilot/"""
import json
import math
import random
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import vlm_rotation as vlm  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
POSE = {"lat": 56.2063, "lon": 10.1880, "altitude": 21.6, "heading": 64.0, "gimbal_pitch": -90.0}


# --- geometry: the Python port must agree with src/geoConverter.js ------------------------------

def test_pixel_at_the_image_centre_is_directly_below_the_drone():
    focal = vlm.diag_fov_to_focal_px(1920, 1080, 80)
    lat, lon, dist = vlm.pixel_to_gps(960, 540, POSE, focal)
    assert dist == pytest.approx(0, abs=1e-9)
    assert vlm.haversine_m((lat, lon), (POSE["lat"], POSE["lon"])) < 1e-6


def test_ground_offset_follows_pinhole_geometry():
    focal = vlm.diag_fov_to_focal_px(1920, 1080, 80)
    _, _, dist = vlm.pixel_to_gps(960 + 300, 540, POSE, focal)
    assert dist == pytest.approx(POSE["altitude"] * 300 / focal[0], rel=1e-9)


def test_rays_above_the_horizon_have_no_ground_position():
    focal = vlm.diag_fov_to_focal_px(1920, 1080, 80)
    level = dict(POSE, gimbal_pitch=0.0)
    assert vlm.pixel_to_gps(960, 100, level, focal) is None
    assert vlm.pixel_to_gps(960, 540, dict(POSE, altitude=0), focal) is None


@pytest.mark.skipif(shutil.which("node") is None or not (REPO / "node_modules" / "@turf").exists(),
                    reason="needs node and the repo's node_modules")
def test_python_port_matches_the_app_javascript():
    pixels = [(100, 80), (960, 540), (1800, 1000), (500, 900), (1500, 200)]
    poses = [POSE, dict(POSE, heading=250.0, altitude=14.3), dict(POSE, gimbal_pitch=-70.0, heading=10.0)]
    script = (
        "import GeoConverter from '%s';"
        "const log = console.log; console.log = () => {};"
        "const g = new GeoConverter({ fov: 80, videoWidth: 1920, videoHeight: 1080 });"
        "console.log = log;"
        "const poses = %s, pixels = %s, out = [];"
        "for (const p of poses) for (const [x, y] of pixels) {"
        "  const r = g.pixelToGPS(x, y, { lat: p.lat, lon: p.lon, altitude: p.altitude, heading: p.heading, gimbalPitch: p.gimbal_pitch });"
        "  out.push(r && [r.latitude, r.longitude, r.distanceFromDrone]); }"
        "console.log(JSON.stringify(out));"
    ) % ((REPO / "src" / "geoConverter.js").as_uri(), json.dumps(poses), json.dumps(pixels))
    result = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, cwd=REPO)
    assert result.returncode == 0, result.stderr
    expected = json.loads(result.stdout.strip().splitlines()[-1])
    focal = vlm.diag_fov_to_focal_px(1920, 1080, 80)
    got = [vlm.pixel_to_gps(x, y, p, focal) for p in poses for x, y in pixels]
    assert len(got) == len(expected)
    for g, e in zip(got, expected):
        if e is None:
            assert g is None
        else:
            assert vlm.haversine_m((g[0], g[1]), (e[0], e[1])) < 0.01      # under a centimetre
            assert g[2] == pytest.approx(e[2], rel=1e-9)


# --- question validity and construction -------------------------------------------------------------

def test_comparison_thresholds_are_inclusive_and_both_required():
    assert vlm.comparison_is_valid(10.0, 13.0)             # exactly 30 % larger and exactly 3 m apart
    assert not vlm.comparison_is_valid(10.0, 12.9)         # under 30 % and under 3 m
    assert not vlm.comparison_is_valid(3.0, 4.5)           # 50 % larger but only 1.5 m apart
    assert not vlm.comparison_is_valid(30.0, 32.5)         # 2.5 m is not enough, nor is 8 %
    assert vlm.comparison_is_valid(30.0, 40.0)             # both satisfied
    assert not vlm.comparison_is_valid(30.0, 38.0)         # 8 m apart but only 27 % larger


def _obj(px, north_m, east_m=0.0, conf=0.9):
    """An object `north_m` north and `east_m` east of the pose, drawn at pixel (px, 100)."""
    lat, lon = vlm.rhumb_destination(POSE["lat"], POSE["lon"], math.hypot(north_m, east_m),
                                     math.degrees(math.atan2(east_m, north_m)) % 360)
    return {"x": px, "y": 100.0, "gps": (lat, lon), "conf": conf, "cls": "small-vehicle"}


def test_choose_objects_enforces_separation_and_skips_scenes_with_no_valid_question():
    far = [_obj(100, 0), _obj(400, 5), _obj(700, 18), _obj(1000, 40)]
    chosen = vlm.choose_objects(far, k=4)
    assert chosen is not None and len(chosen) == 4
    # Two cars 1 m apart in the image's world and 30 px apart on screen are never chosen together.
    crowded = [_obj(100, 0), _obj(130, 1), _obj(700, 18), _obj(1000, 40), _obj(1300, 60)]
    chosen = vlm.choose_objects(crowded, k=4)
    assert chosen is not None
    for a in chosen:
        for b in chosen:
            if a is not b:
                assert vlm.haversine_m(a["gps"], b["gps"]) >= vlm.MIN_SEP_M
                assert math.hypot(a["x"] - b["x"], a["y"] - b["y"]) >= vlm.MIN_SEP_PX
    # An equilateral triangle has equal distances from every anchor, hence no comparison that clears the margin.
    equilateral = [_obj(100, 0), _obj(400, 0, 10), _obj(700, 8.66, 5)]
    assert vlm.choose_objects(equilateral, k=3) is None
    assert vlm.choose_objects(far[:2], k=3) is None


def test_choose_objects_falls_back_to_three_when_four_do_not_fit():
    pool = [_obj(100, 0), _obj(400, 5), _obj(700, 18), _obj(710, 19)]       # the last two collide on screen
    chosen = vlm.choose_objects(pool, k=4)
    assert chosen is not None and len(chosen) == 3


def _scene():
    objs = [dict(_obj(100, 0), label="A"), dict(_obj(400, 5), label="B"),
            dict(_obj(700, 18), label="C"), dict(_obj(1000, 40), label="D")]
    return objs


def test_questions_have_correct_truth_and_clear_the_margin():
    qs = vlm.build_questions(7, _scene(), random.Random(1), max_comparisons=10, max_metric=10)
    by = {o["label"]: o for o in _scene()}
    cmp_qs = [q for q in qs if q["type"] == "comparison"]
    assert cmp_qs
    for q in cmp_qs:
        d = {l: vlm.haversine_m(by[q["anchor"]]["gps"], by[l]["gps"]) for l in q["options"]}
        assert q["truth"] == min(d, key=d.get)
        assert vlm.comparison_is_valid(*d.values())
        assert set(q["options"]) | {q["anchor"]} == set(q["markers"])
    for q in (q for q in qs if q["type"] == "metric"):
        a, b = q["pair"]
        assert q["truth"] == pytest.approx(vlm.haversine_m(by[a]["gps"], by[b]["gps"]), abs=0.006)
        assert q["truth"] >= vlm.MIN_ABS_DIFF_M


def test_option_order_is_randomised_and_questions_are_capped():
    firsts = set()
    for seed in range(40):
        qs = vlm.build_questions(7, _scene(), random.Random(seed), max_comparisons=2, max_metric=1)
        assert sum(q["type"] == "comparison" for q in qs) <= 2
        assert sum(q["type"] == "metric" for q in qs) <= 1
        firsts |= {q["options"][0] == q["truth"] for q in qs if q["type"] == "comparison"}
    assert firsts == {True, False}                         # the correct answer is listed first and second


def test_prompt_is_identical_for_every_rotation_and_names_only_the_options():
    q = {"type": "comparison", "anchor": "A", "options": ["C", "B"], "markers": ["A", "C", "B"],
         "prompt_body": "Which is closer to A: C or B?", "rotation": 0}
    assert vlm.build_prompt(q) == vlm.build_prompt(dict(q, rotation=270))
    assert '"C or B"' not in vlm.build_prompt(q) and "<C or B>" in vlm.build_prompt(q)
    m = {"type": "metric", "pair": ["A", "B"], "markers": ["A", "B"],
         "prompt_body": "Approximately how many metres apart are A and B?"}
    assert "number of metres" in vlm.build_prompt(m)


# --- rotation: markers must land on the same scene content, labels upright --------------------------

@pytest.mark.parametrize("degrees", [0, 90, 180, 270])
def test_rotated_marker_position_lands_on_the_same_pixel_content(degrees):
    from PIL import Image
    w, h = 40, 20
    img = Image.new("RGB", (w, h), (0, 0, 0))
    x, y = 31, 4
    img.putpixel((x, y), (255, 0, 0))
    rotated = vlm.rotate_image(img, degrees)
    assert rotated.size == ((h, w) if degrees in (90, 270) else (w, h))
    rx, ry = vlm.rotate_point(x + 0.5, y + 0.5, w, h, degrees)       # centre of the pixel
    assert rotated.getpixel((int(rx), int(ry))) == (255, 0, 0)


def test_four_quarter_turns_return_to_the_start():
    x, y = 123.0, 456.0
    w, h = 1920, 1080
    px, py, cw, ch = x, y, w, h
    for _ in range(4):
        px, py = vlm.rotate_point(px, py, cw, ch, 90)
        cw, ch = ch, cw
    assert (px, py) == pytest.approx((x, y))


def test_render_draws_markers_after_rotation_and_keeps_labels_upright():
    from PIL import Image
    img = Image.new("RGB", (400, 200), (30, 30, 30))
    views = {d: vlm.render_view(img, {"A": (300, 50)}, d, max_edge=400) for d in vlm.ROTATIONS}
    assert views[90].size == (200, 400) and views[0].size == (400, 200)

    def yellow(view):
        px = view.load()
        return [(x, y) for x in range(view.width) for y in range(view.height) if px[x, y] == (255, 230, 0)]

    shapes = []
    for d, view in views.items():
        pts = yellow(view)
        assert pts, f"no label box at {d} deg"
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        shapes.append((max(xs) - min(xs), max(ys) - min(ys)))
        # the marker's red dot is where the rotated point should be
        rx, ry = vlm.rotate_point(300, 50, 400, 200, d)
        assert view.getpixel((round(rx), round(ry))) == (255, 40, 40)
    assert len(set(shapes)) == 1                           # the label box is the same wide-and-short shape at every angle


# --- parsing -----------------------------------------------------------------------------------------

CMP = {"type": "comparison", "options": ["B", "C"]}
MET = {"type": "metric"}


def test_parse_comparison_replies():
    assert vlm.parse_response('{"answer": "B", "confidence": 90}', CMP) == ("B", 90, None)
    assert vlm.parse_response('Sure!\n```json\n{"answer": "c", "confidence": 55.4}\n```', CMP) == ("C", 55, None)
    a, c, err = vlm.parse_response('{"answer": "A", "confidence": 70}', CMP)
    assert a is None and c == 70 and "not one of" in err
    assert vlm.parse_response("I think B", CMP)[2] == "no JSON object in reply"
    assert vlm.parse_response('{"answer": "B", "confidence": 250}', CMP)[1] == 100
    assert vlm.parse_response('{"answer": "B", "confidence": "high"}', CMP)[1] is None


def test_parse_metric_replies():
    assert vlm.parse_response('{"answer": 12.5, "confidence": 80}', MET) == (12.5, 80, None)
    assert vlm.parse_response('{"answer": "about 12 m", "confidence": 80}', MET)[0] == 12.0
    assert vlm.parse_response('{"answer": "n/a", "confidence": 80}', MET)[0] is None
    assert vlm.parse_response('{"answer": -3, "confidence": 80}', MET)[0] is None
    assert vlm.parse_response('{"answer": true, "confidence": 80}', MET)[0] is None
    assert vlm.parse_response('{"confidence": 80}', MET)[2] == "no 'answer' key"


# --- analysis ----------------------------------------------------------------------------------------

def _cmp(qid, rot, answer, truth="B", confidence=90):
    return {"type": "comparison", "qid": qid, "rotation": rot, "truth": truth, "answer": answer,
            "confidence": confidence, "options": ["B", "C"]}


def _met(qid, rot, answer, truth=10.0, confidence=90):
    return {"type": "metric", "qid": qid, "rotation": rot, "truth": truth, "answer": answer,
            "confidence": confidence, "options": None}


def test_summary_accuracy_flips_and_confidence_split():
    rows = []
    # q1 always right, high confidence; q2 right only upright, low confidence when wrong; q3 always wrong
    for rot in (0, 90, 180, 270):
        rows.append(_cmp("q1", rot, "B", confidence=95))
        rows.append(_cmp("q2", rot, "B" if rot == 0 else "C", confidence=90 if rot == 0 else 40))
        rows.append(_cmp("q3", rot, "C", confidence=85))
    s = vlm.summarise(rows)
    assert s["comparison"]["n"] == 12 and s["comparison"]["correct"] == 5
    assert s["by_rotation"][0]["comparison"]["accuracy"] == pytest.approx(2 / 3)
    assert s["by_rotation"][90]["comparison"]["accuracy"] == pytest.approx(1 / 3)
    assert s["flips"]["comparison"]["questions"] == 3
    assert s["flips"]["comparison"]["flipped"] == 1 and s["flips"]["comparison"]["flip_rate"] == pytest.approx(1 / 3)
    assert s["flips"]["comparison"]["vs_0deg"][180] == pytest.approx(1 / 3)
    hi, lo = s["by_confidence"][">=80"]["comparison"], s["by_confidence"]["<80"]["comparison"]
    assert (hi["n"], hi["correct"]) == (4 + 1 + 4, 4 + 1)               # q1 x4, q2 at 0 deg, q3 x4
    assert (lo["n"], lo["correct"]) == (3, 0)


def test_summary_metric_errors_and_spread():
    rows = [_met("m1", 0, 12.0), _met("m1", 90, 8.0), _met("m1", 180, 10.0), _met("m1", 270, 15.0, confidence=50),
            _met("m2", 0, 20.0, truth=10.0)]
    s = vlm.summarise(rows)
    errors = sorted([20, 20, 0, 50, 100])
    assert s["metric"]["median_abs_pct_error"] == pytest.approx(errors[2])
    assert s["metric"]["median_signed_pct_error"] == pytest.approx(20.0)
    assert s["flips"]["metric"]["questions"] == 1                      # m2 was not answered at every rotation
    assert s["flips"]["metric"]["median_spread_pct"] == pytest.approx((15 - 8) / 11 * 100)
    assert s["by_confidence"]["<80"]["metric"]["n"] == 1


def test_unparsed_comparison_counts_wrong_and_unparsed_metric_is_excluded():
    rows = [_cmp("q1", 0, None), _cmp("q1", 90, "B"), _met("m1", 0, None), _met("m1", 90, 10.0)]
    s = vlm.summarise(rows)
    assert s["comparison"]["accuracy"] == 0.5 and s["unparsed"] == {"comparison": 1, "metric": 1}
    assert s["metric"]["n"] == 1
    assert s["flips"]["comparison"]["questions"] == 0                  # an unanswered rotation makes the question incomplete


def test_report_renders_with_nan_sections():
    text = vlm.format_report(vlm.summarise([_cmp("q1", 0, "B")]), ["header"])
    assert "Comparison questions: 1/1" in text and "n/a" in text


def test_wilson_interval_brackets_the_estimate():
    lo, hi = vlm.wilson_interval(30, 40)
    assert lo < 0.75 < hi and 0 <= lo and hi <= 1


# --- selection, providers, resume --------------------------------------------------------------------

def test_spread_select_keeps_frames_apart_and_stops_when_it_cannot():
    scenes = [{"frame": f} for f in (100, 110, 120, 500, 510, 900, 905, 2000)]
    chosen = vlm.spread_select(scenes, 5, min_gap=50)
    frames = [s["frame"] for s in chosen]
    assert all(b - a >= 50 for a, b in zip(frames, frames[1:]))
    assert frames == [100, 500, 905, 2000]                 # only four groups of frames are >= 50 apart
    assert len(vlm.spread_select(scenes, 8, min_gap=200)) < 8
    assert vlm.spread_select([], 5, 10) == []


def test_mock_provider_is_deterministic_and_answers_in_the_requested_format():
    q = {"id": "f1-cmp-A-BC", "type": "comparison", "options": ["B", "C"], "truth": "B", "rotation": 90}
    p = vlm.MockProvider(seed=3)
    r1, r2 = p.ask(b"", "prompt", q), p.ask(b"", "prompt", q)
    assert r1["text"] == r2["text"]
    answer, confidence, err = vlm.parse_response(r1["text"], q)
    assert err is None and answer in ("B", "C") and 0 <= confidence <= 100


def test_live_run_needs_an_explicit_model_and_a_key_from_the_environment(monkeypatch):
    base = dict(provider="anthropic", model=None, temperature="0", max_tokens=1024, allow_profile_auth=False, seed=0)
    ns = type("A", (), base)
    with pytest.raises(SystemExit, match="--model is required"):
        vlm.make_provider(ns)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY is not set"):
        vlm.make_provider(type("A", (), dict(base, model="some-model")))


def test_load_rows_uses_the_latest_success_and_ignores_stale_or_failed_rows(tmp_path):
    questions = {"rotations": [0, 90], "scenes": [{"questions": [{"id": "q1", "truth": "B"}]}]}
    lines = [
        {"qid": "q1", "rotation": 0, "model": "m", "truth": "B", "answer": "C", "error": "RateLimitError"},
        {"qid": "q1", "rotation": 0, "model": "m", "truth": "B", "answer": "C", "error": None},
        {"qid": "q1", "rotation": 0, "model": "m", "truth": "B", "answer": "B", "error": None},
        {"qid": "q1", "rotation": 90, "model": "other", "truth": "B", "answer": "B", "error": None},
        {"qid": "q1", "rotation": 270, "model": "m", "truth": "B", "answer": "B", "error": None},     # not in this run
        {"qid": "q9", "rotation": 0, "model": "m", "truth": "B", "answer": "B", "error": None},       # question no longer exists
        {"qid": "q1", "rotation": 90, "model": "m", "truth": "C", "answer": "C", "error": None},      # truth changed
    ]
    path = tmp_path / "raw.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in lines) + "\n")
    rows = vlm.load_rows(path, "m", questions)
    assert [(r["qid"], r["rotation"], r["answer"]) for r in rows] == [("q1", 0, "B")]


# --- the Anthropic request, checked against a canned HTTP transport (no network, no key) -------------

def _http():
    """The HTTP library the installed anthropic SDK uses: httpx2 for 1.x, httpx for 0.x."""
    pytest.importorskip("anthropic")
    try:
        import httpx2 as http
    except ImportError:
        http = pytest.importorskip("httpx")
    return http


def _anthropic_with(handler):
    import anthropic
    http = _http()
    return anthropic.Anthropic(api_key="test-key-not-real", max_retries=0,
                               http_client=http.Client(transport=http.MockTransport(handler)))


def test_anthropic_request_carries_the_image_the_prompt_and_temperature_zero():
    import base64
    httpx = _http()
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": "test-model",
            "content": [{"type": "text", "text": '{"answer": "B", "confidence": 77}'}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 1500, "output_tokens": 12}})

    provider = vlm.AnthropicProvider("test-model", temperature=0.0, max_tokens=256, client=_anthropic_with(handler))
    reply = provider.ask(b"\xff\xd8jpegbytes", "the prompt")
    body = seen["body"]
    assert body["model"] == "test-model" and body["temperature"] == 0.0 and body["max_tokens"] == 256
    image, text = body["messages"][0]["content"]
    assert image["type"] == "image" and image["source"]["media_type"] == "image/jpeg"
    assert base64.b64decode(image["source"]["data"]) == b"\xff\xd8jpegbytes"
    assert text == {"type": "text", "text": "the prompt"}
    assert reply["text"] == '{"answer": "B", "confidence": 77}'
    assert reply["usage"] == {"input_tokens": 1500, "output_tokens": 12}
    assert reply["response"]["id"] == "msg_1"                           # the full raw response is kept
    assert "test-key-not-real" not in json.dumps(reply)


def test_temperature_omit_sends_no_temperature_and_a_rejected_temperature_stops_the_run():
    httpx = _http()
    seen = {}

    def ok(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "id": "m", "type": "message", "role": "assistant", "model": "x", "content": [{"type": "text", "text": "{}"}],
            "stop_reason": "end_turn", "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}})

    vlm.AnthropicProvider("x", temperature=None, client=_anthropic_with(ok)).ask(b"j", "p")
    assert "temperature" not in seen["body"]

    def reject(request):
        return httpx.Response(400, json={"type": "error", "error": {
            "type": "invalid_request_error", "message": "`temperature` may only be set to 1 for this model"}})

    with pytest.raises(SystemExit, match="rejected temperature=0.0"):
        vlm.AnthropicProvider("x", temperature=0.0, client=_anthropic_with(reject)).ask(b"j", "p")
