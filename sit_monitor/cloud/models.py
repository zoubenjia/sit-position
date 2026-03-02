"""云端数据模型"""

from dataclasses import dataclass, field


@dataclass
class UserProfile:
    user_id: str = ""
    device_id: str = ""
    nickname: str = "匿名用户"
    share_posture: bool = True
    share_exercise: bool = True


@dataclass
class DailyReport:
    user_id: str = ""
    report_date: str = ""  # YYYY-MM-DD
    good_checks: int = 0
    bad_checks: int = 0
    good_pct: int = 0
    alerts: int = 0
    sit_alerts: int = 0
    good_minutes: float = 0.0
    bad_minutes: float = 0.0
    total_minutes: float = 0.0


@dataclass
class LeaderboardEntry:
    rank: int = 0
    user_id: str = ""
    nickname: str = ""
    good_pct: int = 0
    total_minutes: float = 0.0
    likes_count: int = 0


@dataclass
class Achievement:
    id: str = ""
    name: str = ""
    description: str = ""
    icon: str = ""
    condition_type: str = ""  # streak, cumulative, single_day, action_count
    condition_value: int = 0


@dataclass
class Challenge:
    id: str = ""
    creator_id: str = ""
    opponent_id: str = ""
    creator_nickname: str = ""
    opponent_nickname: str = ""
    challenge_type: str = "good_pct"  # good_pct, total_minutes
    target_value: int = 80
    duration_days: int = 7
    start_date: str = ""
    end_date: str = ""
    creator_score: float = 0.0
    opponent_score: float = 0.0
    status: str = "pending"  # pending, active, completed
    winner_id: str = ""
