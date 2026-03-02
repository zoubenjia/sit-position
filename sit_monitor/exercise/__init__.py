"""运动模块：导出 + 运动注册表"""

from sit_monitor.exercise.base import (
    ExerciseAnalyzer,
    ExerciseMonitor,
    RepPhase,
    RepResult,
)
from sit_monitor.exercise.pushup import PushupAnalyzer
from sit_monitor.exercise.voice_coach import VoiceCoach

# 运动注册表
EXERCISE_REGISTRY: dict[str, type[ExerciseAnalyzer]] = {
    "pushup": PushupAnalyzer,
}

__all__ = [
    "ExerciseAnalyzer",
    "ExerciseMonitor",
    "RepPhase",
    "RepResult",
    "PushupAnalyzer",
    "VoiceCoach",
    "EXERCISE_REGISTRY",
]
