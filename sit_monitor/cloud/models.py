"""云端数据模型"""

from dataclasses import dataclass, field

from sit_monitor.i18n import t


@dataclass
class UserProfile:
    user_id: str = ""
    device_id: str = ""
    nickname: str = field(default_factory=lambda: t("cloud.default_nickname"))
    share_posture: bool = True
    share_exercise: bool = True
    avatar_url: str = ""
    auth_provider: str = "device"  # device, google


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


@dataclass
class Battle:
    id: str = ""
    creator_id: str = ""
    opponent_id: str = ""
    status: str = "invite"  # invite, accepted, countdown, active, finished, expired, cancelled
    mode: str = "async"  # async, realtime
    time_limit_seconds: int = 120
    quality_weight: float = 0.3
    # 创建者成绩
    creator_reps: int = 0
    creator_good_reps: int = 0
    creator_form_errors: dict = field(default_factory=dict)
    creator_score: float = 0.0
    creator_duration_seconds: int = 0
    creator_finished_at: str = ""
    # 对手成绩
    opponent_reps: int = 0
    opponent_good_reps: int = 0
    opponent_form_errors: dict = field(default_factory=dict)
    opponent_score: float = 0.0
    opponent_duration_seconds: int = 0
    opponent_finished_at: str = ""
    # 结果
    winner_id: str = ""
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    expires_at: str = ""


@dataclass
class BattleResult:
    """单方对战结果"""
    reps: int = 0
    good_reps: int = 0
    form_errors: dict = field(default_factory=dict)
    score: float = 0.0
    duration_seconds: int = 0
