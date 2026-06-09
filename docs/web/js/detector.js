import { PoseLandmarker, FilesetResolver }
  from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/vision_bundle.mjs";

let landmarker = null;

// 加载模型（首次约几 MB，浏览器缓存后秒开）
export async function initDetector() {
  const vision = await FilesetResolver.forVisionTasks(
    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm");
  landmarker = await PoseLandmarker.createFromOptions(vision, {
    baseOptions: {
      modelAssetPath:
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
      delegate: "GPU",
    },
    runningMode: "VIDEO",
    numPoses: 1,
  });
}

// 检测一帧。返回 33 点 landmark 数组，或 null（无人）。
export function detect(videoEl, timestampMs) {
  if (!landmarker) return null;
  const res = landmarker.detectForVideo(videoEl, timestampMs);
  if (!res.landmarks || res.landmarks.length === 0) return null;
  return res.landmarks[0];
}
