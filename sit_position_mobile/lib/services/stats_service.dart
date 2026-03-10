import 'package:shared_preferences/shared_preferences.dart';
import 'package:intl/intl.dart';

/// 使用统计服务：记录和查询低头数据
class StatsService {
  static final _dateFmt = DateFormat('yyyy-MM-dd');

  String get _todayKey => _dateFmt.format(DateTime.now());

  // 内存中的当前会话计数（每次 tick 约 200ms）
  int _sessionBadTicks = 0;
  DateTime? _sessionStart;

  // 连续好姿势追踪
  DateTime? _goodStreakStart;
  int _sessionMaxGoodStreakSeconds = 0;

  /// 记录会话开始
  void recordSessionStart() {
    _sessionStart = DateTime.now();
    _sessionBadTicks = 0;
    _goodStreakStart = DateTime.now();
    _sessionMaxGoodStreakSeconds = 0;
  }

  /// 记录会话结束
  Future<void> recordSessionEnd() async {
    if (_sessionStart == null) return;
    final duration = DateTime.now().difference(_sessionStart!).inSeconds;
    _endGoodStreak();
    final prefs = await SharedPreferences.getInstance();
    final key = 'monitor_seconds_$_todayKey';
    final prev = prefs.getInt(key) ?? 0;
    await prefs.setInt(key, prev + duration);
    // 更新历史最大连续好姿势
    final streakKey = 'max_good_streak_$_todayKey';
    final prevStreak = prefs.getInt(streakKey) ?? 0;
    if (_sessionMaxGoodStreakSeconds > prevStreak) {
      await prefs.setInt(streakKey, _sessionMaxGoodStreakSeconds);
    }
    _sessionStart = null;
    _goodStreakStart = null;
  }

  /// 记录一次低头 tick（传感器每次采样时调用）
  Future<void> recordBadPostureTick() async {
    _sessionBadTicks++;
    // 每 25 次（约 5 秒）写一次持久化，减少 IO
    if (_sessionBadTicks % 25 == 0) {
      await _persistBadSeconds(5);
    }
  }

  /// 记录一次低头提醒
  Future<void> recordBadPostureAlert() async {
    final prefs = await SharedPreferences.getInstance();
    final key = 'alerts_$_todayKey';
    final prev = prefs.getInt(key) ?? 0;
    await prefs.setInt(key, prev + 1);
  }

  Future<void> _persistBadSeconds(int seconds) async {
    final prefs = await SharedPreferences.getInstance();
    final key = 'bad_seconds_$_todayKey';
    final prev = prefs.getInt(key) ?? 0;
    await prefs.setInt(key, prev + seconds);
  }

  /// 好姿势开始（从坏姿势恢复时调用）
  void startGoodStreak() {
    _goodStreakStart ??= DateTime.now();
  }

  /// 好姿势中断（进入坏姿势时调用）
  void _endGoodStreak() {
    if (_goodStreakStart != null) {
      final streak = DateTime.now().difference(_goodStreakStart!).inSeconds;
      if (streak > _sessionMaxGoodStreakSeconds) {
        _sessionMaxGoodStreakSeconds = streak;
      }
      _goodStreakStart = null;
    }
  }

  /// 坏姿势开始（中断好姿势连续记录）
  void breakGoodStreak() {
    _endGoodStreak();
  }

  /// 当前连续好姿势秒数
  int get currentGoodStreakSeconds {
    if (_goodStreakStart == null) return 0;
    return DateTime.now().difference(_goodStreakStart!).inSeconds;
  }

  /// 获取指定日期最大连续好姿势秒数
  Future<int> getMaxGoodStreak(DateTime date) async {
    final prefs = await SharedPreferences.getInstance();
    final dateKey = _dateFmt.format(date);
    return prefs.getInt('max_good_streak_$dateKey') ?? 0;
  }

  /// 获取所有已解锁的成就
  Future<List<AchievementData>> getAchievements() async {
    final prefs = await SharedPreferences.getInstance();
    final achievements = <AchievementData>[];
    // 查找历史最大连续好姿势
    int allTimeMaxStreak = 0;
    final now = DateTime.now();
    for (var i = 0; i < 365; i++) {
      final date = now.subtract(Duration(days: i));
      final dateKey = _dateFmt.format(date);
      final streak = prefs.getInt('max_good_streak_$dateKey') ?? 0;
      if (streak > allTimeMaxStreak) allTimeMaxStreak = streak;
    }
    // 当前会话的也要算
    if (currentGoodStreakSeconds > allTimeMaxStreak) {
      allTimeMaxStreak = currentGoodStreakSeconds;
    }
    if (_sessionMaxGoodStreakSeconds > allTimeMaxStreak) {
      allTimeMaxStreak = _sessionMaxGoodStreakSeconds;
    }

    achievements.addAll([
      AchievementData(
        id: 'focus_30', icon: '🎯', name: '专注半小时',
        description: '单次连续保持良好姿势 30 分钟',
        targetMinutes: 30, bestMinutes: allTimeMaxStreak ~/ 60,
        unlocked: allTimeMaxStreak >= 30 * 60,
      ),
      AchievementData(
        id: 'focus_60', icon: '💪', name: '一小时达人',
        description: '单次连续保持良好姿势 60 分钟',
        targetMinutes: 60, bestMinutes: allTimeMaxStreak ~/ 60,
        unlocked: allTimeMaxStreak >= 60 * 60,
      ),
      AchievementData(
        id: 'focus_120', icon: '🏅', name: '钢铁意志',
        description: '单次连续保持良好姿势 120 分钟',
        targetMinutes: 120, bestMinutes: allTimeMaxStreak ~/ 60,
        unlocked: allTimeMaxStreak >= 120 * 60,
      ),
    ]);

    // 使用天数统计成就
    int totalMonitorDays = 0;
    int streakDays = 0;
    int maxStreakDays = 0;
    for (var i = 0; i < 30; i++) {
      final date = now.subtract(Duration(days: i));
      final dateKey = _dateFmt.format(date);
      final monitorSec = prefs.getInt('monitor_seconds_$dateKey') ?? 0;
      if (monitorSec > 0) {
        totalMonitorDays++;
        streakDays++;
        if (streakDays > maxStreakDays) maxStreakDays = streakDays;
      } else {
        streakDays = 0;
      }
    }
    achievements.addAll([
      AchievementData(
        id: 'first_day', icon: '🌟', name: '初次打卡',
        description: '首次使用坐姿监控',
        targetMinutes: 1, bestMinutes: totalMonitorDays,
        unlocked: totalMonitorDays >= 1,
      ),
      AchievementData(
        id: 'streak_3', icon: '🔥', name: '三日连胜',
        description: '连续 3 天使用坐姿监控',
        targetMinutes: 3, bestMinutes: maxStreakDays,
        unlocked: maxStreakDays >= 3,
      ),
      AchievementData(
        id: 'streak_7', icon: '👑', name: '周冠军',
        description: '连续 7 天使用坐姿监控',
        targetMinutes: 7, bestMinutes: maxStreakDays,
        unlocked: maxStreakDays >= 7,
      ),
    ]);

    return achievements;
  }

  /// 获取今日统计
  Future<DailyStats> getTodayStats() async {
    return getStatsForDate(DateTime.now());
  }

  /// 获取指定日期统计
  Future<DailyStats> getStatsForDate(DateTime date) async {
    final prefs = await SharedPreferences.getInstance();
    final dateKey = _dateFmt.format(date);
    return DailyStats(
      date: date,
      alertCount: prefs.getInt('alerts_$dateKey') ?? 0,
      badPostureSeconds: prefs.getInt('bad_seconds_$dateKey') ?? 0,
      monitorSeconds: prefs.getInt('monitor_seconds_$dateKey') ?? 0,
    );
  }

  /// 获取最近 N 天的统计
  Future<List<DailyStats>> getWeeklyStats({int days = 7}) async {
    final stats = <DailyStats>[];
    final now = DateTime.now();
    for (var i = days - 1; i >= 0; i--) {
      final date = now.subtract(Duration(days: i));
      stats.add(await getStatsForDate(date));
    }
    return stats;
  }
}

class DailyStats {
  final DateTime date;
  final int alertCount;
  final int badPostureSeconds;
  final int monitorSeconds;

  DailyStats({
    required this.date,
    required this.alertCount,
    required this.badPostureSeconds,
    required this.monitorSeconds,
  });

  /// 低头占比
  double get badPostureRatio {
    if (monitorSeconds == 0) return 0;
    return badPostureSeconds / monitorSeconds;
  }

  /// 格式化低头时长
  String get badPostureDurationText {
    if (badPostureSeconds < 60) return '$badPostureSeconds秒';
    if (badPostureSeconds < 3600) return '${badPostureSeconds ~/ 60}分钟';
    return '${badPostureSeconds ~/ 3600}小时${(badPostureSeconds % 3600) ~/ 60}分钟';
  }

  /// 格式化监控时长
  String get monitorDurationText {
    if (monitorSeconds < 60) return '$monitorSeconds秒';
    if (monitorSeconds < 3600) return '${monitorSeconds ~/ 60}分钟';
    return '${monitorSeconds ~/ 3600}小时${(monitorSeconds % 3600) ~/ 60}分钟';
  }
}

class AchievementData {
  final String id;
  final String icon;
  final String name;
  final String description;
  final int targetMinutes;
  final int bestMinutes;
  final bool unlocked;

  AchievementData({
    required this.id,
    required this.icon,
    required this.name,
    required this.description,
    required this.targetMinutes,
    required this.bestMinutes,
    required this.unlocked,
  });

  double get progress {
    if (targetMinutes <= 0) return unlocked ? 1.0 : 0.0;
    return (bestMinutes / targetMinutes).clamp(0.0, 1.0);
  }
}
