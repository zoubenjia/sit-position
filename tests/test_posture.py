"""posture.py 单元测试"""

from unittest.mock import MagicMock

from sit_monitor.posture import (
    LEFT_EAR, RIGHT_EAR, LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP,
    angle_deg,
    evaluate_posture,
    head_forward_angle,
    shoulder_tilt,
    torso_forward_angle,
)


def _make_landmark(x, y, visibility=0.9):
    lm = MagicMock()
    lm.x = x
    lm.y = y
    lm.visibility = visibility
    return lm


def _make_landmarks(overrides=None):
    """创建一组 landmarks（坐正姿势），支持覆盖特定关键点"""
    # 默认：对称坐正，耳朵在肩膀正上方，躯干垂直
    defaults = {
        LEFT_EAR: (0.40, 0.10),
        RIGHT_EAR: (0.60, 0.10),
        LEFT_SHOULDER: (0.40, 0.30),
        RIGHT_SHOULDER: (0.60, 0.30),
        LEFT_HIP: (0.40, 0.60),
        RIGHT_HIP: (0.60, 0.60),
    }
    if overrides:
        defaults.update(overrides)

    landmarks = {}
    for idx in range(33):
        landmarks[idx] = _make_landmark(0.5, 0.5, visibility=0.1)
    for idx, (x, y) in defaults.items():
        landmarks[idx] = _make_landmark(x, y)
    return landmarks


class TestAngleDeg:
    def test_vertical_up(self):
        assert angle_deg(0, -1) == 0.0

    def test_horizontal(self):
        assert abs(angle_deg(1, 0) - 90.0) < 0.01

    def test_45_degrees(self):
        assert abs(angle_deg(1, -1) - 45.0) < 0.01


class TestShoulderTilt:
    def test_level_shoulders(self):
        landmarks = _make_landmarks()
        result = shoulder_tilt(landmarks)
        assert result is not None
        assert result == 0.0

    def test_tilted_shoulders(self):
        landmarks = _make_landmarks({
            LEFT_SHOULDER: (0.4, 0.3),
            RIGHT_SHOULDER: (0.6, 0.4),
        })
        result = shoulder_tilt(landmarks)
        assert result is not None
        assert result > 0

    def test_low_visibility(self):
        landmarks = _make_landmarks()
        landmarks[LEFT_SHOULDER] = _make_landmark(0.4, 0.3, visibility=0.3)
        assert shoulder_tilt(landmarks) is None


class TestHeadForwardAngle:
    def test_upright_head(self):
        landmarks = _make_landmarks()
        result = head_forward_angle(landmarks)
        assert result is not None
        assert result < 5  # 耳朵正在肩膀上方

    def test_forward_head(self):
        landmarks = _make_landmarks({
            LEFT_EAR: (0.55, 0.20),
            RIGHT_EAR: (0.75, 0.20),
        })
        result = head_forward_angle(landmarks)
        assert result is not None
        assert result > 15


class TestTorsoForwardAngle:
    def test_upright_torso(self):
        landmarks = _make_landmarks()
        result = torso_forward_angle(landmarks)
        assert result is not None
        assert result < 5

    def test_leaning_forward(self):
        landmarks = _make_landmarks({
            LEFT_SHOULDER: (0.55, 0.30),
            RIGHT_SHOULDER: (0.75, 0.30),
        })
        result = torso_forward_angle(landmarks)
        assert result is not None
        assert result > 10


class TestEvaluatePosture:
    def test_good_posture(self):
        landmarks = _make_landmarks()
        thresholds = {"shoulder": 7, "neck": 10, "torso": 5}
        is_bad, details, reasons = evaluate_posture(landmarks, thresholds)
        assert not is_bad
        assert len(reasons) == 0

    def test_bad_neck(self):
        landmarks = _make_landmarks({
            LEFT_EAR: (0.60, 0.20),
            RIGHT_EAR: (0.80, 0.20),
        })
        thresholds = {"shoulder": 7, "neck": 10, "torso": 5}
        is_bad, details, reasons = evaluate_posture(landmarks, thresholds)
        assert is_bad
        assert any("下巴" in r for r in reasons)

    def test_returns_all_detail_keys(self):
        landmarks = _make_landmarks()
        thresholds = {"shoulder": 99, "neck": 99, "torso": 99}
        _, details, _ = evaluate_posture(landmarks, thresholds)
        assert set(details.keys()) == {"shoulder", "neck", "torso"}
