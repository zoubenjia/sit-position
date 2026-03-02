import 'dart:async';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:sit_position_mobile/models/posture_settings.dart';
import 'package:sit_position_mobile/services/fatigue_service.dart';

class FatigueScreen extends StatefulWidget {
  final PostureSettings settings;

  const FatigueScreen({super.key, required this.settings});

  @override
  State<FatigueScreen> createState() => _FatigueScreenState();
}

class _FatigueScreenState extends State<FatigueScreen> {
  late FatigueService _fatigueService;
  FatigueState _state = const FatigueState();
  CameraController? _cameraController;
  StreamSubscription<FatigueState>? _stateSub;
  StreamSubscription<CameraController?>? _previewSub;
  bool _isRunning = false;

  @override
  void initState() {
    super.initState();
    _fatigueService = FatigueService(settings: widget.settings);

    _stateSub = _fatigueService.stateStream.listen((state) {
      if (mounted) setState(() => _state = state);
    });

    _previewSub = _fatigueService.previewStream.listen((controller) {
      if (mounted) setState(() => _cameraController = controller);
    });
  }

  Future<void> _toggle() async {
    if (_isRunning) {
      await _fatigueService.stop();
    } else {
      await _fatigueService.start();
    }
    if (mounted) {
      setState(() => _isRunning = _fatigueService.isRunning);
    }
  }

  Color _levelColor(FatigueLevel level) {
    switch (level) {
      case FatigueLevel.normal:
        return Colors.green;
      case FatigueLevel.tired:
        return Colors.orange;
      case FatigueLevel.veryTired:
        return Colors.red;
    }
  }

  String _levelText(FatigueLevel level) {
    switch (level) {
      case FatigueLevel.normal:
        return '正常';
      case FatigueLevel.tired:
        return '疲劳';
      case FatigueLevel.veryTired:
        return '非常疲劳';
    }
  }

  IconData _levelIcon(FatigueLevel level) {
    switch (level) {
      case FatigueLevel.normal:
        return Icons.sentiment_satisfied;
      case FatigueLevel.tired:
        return Icons.sentiment_neutral;
      case FatigueLevel.veryTired:
        return Icons.sentiment_very_dissatisfied;
    }
  }

  @override
  Widget build(BuildContext context) {
    final color = _levelColor(_state.level);

    return Scaffold(
      backgroundColor: Colors.grey[50],
      appBar: AppBar(
        title: const Text('精准模式'),
        centerTitle: true,
        elevation: 0,
      ),
      body: SafeArea(
        child: Column(
          children: [
            // Camera preview
            Expanded(
              flex: 3,
              child: Container(
                margin: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(16),
                  color: Colors.black,
                ),
                clipBehavior: Clip.antiAlias,
                child: _isRunning && _cameraController != null && _cameraController!.value.isInitialized
                    ? Stack(
                        fit: StackFit.expand,
                        children: [
                          CameraPreview(_cameraController!),
                          // EAR/MAR overlay
                          Positioned(
                            top: 12,
                            left: 12,
                            child: Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 10,
                                vertical: 6,
                              ),
                              decoration: BoxDecoration(
                                color: Colors.black54,
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    'EAR: ${_state.ear.toStringAsFixed(3)}',
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 13,
                                      fontFamily: 'monospace',
                                    ),
                                  ),
                                  Text(
                                    'MAR: ${_state.mar.toStringAsFixed(3)}',
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 13,
                                      fontFamily: 'monospace',
                                    ),
                                  ),
                                  Text(
                                    'Blinks/min: ${_state.blinkRate.toStringAsFixed(0)}',
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 13,
                                      fontFamily: 'monospace',
                                    ),
                                  ),
                                  Text(
                                    'Yawns (5m): ${_state.yawnCount}',
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 13,
                                      fontFamily: 'monospace',
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                          // Fatigue level badge
                          Positioned(
                            top: 12,
                            right: 12,
                            child: Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 12,
                                vertical: 6,
                              ),
                              decoration: BoxDecoration(
                                color: color.withValues(alpha:0.9),
                                borderRadius: BorderRadius.circular(20),
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Icon(
                                    _levelIcon(_state.level),
                                    color: Colors.white,
                                    size: 18,
                                  ),
                                  const SizedBox(width: 4),
                                  Text(
                                    _levelText(_state.level),
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontWeight: FontWeight.bold,
                                      fontSize: 14,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ],
                      )
                    : Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              Icons.camera_front,
                              size: 64,
                              color: Colors.grey[600],
                            ),
                            const SizedBox(height: 12),
                            Text(
                              '点击下方按钮开启前置摄像头',
                              style: TextStyle(
                                color: Colors.grey[500],
                                fontSize: 14,
                              ),
                            ),
                          ],
                        ),
                      ),
              ),
            ),

            // Status indicators
            Expanded(
              flex: 2,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: Column(
                  children: [
                    // Fatigue level indicator
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: color.withValues(alpha:0.1),
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(color: color.withValues(alpha:0.3)),
                      ),
                      child: Row(
                        children: [
                          Icon(_levelIcon(_state.level), color: color, size: 40),
                          const SizedBox(width: 16),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  '疲劳状态: ${_levelText(_state.level)}',
                                  style: TextStyle(
                                    color: color,
                                    fontWeight: FontWeight.bold,
                                    fontSize: 18,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  '眨眼 ${_state.blinkRate.toStringAsFixed(0)}/min '
                                  '| 哈欠 ${_state.yawnCount}/5min',
                                  style: TextStyle(
                                    color: Colors.grey[600],
                                    fontSize: 13,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),

                    // Info text
                    Text(
                      _isRunning
                          ? '通过前置摄像头实时分析面部特征检测疲劳'
                          : '精准模式使用前置摄像头，较耗电，建议按需开启',
                      style: TextStyle(color: Colors.grey[500], fontSize: 13),
                      textAlign: TextAlign.center,
                    ),
                    const Spacer(),

                    // Start/Stop button
                    SizedBox(
                      width: 200,
                      height: 50,
                      child: ElevatedButton.icon(
                        onPressed: _toggle,
                        icon: Icon(_isRunning ? Icons.stop : Icons.play_arrow),
                        label: Text(
                          _isRunning ? '停止检测' : '开始检测',
                          style: const TextStyle(fontSize: 16),
                        ),
                        style: ElevatedButton.styleFrom(
                          backgroundColor:
                              _isRunning ? Colors.red[400] : Colors.deepPurple,
                          foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(25),
                          ),
                          elevation: 2,
                        ),
                      ),
                    ),
                    const SizedBox(height: 24),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  void dispose() {
    _stateSub?.cancel();
    _previewSub?.cancel();
    _fatigueService.dispose();
    super.dispose();
  }
}
