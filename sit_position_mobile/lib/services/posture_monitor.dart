import 'dart:async';
import 'package:sit_position_mobile/models/posture_settings.dart';
import 'package:sit_position_mobile/services/sensor_service.dart';
import 'package:sit_position_mobile/services/notification_service.dart';
import 'package:sit_position_mobile/services/stats_service.dart';

enum PostureState { good, warning, bad }

/// 姿势监控服务：防抖判定 + 提醒触发
class PostureMonitor {
  final SensorService _sensorService;
  final NotificationService _notificationService;
  final StatsService _statsService;
  PostureSettings settings;

  PostureMonitor({
    required SensorService sensorService,
    required NotificationService notificationService,
    required StatsService statsService,
    required this.settings,
  })  : _sensorService = sensorService,
        _notificationService = notificationService,
        _statsService = statsService;

  StreamSubscription<SensorReading>? _subscription;
  final _stateController = StreamController<PostureState>.broadcast();

  Stream<PostureState> get stateStream => _stateController.stream;

  // 防抖状态
  int _goodStreak = 0;
  DateTime? _badStartTime;
  DateTime? _lastNotifyTime;
  PostureState _currentState = PostureState.good;
  bool _isMonitoring = false;
  BodyOrientation _currentOrientation = BodyOrientation.upright;

  // 好姿势里程碑
  static const _milestones = {
    15 * 60: '已连续保持好姿势 15 分钟，做得好！',
    30 * 60: '连续 30 分钟好姿势，太棒了！',
    60 * 60: '整整一小时好姿势，你是坐姿达人！',
    120 * 60: '连续 2 小时好姿势，钢铁意志！',
  };
  final Set<int> _milestonesHit = {};

  PostureState get currentState => _currentState;
  bool get isMonitoring => _isMonitoring;
  BodyOrientation get currentOrientation => _currentOrientation;

  double get currentBadDuration {
    if (_badStartTime == null) return 0;
    return DateTime.now().difference(_badStartTime!).inMilliseconds / 1000.0;
  }

  void start() {
    if (_isMonitoring) return;
    _isMonitoring = true;
    _resetState();
    _sensorService.start(
      interval: Duration(milliseconds: settings.sensorIntervalMs),
    );
    _subscription = _sensorService.readingStream.listen(_onReading);
    _statsService.recordSessionStart();
  }

  void stop() {
    _isMonitoring = false;
    _subscription?.cancel();
    _subscription = null;
    _sensorService.stop();
    _statsService.recordSessionEnd();
    _resetState();
  }

  int get currentGoodStreakSeconds => _statsService.currentGoodStreakSeconds;

  void _resetState() {
    _goodStreak = 0;
    _badStartTime = null;
    _lastNotifyTime = null;
    _currentState = PostureState.good;
    _currentOrientation = BodyOrientation.upright;
    _milestonesHit.clear();
    _stateController.add(_currentState);
  }

  void _onReading(SensorReading reading) {
    _currentOrientation = reading.orientation;

    // 躺着看手机时，手机水平是正常的，不算低头
    if (reading.orientation == BodyOrientation.lyingDown) {
      _goodStreak++;
      if (_goodStreak >= settings.goodStreakRequired && _badStartTime != null) {
        _badStartTime = null;
      }
      _updateState(PostureState.good);
      return;
    }

    // 站着/坐着：正常的角度判定
    final angle = reading.angle;
    final isBad = angle > settings.angleThreshold;
    final isWarning = angle > settings.angleThreshold * 0.7 && !isBad;
    final now = DateTime.now();

    if (isBad) {
      _goodStreak = 0;
      _milestonesHit.clear();
      _statsService.breakGoodStreak();
      _badStartTime ??= now;

      final badDuration = now.difference(_badStartTime!).inSeconds;

      if (badDuration >= settings.badDurationSeconds) {
        _updateState(PostureState.bad);

        final canNotify = _lastNotifyTime == null ||
            now.difference(_lastNotifyTime!).inSeconds >=
                settings.cooldownSeconds;

        if (canNotify) {
          _notificationService.notify(
            title: '低头提醒',
            body: '你已经低头 ${badDuration}s 了，抬起头来休息一下吧！',
            vibrate: settings.vibrationEnabled,
            playSound: settings.soundEnabled,
          );
          _lastNotifyTime = now;
          _statsService.recordBadPostureAlert();
        }
      } else {
        _updateState(PostureState.warning);
      }

      _statsService.recordBadPostureTick();
    } else if (isWarning) {
      if (_badStartTime == null) {
        _updateState(PostureState.warning);
      }
      _goodStreak = 0;
    } else {
      _goodStreak++;
      _statsService.startGoodStreak();
      if (_goodStreak >= settings.goodStreakRequired && _badStartTime != null) {
        _badStartTime = null;
        _updateState(PostureState.good);
      } else if (_badStartTime == null) {
        _updateState(PostureState.good);
      }
      // 里程碑鼓励
      _checkMilestones();
    }
  }

  void _updateState(PostureState newState) {
    if (_currentState != newState) {
      _currentState = newState;
      _stateController.add(newState);
    }
  }

  void _checkMilestones() {
    final streakSec = _statsService.currentGoodStreakSeconds;
    for (final entry in _milestones.entries) {
      if (streakSec >= entry.key && !_milestonesHit.contains(entry.key)) {
        _milestonesHit.add(entry.key);
        _notificationService.notify(
          title: '姿势里程碑',
          body: entry.value,
          vibrate: settings.vibrationEnabled,
          playSound: settings.soundEnabled,
        );
      }
    }
  }

  void dispose() {
    stop();
    _stateController.close();
  }
}
