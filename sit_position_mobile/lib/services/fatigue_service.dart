import 'dart:async';
import 'dart:math';
import 'dart:ui' show Size;

import 'package:camera/camera.dart';
import 'package:google_mlkit_face_detection/google_mlkit_face_detection.dart';
import 'package:sit_position_mobile/models/posture_settings.dart';

enum FatigueLevel { normal, tired, veryTired }

class FatigueState {
  final FatigueLevel level;
  final double ear;
  final double mar;
  final double blinkRate;
  final int yawnCount;

  const FatigueState({
    this.level = FatigueLevel.normal,
    this.ear = 0.0,
    this.mar = 0.0,
    this.blinkRate = 0.0,
    this.yawnCount = 0,
  });
}

class FatigueService {
  final PostureSettings settings;

  CameraController? _cameraController;
  FaceDetector? _faceDetector;
  bool _isProcessing = false;
  int _frameCount = 0;

  // EAR/MAR tracking
  bool _eyeClosed = false;
  DateTime? _eyeClosedStart;
  final List<DateTime> _blinkTimes = [];
  bool _mouthOpen = false;
  DateTime? _mouthOpenStart;
  final List<DateTime> _yawnTimes = [];

  final _stateController = StreamController<FatigueState>.broadcast();
  Stream<FatigueState> get stateStream => _stateController.stream;

  final _previewController = StreamController<CameraController?>.broadcast();
  Stream<CameraController?> get previewStream => _previewController.stream;

  bool _running = false;
  bool get isRunning => _running;

  FatigueService({required this.settings});

  Future<void> start() async {
    if (_running) return;

    final cameras = await availableCameras();
    final frontCamera = cameras.firstWhere(
      (c) => c.lensDirection == CameraLensDirection.front,
      orElse: () => cameras.first,
    );

    _cameraController = CameraController(
      frontCamera,
      ResolutionPreset.low,
      enableAudio: false,
      imageFormatGroup: ImageFormatGroup.nv21,
    );

    await _cameraController!.initialize();

    _faceDetector = FaceDetector(
      options: FaceDetectorOptions(
        enableContours: true,
        enableClassification: true,
        performanceMode: FaceDetectorMode.fast,
      ),
    );

    _running = true;
    _frameCount = 0;
    _reset();
    _previewController.add(_cameraController);

    _cameraController!.startImageStream(_onImage);
  }

  void _onImage(CameraImage image) {
    if (!_running || _isProcessing) return;

    // 每 3 帧处理 1 次
    _frameCount++;
    if (_frameCount % 3 != 0) return;

    _isProcessing = true;
    _processImage(image).whenComplete(() => _isProcessing = false);
  }

  Future<void> _processImage(CameraImage image) async {
    try {
      final inputImage = _convertToInputImage(image);
      if (inputImage == null) return;

      final faces = await _faceDetector!.processImage(inputImage);
      if (faces.isEmpty) return;

      final face = faces.first;
      final now = DateTime.now();

      // ML Kit classification: leftEyeOpenProbability, rightEyeOpenProbability
      final leftEyeOpen = face.leftEyeOpenProbability ?? 1.0;
      final rightEyeOpen = face.rightEyeOpenProbability ?? 1.0;

      // EAR approximation from ML Kit eye open probability
      // ML Kit: 1.0 = fully open, 0.0 = closed
      final ear = (leftEyeOpen + rightEyeOpen) / 2.0;

      // MAR from face contours
      double mar = 0.0;
      final upperLip = face.contours[FaceContourType.upperLipTop];
      final lowerLip = face.contours[FaceContourType.lowerLipBottom];

      if (upperLip != null && lowerLip != null) {
        // Use center points of lip contours
        final topCenter = upperLip.points[upperLip.points.length ~/ 2];
        final bottomCenter = lowerLip.points[lowerLip.points.length ~/ 2];

        // Horizontal: left and right corners
        final leftCorner = upperLip.points.first;
        final rightCorner = upperLip.points.last;

        final vertical = _pointDist(topCenter, bottomCenter);
        final horizontal = _pointDist(leftCorner, rightCorner);
        if (horizontal > 0) {
          mar = vertical / horizontal;
        }
      }

      // --- Blink detection ---
      final isClosed = ear < settings.earThreshold;

      if (isClosed) {
        if (!_eyeClosed) {
          _eyeClosed = true;
          _eyeClosedStart = now;
        }
      } else {
        if (_eyeClosed) {
          _blinkTimes.add(now);
          _eyeClosed = false;
          _eyeClosedStart = null;
        }
      }

      // Clean blink window (60s)
      _blinkTimes.removeWhere(
        (t) => now.difference(t).inSeconds > 60,
      );
      final blinkRate = _blinkTimes.length.toDouble();

      // --- Yawn detection ---
      final isMouthOpen = mar > settings.marThreshold;

      if (isMouthOpen) {
        _mouthOpen = true;
        _mouthOpenStart ??= now;
      } else {
        if (_mouthOpen && _mouthOpenStart != null) {
          if (now.difference(_mouthOpenStart!).inMilliseconds >= 500) {
            _yawnTimes.add(now);
          }
          _mouthOpen = false;
          _mouthOpenStart = null;
        }
      }

      // Clean yawn window (5min)
      _yawnTimes.removeWhere(
        (t) => now.difference(t).inMinutes >= 5,
      );
      final yawnCount = _yawnTimes.length;

      // --- Determine fatigue level ---
      var level = FatigueLevel.normal;

      // Long eye closure > 2s
      if (_eyeClosed &&
          _eyeClosedStart != null &&
          now.difference(_eyeClosedStart!).inSeconds >= 2) {
        level = FatigueLevel.veryTired;
      }

      if (level == FatigueLevel.normal) {
        if (blinkRate > 25 || yawnCount >= 3) {
          level = FatigueLevel.tired;
        }
      }

      _stateController.add(FatigueState(
        level: level,
        ear: ear,
        mar: mar,
        blinkRate: blinkRate,
        yawnCount: yawnCount,
      ));
    } catch (_) {
      // Silently ignore processing errors
    }
  }

  double _pointDist(Point<int> a, Point<int> b) {
    final dx = (a.x - b.x).toDouble();
    final dy = (a.y - b.y).toDouble();
    return sqrt(dx * dx + dy * dy);
  }

  InputImage? _convertToInputImage(CameraImage image) {
    final plane = image.planes.first;
    return InputImage.fromBytes(
      bytes: plane.bytes,
      metadata: InputImageMetadata(
        size: Size(image.width.toDouble(), image.height.toDouble()),
        rotation: InputImageRotation.rotation270deg,
        format: InputImageFormat.nv21,
        bytesPerRow: plane.bytesPerRow,
      ),
    );
  }

  void _reset() {
    _eyeClosed = false;
    _eyeClosedStart = null;
    _blinkTimes.clear();
    _mouthOpen = false;
    _mouthOpenStart = null;
    _yawnTimes.clear();
  }

  Future<void> stop() async {
    _running = false;
    if (_cameraController != null) {
      if (_cameraController!.value.isStreamingImages) {
        await _cameraController!.stopImageStream();
      }
      await _cameraController!.dispose();
      _cameraController = null;
    }
    _faceDetector?.close();
    _faceDetector = null;
    _previewController.add(null);
    _reset();
  }

  void dispose() {
    stop();
    _stateController.close();
    _previewController.close();
  }
}
