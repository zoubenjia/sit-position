"""Settings dataclass + JSON 持久化"""

import json
import os
import uuid
from dataclasses import asdict, dataclass, field

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH = os.path.join(SCRIPT_DIR, "settings.json")


@dataclass
class Settings:
    shoulder_threshold: float = 10.0
    neck_threshold: float = 20.0
    torso_threshold: float = 8.0
    head_tilt_threshold: float = 8.0
    interval: float = 5.0
    bad_seconds: int = 30
    cooldown: int = 180
    sit_max_minutes: int = 45
    away_seconds: float = 3.0
    sound: bool = False
    auto_pause: bool = False
    camera: int = 0
    browser: str = ""
    # Fatigue detection
    fatigue_enabled: bool = True
    ear_threshold: float = 0.2       # EAR < 此值 = 闭眼
    mar_threshold: float = 0.6       # MAR > 此值 = 张嘴
    fatigue_cooldown: int = 300      # 疲劳提醒最小间隔（秒）
    # Cloud / Social
    cloud_enabled: bool = False
    nickname: str = "匿名用户"
    device_id: str = ""
    share_posture: bool = True
    share_exercise: bool = True
    supabase_refresh_token: str = ""
    # Auth
    auth_provider: str = "device"  # device, google
    # UI
    simple_mode: bool = True  # True=精简菜单, False=完整菜单

    def ensure_device_id(self):
        """首次启动时自动生成设备 ID 并保存"""
        if not self.device_id:
            self.device_id = uuid.uuid4().hex[:12]
            self.save()

    @property
    def thresholds(self):
        return {
            "shoulder": self.shoulder_threshold,
            "neck": self.neck_threshold,
            "torso": self.torso_threshold,
            "head_tilt": self.head_tilt_threshold,
        }

    def save(self, path=None):
        """保存设置到 JSON 文件"""
        p = path or SETTINGS_PATH
        with open(p, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path=None):
        """从 JSON 文件加载设置，文件不存在则返回默认值"""
        p = path or SETTINGS_PATH
        if not os.path.exists(p):
            return cls()
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 只取已知字段
            known = {f.name for f in cls.__dataclass_fields__.values()}
            filtered = {k: v for k, v in data.items() if k in known}
            return cls(**filtered)
        except (json.JSONDecodeError, TypeError):
            return cls()

    def apply_args(self, args):
        """用 CLI 参数覆盖设置（CLI 优先但不保存到文件）"""
        if args.shoulder_threshold != 10.0:
            self.shoulder_threshold = args.shoulder_threshold
        if args.neck_threshold != 20.0:
            self.neck_threshold = args.neck_threshold
        if args.torso_threshold != 8.0:
            self.torso_threshold = args.torso_threshold
        if args.interval != 5.0:
            self.interval = args.interval
        if args.bad_seconds != 30:
            self.bad_seconds = args.bad_seconds
        if args.cooldown != 180:
            self.cooldown = args.cooldown
        if args.sit_max_minutes != 45:
            self.sit_max_minutes = args.sit_max_minutes
        if args.away_seconds != 3.0:
            self.away_seconds = args.away_seconds
        if args.sound:
            self.sound = True
        if args.auto_pause:
            self.auto_pause = True
        if args.camera != 0:
            self.camera = args.camera
        if args.browser:
            self.browser = args.browser
