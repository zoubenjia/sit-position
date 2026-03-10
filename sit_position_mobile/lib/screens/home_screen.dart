import 'dart:async';
import 'package:flutter/material.dart';
import 'package:sit_position_mobile/models/posture_settings.dart';
import 'package:sit_position_mobile/services/sensor_service.dart';
import 'package:sit_position_mobile/services/posture_monitor.dart';
import 'package:sit_position_mobile/services/notification_service.dart';
import 'package:sit_position_mobile/services/stats_service.dart';
import 'package:sit_position_mobile/screens/settings_screen.dart';
import 'package:sit_position_mobile/screens/stats_screen.dart';
import 'package:sit_position_mobile/screens/fatigue_screen.dart';
import 'package:sit_position_mobile/screens/achievements_screen.dart';
import 'package:sit_position_mobile/widgets/angle_gauge.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  late final SensorService _sensorService;
  late final NotificationService _notificationService;
  late final StatsService _statsService;
  late final PostureMonitor _monitor;
  late PostureSettings _settings;

  double _currentAngle = 0.0;
  PostureState _currentState = PostureState.good;
  BodyOrientation _currentOrientation = BodyOrientation.upright;
  bool _isMonitoring = false;

  StreamSubscription<SensorReading>? _readingSub;
  StreamSubscription<PostureState>? _stateSub;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _initServices();
  }

  Future<void> _initServices() async {
    _settings = PostureSettings();
    await _settings.load();

    _sensorService = SensorService();
    _notificationService = NotificationService();
    _statsService = StatsService();

    await _notificationService.init();

    _monitor = PostureMonitor(
      sensorService: _sensorService,
      notificationService: _notificationService,
      statsService: _statsService,
      settings: _settings,
    );

    _readingSub = _sensorService.readingStream.listen((reading) {
      setState(() {
        _currentAngle = reading.angle;
        _currentOrientation = reading.orientation;
      });
    });

    _stateSub = _monitor.stateStream.listen((state) {
      setState(() => _currentState = state);
    });

    setState(() {});
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {}

  void _toggleMonitoring() {
    setState(() {
      if (_isMonitoring) {
        _monitor.stop();
      } else {
        _monitor.settings = _settings;
        _monitor.start();
      }
      _isMonitoring = _monitor.isMonitoring;
    });
  }

  void _openSettings() async {
    final result = await Navigator.push<PostureSettings>(
      context,
      MaterialPageRoute(
        builder: (_) => SettingsScreen(settings: _settings),
      ),
    );
    if (result != null) {
      setState(() {
        _settings = result;
        _monitor.settings = _settings;
      });
    }
  }

  void _openFatigue() {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => FatigueScreen(settings: _settings),
      ),
    );
  }

  void _openStats() {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => StatsScreen(statsService: _statsService),
      ),
    );
  }

  void _openAchievements() {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => AchievementsScreen(statsService: _statsService),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isLyingDown = _currentOrientation == BodyOrientation.lyingDown;

    return Scaffold(
      backgroundColor: Colors.grey[50],
      appBar: AppBar(
        title: const Text('低头族检测'),
        centerTitle: true,
        elevation: 0,
        actions: [
          IconButton(
            icon: const Icon(Icons.face_retouching_natural),
            onPressed: _openFatigue,
            tooltip: '精准模式',
          ),
          IconButton(
            icon: const Icon(Icons.emoji_events),
            onPressed: _openAchievements,
            tooltip: '成就',
          ),
          IconButton(
            icon: const Icon(Icons.bar_chart),
            onPressed: _openStats,
            tooltip: '统计',
          ),
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: _openSettings,
            tooltip: '设置',
          ),
        ],
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                // 躺着检测提示
                if (_isMonitoring && isLyingDown)
                  Container(
                    margin: const EdgeInsets.only(bottom: 16),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 16,
                      vertical: 10,
                    ),
                    decoration: BoxDecoration(
                      color: Colors.blue[50],
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.airline_seat_flat,
                            color: Colors.blue[400], size: 20),
                        const SizedBox(width: 8),
                        Text(
                          '检测到躺姿，已暂停低头提醒',
                          style: TextStyle(
                            color: Colors.blue[700],
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ],
                    ),
                  ),

                AngleGauge(
                  angle: _currentAngle,
                  state: _currentState,
                  threshold: _settings.angleThreshold,
                ),
                const SizedBox(height: 32),

                // 低头持续时间
                if (_isMonitoring &&
                    !isLyingDown &&
                    _monitor.currentBadDuration > 0)
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 20,
                      vertical: 12,
                    ),
                    decoration: BoxDecoration(
                      color: Colors.red[50],
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.timer, color: Colors.red[400], size: 20),
                        const SizedBox(width: 8),
                        Text(
                          '低头 ${_monitor.currentBadDuration.toStringAsFixed(0)}s / ${_settings.badDurationSeconds}s',
                          style: TextStyle(
                            color: Colors.red[700],
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ],
                    ),
                  ),
                // 好姿势连续时间
                if (_isMonitoring &&
                    !isLyingDown &&
                    _monitor.currentBadDuration == 0 &&
                    _monitor.currentGoodStreakSeconds >= 60)
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 20,
                      vertical: 12,
                    ),
                    decoration: BoxDecoration(
                      color: Colors.green[50],
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.emoji_events,
                            color: Colors.green[600], size: 20),
                        const SizedBox(width: 8),
                        Text(
                          '好姿势连续 ${_monitor.currentGoodStreakSeconds ~/ 60} 分钟',
                          style: TextStyle(
                            color: Colors.green[700],
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ],
                    ),
                  ),
                const SizedBox(height: 32),

                // 开始/停止按钮
                SizedBox(
                  width: 200,
                  height: 56,
                  child: ElevatedButton.icon(
                    onPressed: _toggleMonitoring,
                    icon: Icon(_isMonitoring ? Icons.stop : Icons.play_arrow),
                    label: Text(
                      _isMonitoring ? '停止监控' : '开始监控',
                      style: const TextStyle(fontSize: 18),
                    ),
                    style: ElevatedButton.styleFrom(
                      backgroundColor:
                          _isMonitoring ? Colors.red[400] : Colors.green[600],
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(28),
                      ),
                      elevation: 2,
                    ),
                  ),
                ),
                const SizedBox(height: 24),

                // 监控状态信息
                if (!_isMonitoring)
                  Text(
                    '点击开始监控你的手机使用姿势',
                    style: TextStyle(color: Colors.grey[500], fontSize: 14),
                  ),
                if (_isMonitoring)
                  Text(
                    '阈值 ${_settings.angleThreshold.toStringAsFixed(0)}° · '
                    '${_settings.badDurationSeconds}s 后提醒',
                    style: TextStyle(color: Colors.grey[500], fontSize: 14),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _readingSub?.cancel();
    _stateSub?.cancel();
    _monitor.dispose();
    _sensorService.dispose();
    _notificationService.dispose();
    super.dispose();
  }
}
