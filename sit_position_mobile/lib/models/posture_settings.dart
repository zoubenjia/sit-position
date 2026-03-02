import 'package:shared_preferences/shared_preferences.dart';

class PostureSettings {
  /// 角度阈值（度）：超过此角度视为低头
  double angleThreshold;

  /// 持续低头多少秒后提醒
  int badDurationSeconds;

  /// 两次提醒之间的冷却时间（秒）
  int cooldownSeconds;

  /// good streak 多少次才算真正恢复
  int goodStreakRequired;

  /// 是否开启震动
  bool vibrationEnabled;

  /// 是否开启声音提醒
  bool soundEnabled;

  /// 传感器采样间隔（毫秒）
  int sensorIntervalMs;

  /// 疲劳检测（精准模式）
  bool fatigueEnabled;

  /// EAR 阈值：低于此值视为闭眼
  double earThreshold;

  /// MAR 阈值：高于此值视为张嘴
  double marThreshold;

  /// 疲劳提醒冷却时间（秒）
  int fatigueCooldownSeconds;

  PostureSettings({
    this.angleThreshold = 50.0,
    this.badDurationSeconds = 15,
    this.cooldownSeconds = 30,
    this.goodStreakRequired = 3,
    this.vibrationEnabled = true,
    this.soundEnabled = true,
    this.sensorIntervalMs = 200,
    this.fatigueEnabled = false,
    this.earThreshold = 0.2,
    this.marThreshold = 0.6,
    this.fatigueCooldownSeconds = 300,
  });

  static const _keyAngle = 'angle_threshold';
  static const _keyBadDuration = 'bad_duration_seconds';
  static const _keyCooldown = 'cooldown_seconds';
  static const _keyGoodStreak = 'good_streak_required';
  static const _keyVibration = 'vibration_enabled';
  static const _keySound = 'sound_enabled';
  static const _keySensorInterval = 'sensor_interval_ms';
  static const _keyFatigueEnabled = 'fatigue_enabled';
  static const _keyEarThreshold = 'ear_threshold';
  static const _keyMarThreshold = 'mar_threshold';
  static const _keyFatigueCooldown = 'fatigue_cooldown_seconds';

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    angleThreshold = prefs.getDouble(_keyAngle) ?? angleThreshold;
    badDurationSeconds = prefs.getInt(_keyBadDuration) ?? badDurationSeconds;
    cooldownSeconds = prefs.getInt(_keyCooldown) ?? cooldownSeconds;
    goodStreakRequired = prefs.getInt(_keyGoodStreak) ?? goodStreakRequired;
    vibrationEnabled = prefs.getBool(_keyVibration) ?? vibrationEnabled;
    soundEnabled = prefs.getBool(_keySound) ?? soundEnabled;
    sensorIntervalMs = prefs.getInt(_keySensorInterval) ?? sensorIntervalMs;
    fatigueEnabled = prefs.getBool(_keyFatigueEnabled) ?? fatigueEnabled;
    earThreshold = prefs.getDouble(_keyEarThreshold) ?? earThreshold;
    marThreshold = prefs.getDouble(_keyMarThreshold) ?? marThreshold;
    fatigueCooldownSeconds = prefs.getInt(_keyFatigueCooldown) ?? fatigueCooldownSeconds;
  }

  Future<void> save() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setDouble(_keyAngle, angleThreshold);
    await prefs.setInt(_keyBadDuration, badDurationSeconds);
    await prefs.setInt(_keyCooldown, cooldownSeconds);
    await prefs.setInt(_keyGoodStreak, goodStreakRequired);
    await prefs.setBool(_keyVibration, vibrationEnabled);
    await prefs.setBool(_keySound, soundEnabled);
    await prefs.setInt(_keySensorInterval, sensorIntervalMs);
    await prefs.setBool(_keyFatigueEnabled, fatigueEnabled);
    await prefs.setDouble(_keyEarThreshold, earThreshold);
    await prefs.setDouble(_keyMarThreshold, marThreshold);
    await prefs.setInt(_keyFatigueCooldown, fatigueCooldownSeconds);
  }

  PostureSettings copyWith({
    double? angleThreshold,
    int? badDurationSeconds,
    int? cooldownSeconds,
    int? goodStreakRequired,
    bool? vibrationEnabled,
    bool? soundEnabled,
    int? sensorIntervalMs,
    bool? fatigueEnabled,
    double? earThreshold,
    double? marThreshold,
    int? fatigueCooldownSeconds,
  }) {
    return PostureSettings(
      angleThreshold: angleThreshold ?? this.angleThreshold,
      badDurationSeconds: badDurationSeconds ?? this.badDurationSeconds,
      cooldownSeconds: cooldownSeconds ?? this.cooldownSeconds,
      goodStreakRequired: goodStreakRequired ?? this.goodStreakRequired,
      vibrationEnabled: vibrationEnabled ?? this.vibrationEnabled,
      soundEnabled: soundEnabled ?? this.soundEnabled,
      sensorIntervalMs: sensorIntervalMs ?? this.sensorIntervalMs,
      fatigueEnabled: fatigueEnabled ?? this.fatigueEnabled,
      earThreshold: earThreshold ?? this.earThreshold,
      marThreshold: marThreshold ?? this.marThreshold,
      fatigueCooldownSeconds: fatigueCooldownSeconds ?? this.fatigueCooldownSeconds,
    );
  }
}
