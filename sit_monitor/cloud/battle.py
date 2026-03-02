"""俯卧撑对战：评分算法 + 状态管理"""

from enum import Enum


class BattleStatus(str, Enum):
    INVITE = "invite"
    ACCEPTED = "accepted"
    COUNTDOWN = "countdown"
    ACTIVE = "active"
    FINISHED = "finished"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class BattleMode(str, Enum):
    ASYNC = "async"
    REALTIME = "realtime"


class RepQuality(str, Enum):
    GOOD = "good"
    SHALLOW = "shallow"
    BAD = "bad"


def calculate_battle_score(
    reps: int,
    good_reps: int,
    quality_weight: float = 0.3,
) -> float:
    """计算对战分数。

    score = reps × (1 - quality_weight + quality_weight × good_reps / reps)

    满分 = reps（全部 good），最低 = reps × (1 - quality_weight)
    quality_weight=0.3 时，烂动作打 7 折。
    """
    if reps <= 0:
        return 0.0
    good_ratio = min(good_reps, reps) / reps
    return round(reps * (1.0 - quality_weight + quality_weight * good_ratio), 2)


def determine_winner(
    creator_score: float,
    opponent_score: float,
    creator_id: str,
    opponent_id: str,
) -> str:
    """决定胜者，返回 winner_id。平局返回空字符串。"""
    if creator_score > opponent_score:
        return creator_id
    elif opponent_score > creator_score:
        return opponent_id
    return ""
