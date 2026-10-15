"""Tests for the pure logic in da3_altitude.py (no GPU, no model).  Run: python -m pytest pilot/"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import da3_altitude as da3  # noqa: E402


def test_focal_from_diagonal_fov_matches_the_horizontal_fov_split():
    # 84 deg diagonal on 1920x1080 splits into HFOV 76.2475 deg, so f = (W/2) / tan(HFOV/2).
    focal = da3.focal_px_from_diag_fov(1920, 1080, 84)
    hfov = math.radians(76.2475)
    assert focal == pytest.approx((1920 / 2) / math.tan(hfov / 2), rel=1e-4)


def test_processed_focal_is_the_mean_of_fx_and_fy_after_resize():
    # 1920x1080 -> 504x280: x scaled by 0.2625, y by 0.259259...
    f = da3.processed_focal_px(1000.0, 1920, 1080, 504, 280)
    assert f == pytest.approx(1000 * (0.2625 + 280 / 1080) / 2)


def test_metric_conversion_follows_the_readme_formula():
    assert da3.to_metres(0.5, 700.0) == pytest.approx(700 * 0.5 / 300)


def test_implied_fov_recovers_the_assumed_fov_when_depth_equals_altitude():
    width, height, pw, ph = 1920, 1080, 504, 280
    fov = 80.0
    focal_proc = da3.processed_focal_px(da3.focal_px_from_diag_fov(width, height, fov), width, height, pw, ph)
    altitude = 21.7
    net = da3.METRIC_DIVISOR * altitude / focal_proc          # the net output that gives exactly `altitude`
    assert da3.to_metres(net, focal_proc) == pytest.approx(altitude)
    assert da3.implied_diag_fov_deg(net, altitude, width, height, pw, ph) == pytest.approx(fov, abs=1e-6)


def test_a_smaller_network_output_needs_a_longer_focal_length_so_a_narrower_fov():
    # focal = 300 * altitude / net_output, and a longer focal length means a narrower field of view.
    args = (1920, 1080, 504, 280)
    assert da3.implied_diag_fov_deg(0.15, 20.0, *args) < da3.implied_diag_fov_deg(0.30, 20.0, *args)
    # Doubling the net output halves the implied focal length.
    f1 = da3.METRIC_DIVISOR * 20.0 / 0.30
    f2 = da3.METRIC_DIVISOR * 20.0 / 0.15
    assert f2 == pytest.approx(2 * f1)


def test_central_median_uses_only_the_centred_window_and_ignores_nans():
    depth = np.full((100, 200), 100.0, dtype=np.float32)
    depth[35:65, 70:130] = 5.0                                # 30 x 60 = 30% of each side, centred
    assert da3.central_median(depth, 0.30) == pytest.approx(5.0)
    depth[50, 100] = np.nan
    assert da3.central_median(depth, 0.30) == pytest.approx(5.0)


def test_percent_error_is_signed_relative_to_the_reference():
    assert da3.pct_error(22.0, 20.0) == pytest.approx(10.0)
    assert da3.pct_error(18.0, 20.0) == pytest.approx(-10.0)


def test_correlation_helpers():
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert da3.pearson(x, [2 * v + 1 for v in x]) == pytest.approx(1.0)
    assert da3.pearson(x, [-v for v in x]) == pytest.approx(-1.0)
    assert da3.spearman(x, [v ** 3 for v in x]) == pytest.approx(1.0)      # monotonic but not linear
    assert da3.slope(x, [2 * v + 1 for v in x]) == pytest.approx(2.0)
    # Rescaling one variable (e.g. a focal-length error) leaves the correlation unchanged.
    noisy = [3.0, 1.0, 4.0, 2.0, 5.0]
    assert da3.pearson(x, noisy) == pytest.approx(da3.pearson(x, [0.37 * v for v in noisy]))


def _frame(n, altitude, tilt):
    return {"image": f"f{n}.jpg", "frame": n, "altitude_m": altitude, "tilt_deg": tilt}


def test_selection_respects_tilt_exclusions_count_and_spacing():
    frames = [_frame(n, 10 + n * 0.05, 2.0 if n % 7 else 8.0) for n in range(400)]
    chosen = da3.select_clean_frames(frames, n=30, tilt_limit=5.0, exclude={100, 200})
    assert len(chosen) == 30
    assert all(r["tilt_deg"] < 5.0 for r in chosen)
    assert not {100, 200} & {r["frame"] for r in chosen}
    numbers = sorted(r["frame"] for r in chosen)
    assert all(b - a >= 10 for a, b in zip(numbers, numbers[1:]))
    alts = [r["altitude_m"] for r in chosen]
    assert min(alts) < 11.0 and max(alts) > 29.0              # spread across the altitude range


def test_selection_fails_clearly_when_too_few_frames_qualify():
    with pytest.raises(ValueError):
        da3.select_clean_frames([_frame(n, 20.0, 9.0) for n in range(50)], n=30)


def test_load_frames_converts_units_and_filters_the_clip(tmp_path):
    def rec(name, alt_mm, roll_rad, pitch_rad):
        return {"image_name": name, "altitude": alt_mm, "angle_phi": roll_rad, "angle_theta": pitch_rad}
    annotations = {"annotations": [
        rec("frame_20190829091111_x_0000172.jpg", 15200.0, math.radians(3), math.radians(4)),
        rec("frame_20190829091111_x_0000010.jpg", 9000.0, 0.0, 0.0),
        rec("frame_20190905091750_x_0000172.jpg", 99000.0, 0.0, 0.0),     # another clip
    ]}
    (tmp_path / "annotations.json").write_text(json.dumps(annotations))
    frames = da3.load_frames(tmp_path)
    assert [r["frame"] for r in frames] == [10, 172]                     # sorted, other clip dropped
    f172 = frames[1]
    assert f172["altitude_m"] == pytest.approx(15.2)                     # millimetres -> metres
    assert f172["tilt_deg"] == pytest.approx(5.0)                        # hypot(3, 4)
