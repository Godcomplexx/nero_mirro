from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# EmotiEffLib emotion backend (optional, graceful fallback to Haar Cascade)
# ---------------------------------------------------------------------------
EMOTIEFFLIB_IMPORT_ERROR = ""
EMOTIEFFLIB_AVAILABLE = False
EMOTIEFFLIB_RUNTIME_ERROR = ""
EMOTIEFFLIB_WARMED = False
_emotion_recognizer = None

EMOTION_MODEL_NAME = os.getenv("NEURO_MIRROR_EMOTION_MODEL", "enet_b2_7").strip() or "enet_b2_7"
EMOTION_ENGINE = os.getenv("NEURO_MIRROR_EMOTION_ENGINE", "onnx").strip().lower() or "onnx"
_GLOBAL_DEVICE = os.getenv("NEURO_MIRROR_DEVICE", "auto").strip().lower() or "auto"
EMOTION_DEVICE = os.getenv("NEURO_MIRROR_EMOTION_DEVICE", _GLOBAL_DEVICE).strip().lower() or _GLOBAL_DEVICE

try:
    from emotiefflib.facial_analysis import EmotiEffLibRecognizer, get_model_list  # type: ignore

    EMOTIEFFLIB_AVAILABLE = True
except Exception as exc:
    EmotiEffLibRecognizer = None
    get_model_list = None
    EMOTIEFFLIB_IMPORT_ERROR = str(exc)

# ---------------------------------------------------------------------------
# Camera settings
# ---------------------------------------------------------------------------
CAMERA_INDEX = int(os.getenv("NEURO_MIRROR_CAMERA_INDEX", "0"))
MAX_CAMERA_INDEX = int(os.getenv("NEURO_MIRROR_CAMERA_MAX_INDEX", "5"))
CAMERA_WIDTH = int(os.getenv("NEURO_MIRROR_CAMERA_WIDTH", "640"))
CAMERA_HEIGHT = int(os.getenv("NEURO_MIRROR_CAMERA_HEIGHT", "480"))
PREVIEW_MAX_WIDTH = int(os.getenv("NEURO_MIRROR_PREVIEW_WIDTH", "640"))
PREVIEW_MAX_HEIGHT = int(os.getenv("NEURO_MIRROR_PREVIEW_HEIGHT", "360"))
FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

BACKENDS: list[tuple[str, int | None]] = [("default", None)]
if hasattr(cv2, "CAP_DSHOW"):
    BACKENDS.append(("dshow", cv2.CAP_DSHOW))
if hasattr(cv2, "CAP_MSMF"):
    BACKENDS.append(("msmf", cv2.CAP_MSMF))

ACTIVE_CAPTURE = None
ACTIVE_CAMERA_INDEX: int | None = None
ACTIVE_BACKEND_NAME = ""
ACTIVE_ATTEMPTS: list[str] = []

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RPPG_REPO_PATH = Path(os.getenv(
    "NEURO_MIRROR_RPPG_REPO_PATH",
    str(PROJECT_ROOT / "external" / "rppg-heart-rate-measurement"),
)).resolve()
RPPG_MODEL_PATH = Path(os.getenv(
    "NEURO_MIRROR_RPPG_MODEL_PATH",
    str(RPPG_REPO_PATH / "results" / "best_results_2" / "cnn.pth"),
)).resolve()
RPPG_DURATION_SECONDS = float(os.getenv("NEURO_MIRROR_RPPG_SECONDS", "20").strip() or "20")
RPPG_TARGET_FPS = float(os.getenv("NEURO_MIRROR_RPPG_FPS", "15").strip() or "15")
RPPG_ENABLED = os.getenv("NEURO_MIRROR_RPPG_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
RPPG_USE_FRAME_DIFF = os.getenv("NEURO_MIRROR_RPPG_USE_FRAME_DIFF", "1").strip().lower() not in {"0", "false", "no"}
RPPG_IMPORT_ERROR = ""
RPPG_MODEL = None
RPPG_MODEL_DEVICE = None
RPPG_FACE_DETECTOR = None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        try:
            request_payload = json.loads(raw_line)
            response_payload = handle_request(request_payload)
        except Exception as exc:
            response_payload = {
                "id": _safe_id(raw_line),
                "ok": False,
                "error": {
                    "code": "worker_exception",
                    "message": str(exc),
                },
            }

        sys.stdout.write(json.dumps(response_payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    return 0


def handle_request(request_payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(request_payload.get("id") or "")
    action = str(request_payload.get("action") or "")

    if action == "health":
        result = build_health()
    elif action == "capture_preview_frame":
        result = capture_preview_frame()
    elif action == "release_camera":
        result = release_camera_action()
    elif action == "analyze_appearance":
        result = analyze_appearance()
    elif action == "analyze_image_file":
        payload = request_payload.get("payload") or {}
        result = analyze_image_file(str(payload.get("image_path") or ""))
    elif action == "analyze_screening":
        result = analyze_screening()
    else:
        return {
            "id": request_id,
            "ok": False,
            "error": {"code": "unknown_action", "message": f"unknown action: {action}"},
        }

    return {"id": request_id, "ok": True, "result": result}


def build_health() -> dict[str, Any]:
    emotion_error = EMOTIEFFLIB_IMPORT_ERROR
    if EMOTIEFFLIB_AVAILABLE:
        emotion_error = ""
    return {
        "worker_available": True,
        "camera_available": ACTIVE_CAPTURE is not None,
        "emotiefflib_available": EMOTIEFFLIB_AVAILABLE and not emotion_error,
        "emotiefflib_error": emotion_error,
        "emotion_model_name": EMOTION_MODEL_NAME,
        "emotion_engine": EMOTION_ENGINE,
        "emotion_device": EMOTION_DEVICE,
        "python_executable": sys.executable,
        "camera_index": ACTIVE_CAMERA_INDEX,
        "camera_backend": ACTIVE_BACKEND_NAME,
        "camera_attempts": ACTIVE_ATTEMPTS,
        "rppg_enabled": RPPG_ENABLED,
        "rppg_repo_path": str(RPPG_REPO_PATH),
        "rppg_model_path": str(RPPG_MODEL_PATH),
        "rppg_available": RPPG_ENABLED and RPPG_REPO_PATH.exists() and RPPG_MODEL_PATH.exists() and not RPPG_IMPORT_ERROR,
        "rppg_error": RPPG_IMPORT_ERROR,
    }


def capture_preview_frame() -> dict[str, Any]:
    started_at = time.perf_counter()
    frame_info = capture_frame_with_info()
    frame = frame_info["frame"]
    if frame is None:
        total_ms = round((time.perf_counter() - started_at) * 1000, 1)
        return {
            "camera_available": False,
            "image_base64": "",
            "face_detected": False,
            "capture_ms": total_ms,
            "encode_ms": 0.0,
            "total_ms": total_ms,
            "camera_index": frame_info["camera_index"],
            "camera_backend": frame_info["backend_name"],
            "camera_attempts": frame_info["attempts"],
        }

    preview_frame = prepare_preview_frame(frame)
    encoded_started_at = time.perf_counter()
    ok, encoded = cv2.imencode(".png", preview_frame)
    encode_ms = round((time.perf_counter() - encoded_started_at) * 1000, 1)
    if not ok:
        return {
            "camera_available": True,
            "image_base64": "",
            "face_detected": False,
            "capture_ms": round((encoded_started_at - started_at) * 1000, 1),
            "encode_ms": encode_ms,
            "total_ms": round((time.perf_counter() - started_at) * 1000, 1),
            "camera_index": frame_info["camera_index"],
            "camera_backend": frame_info["backend_name"],
            "camera_attempts": frame_info["attempts"],
        }

    return {
        "camera_available": True,
        "face_detected": False,
        "face_count": 0,
        "capture_ms": round((encoded_started_at - started_at) * 1000, 1),
        "encode_ms": encode_ms,
        "total_ms": round((time.perf_counter() - started_at) * 1000, 1),
        "image_base64": base64.b64encode(encoded.tobytes()).decode("ascii"),
        "camera_index": frame_info["camera_index"],
        "camera_backend": frame_info["backend_name"],
        "camera_attempts": frame_info["attempts"],
    }


def release_camera_action() -> dict[str, Any]:
    released = ACTIVE_CAPTURE is not None
    release_active_capture()
    return {
        "worker_available": True,
        "camera_available": False,
        "released": released,
    }


def analyze_screening() -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        frames_info = capture_screening_frames(
            duration_seconds=RPPG_DURATION_SECONDS,
            target_fps=RPPG_TARGET_FPS,
        )
        frames = frames_info["frames"]
        frame = frames[-1] if frames else None
        sys.stderr.write(
            f"[worker] capture done: frames={len(frames)} duration={frames_info['duration_seconds']:.1f}s "
            f"fps={frames_info['fps']:.1f} camera={frames_info['camera_index']}\n"
        )
        sys.stderr.flush()
        if frame is None:
            return {
                "analysis_type": "screening",
                "attention_score": 0.25,
                "gaze_stability": 0.0,
                "face_detected": False,
                "face_count": 0,
                "heart_rate_bpm": None,
                "heart_rate_status": "unavailable",
                "camera_index": frames_info["camera_index"],
                "camera_backend": frames_info["backend_name"],
                "camera_attempts": frames_info["attempts"],
                "screening_video_seconds": frames_info["duration_seconds"],
                "screening_frame_count": 0,
                "screening_fps": 0.0,
                "screening_ms": round((time.perf_counter() - started_at) * 1000, 1),
                "notes": "Камера недоступна. OpenCV не смог получить кадры для видео-скрининга.",
            }

        face_boxes = detect_face_regions(frame)
        face_detected = bool(face_boxes)
        sys.stderr.write(
            f"[worker] analyze_screening: frames={len(frames)} fps={frames_info['fps']:.1f} "
            f"face_detected={face_detected}\n"
        )
        sys.stderr.flush()
        rppg_result = estimate_heart_rate_from_frames(frames, fps=float(frames_info["fps"]))
        sys.stderr.write(
            f"[worker] rppg_result: status={rppg_result.get('heart_rate_status')} "
            f"bpm={rppg_result.get('heart_rate_bpm')} "
            f"error={rppg_result.get('heart_rate_error','')[:200]}\n"
        )
        sys.stderr.flush()
        notes = ["Видео-скрининг использует короткое окно кадров с камеры."]
        if rppg_result.get("heart_rate_status") != "ok":
            notes.append(str(rppg_result.get("heart_rate_error") or "Пульс не рассчитан."))

        return {
            "analysis_type": "screening",
            "attention_score": 0.78 if face_detected else 0.42,
            "gaze_stability": 0.72 if face_detected else 0.0,
            "face_detected": face_detected,
            "face_count": len(face_boxes),
            "camera_index": frames_info["camera_index"],
            "camera_backend": frames_info["backend_name"],
            "camera_attempts": frames_info["attempts"],
            "screening_video_seconds": frames_info["duration_seconds"],
            "screening_frame_count": len(frames),
            "screening_fps": round(float(frames_info["fps"]), 2),
            "screening_ms": round((time.perf_counter() - started_at) * 1000, 1),
            "notes": " ".join(notes),
            "source_backend": "vision_worker + rppg",
            **rppg_result,
        }
    finally:
        release_active_capture()


def analyze_appearance() -> dict[str, Any]:
    emotion_error = ensure_emotion_model_ready()
    try:
        frame_info = capture_frame_with_info()
        frame = frame_info["frame"]
        if frame is None:
            return {
                "analysis_type": "appearance",
                "face_detected": False,
                "face_count": 0,
                "emotiefflib_available": EMOTIEFFLIB_AVAILABLE and not emotion_error,
                "confidence": 0.0,
                "emotion": "",
                "appearance_description": "",
                "camera_index": frame_info["camera_index"],
                "camera_backend": frame_info["backend_name"],
                "camera_attempts": frame_info["attempts"],
                "observed": "Кадр с камеры не получен.",
                "notes": "OpenCV не смог открыть ни одну проверенную камеру.",
            }

        result = analyze_appearance_frame(frame, emotion_error=emotion_error)
        result.update(
            {
                "camera_index": frame_info["camera_index"],
                "camera_backend": frame_info["backend_name"],
                "camera_attempts": frame_info["attempts"],
            }
        )
        return result
    finally:
        release_active_capture()


def analyze_image_file(image_path: str) -> dict[str, Any]:
    emotion_error = ensure_emotion_model_ready()
    if not image_path:
        return {
            "analysis_type": "appearance",
            "face_detected": False,
            "face_count": 0,
            "emotiefflib_available": EMOTIEFFLIB_AVAILABLE and not emotion_error,
            "confidence": 0.0,
            "emotion": "",
            "appearance_description": "",
            "observed": "Изображение не передано.",
            "notes": "Путь к изображению пустой.",
        }

    frame = cv2.imread(image_path)
    if frame is None:
        return {
            "analysis_type": "appearance",
            "face_detected": False,
            "face_count": 0,
            "emotiefflib_available": EMOTIEFFLIB_AVAILABLE and not emotion_error,
            "confidence": 0.0,
            "emotion": "",
            "appearance_description": "",
            "observed": "Изображение не удалось прочитать.",
            "notes": f"OpenCV не смог открыть файл: {image_path}",
        }

    result = analyze_appearance_frame(frame, emotion_error=emotion_error)
    result["input_image_path"] = image_path
    return result


def analyze_appearance_frame(frame, *, emotion_error: str) -> dict[str, Any]:
    emotion_result = run_emotion_model(frame)
    if emotion_result is not None and "error" not in emotion_result:
        face_detected = bool(emotion_result.get("face_detected"))
        face_count = int(emotion_result.get("face_count") or 0)
    else:
        face_boxes = detect_face_regions(frame)
        face_detected = bool(face_boxes)
        face_count = len(face_boxes)

    observed_parts: list[str] = []
    notes_parts: list[str] = []
    confidence = 0.75 if face_detected else 0.2
    emotion = ""

    if face_detected:
        observed_parts.append("Лицо в кадре найдено.")
    else:
        observed_parts.append("Лицо не удалось уверенно выделить.")
        notes_parts.append("Попробуйте улучшить освещение или положение камеры.")

    if face_count > 1:
        notes_parts.append(f"В кадре несколько лиц: {face_count}.")

    if emotion_result is not None and "error" not in emotion_result:
        emotion = str(emotion_result.get("dominant_emotion") or "").strip()
        confidence = max(confidence, float(emotion_result.get("confidence") or 0.0))
        if emotion:
            observed_parts.append(f"Эмоция по модели: {emotion}.")
    elif emotion_result and "error" in emotion_result:
        notes_parts.append(f"EmotiEffLib: {emotion_result['error']}")
    elif emotion_error:
        notes_parts.append(f"EmotiEffLib недоступен: {emotion_error}")

    frame_base64 = ""
    try:
        ok_enc, jpeg_buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if ok_enc:
            frame_base64 = base64.b64encode(jpeg_buf.tobytes()).decode("ascii")
    except Exception:
        pass

    return {
        "analysis_type": "appearance",
        "face_detected": face_detected,
        "face_count": face_count,
        "emotiefflib_available": EMOTIEFFLIB_AVAILABLE and not emotion_error,
        "confidence": confidence,
        "emotion": emotion,
        "appearance_description": "",
        "frame_base64": frame_base64,
        "observed": " ".join(observed_parts).strip(),
        "notes": " ".join(notes_parts).strip(),
    }


def capture_frame_with_info() -> dict[str, Any]:
    global ACTIVE_ATTEMPTS

    frame = read_active_frame()
    if frame is not None:
        return {
            "frame": frame,
            "camera_index": ACTIVE_CAMERA_INDEX,
            "backend_name": ACTIVE_BACKEND_NAME,
            "attempts": ACTIVE_ATTEMPTS or [f"{ACTIVE_BACKEND_NAME}:{ACTIVE_CAMERA_INDEX}"],
        }

    attempts: list[str] = []
    indices = [CAMERA_INDEX] + [i for i in range(MAX_CAMERA_INDEX + 1) if i != CAMERA_INDEX]

    for backend_name, backend_value in BACKENDS:
        for index in indices:
            attempts.append(f"{backend_name}:{index}")
            capture = open_capture(index, backend_value)
            if capture is None:
                continue

            frame = read_frame(capture, flush_reads=2)
            if frame is not None:
                set_active_capture(capture, index, backend_name, attempts)
                return {
                    "frame": frame,
                    "camera_index": index,
                    "backend_name": backend_name,
                    "attempts": attempts,
                }

            capture.release()

    release_active_capture()
    ACTIVE_ATTEMPTS = attempts
    return {
        "frame": None,
        "camera_index": None,
        "backend_name": "",
        "attempts": attempts,
    }


def capture_screening_frames(*, duration_seconds: float, target_fps: float) -> dict[str, Any]:
    first = capture_frame_with_info()
    frame = first["frame"]
    if frame is None:
        return {
            "frames": [],
            "camera_index": first["camera_index"],
            "backend_name": first["backend_name"],
            "attempts": first["attempts"],
            "duration_seconds": 0.0,
            "fps": 0.0,
        }

    frames = [frame]
    started_at = time.perf_counter()
    interval = 1.0 / max(target_fps, 1.0)
    max_frames = max(int(duration_seconds * target_fps), 1)
    next_frame_at = started_at + interval

    while len(frames) < max_frames:
        now = time.perf_counter()
        if now - started_at >= duration_seconds:
            break
        if now < next_frame_at:
            time.sleep(min(next_frame_at - now, interval))

        candidate = read_active_frame()
        if candidate is not None:
            frames.append(candidate)
        next_frame_at += interval

    elapsed = max(time.perf_counter() - started_at, 1e-6)
    return {
        "frames": frames,
        "camera_index": first["camera_index"],
        "backend_name": first["backend_name"],
        "attempts": first["attempts"],
        "duration_seconds": round(elapsed, 2),
        "fps": len(frames) / elapsed,
    }


def estimate_heart_rate_from_frames(frames: list[np.ndarray], *, fps: float) -> dict[str, Any]:
    if not RPPG_ENABLED:
        return {
            "heart_rate_bpm": None,
            "heart_rate_status": "disabled",
            "heart_rate_algorithm": "",
            "heart_rate_error": "rPPG отключён через NEURO_MIRROR_RPPG_ENABLED.",
        }
    if len(frames) < max(int(fps * 6), 30):
        return {
            "heart_rate_bpm": None,
            "heart_rate_status": "unavailable",
            "heart_rate_algorithm": "",
            "heart_rate_error": f"Недостаточно кадров для rPPG: {len(frames)}.",
        }

    import traceback
    errors: list[str] = []
    try:
        result = estimate_heart_rate_physnet(frames, fps=fps)
        if result.get("heart_rate_bpm") is not None:
            return result
    except Exception as exc:
        errors.append(f"PhysNet: {exc} | {traceback.format_exc()}")

    try:
        result = estimate_heart_rate_pos(frames, fps=fps)
        if result.get("heart_rate_bpm") is not None:
            if errors:
                result["heart_rate_error"] = "Fallback после ошибки " + "; ".join(errors)
            return result
    except Exception as exc:
        errors.append(f"POS: {exc} | {traceback.format_exc()}")

    return {
        "heart_rate_bpm": None,
        "heart_rate_status": "unavailable",
        "heart_rate_algorithm": "",
        "heart_rate_error": "; ".join(errors) or "rPPG не смог рассчитать пульс.",
    }


def estimate_heart_rate_physnet(frames: list[np.ndarray], *, fps: float) -> dict[str, Any]:
    global RPPG_IMPORT_ERROR, RPPG_MODEL, RPPG_MODEL_DEVICE, RPPG_FACE_DETECTOR

    if not RPPG_REPO_PATH.exists():
        raise RuntimeError(f"rPPG repo not found: {RPPG_REPO_PATH}")
    if not RPPG_MODEL_PATH.exists():
        raise RuntimeError(f"rPPG model not found: {RPPG_MODEL_PATH}")
    if str(RPPG_REPO_PATH) not in sys.path:
        sys.path.insert(0, str(RPPG_REPO_PATH))

    try:
        import torch  # type: ignore
        from src import config as rppg_config  # type: ignore
        from src.face_detector import FaceDetector  # type: ignore
        from src.test import load_model, predict_bvp  # type: ignore
        from src.utils import estimate_hr  # type: ignore
        from src.utils import extract_multi_rois_patches  # type: ignore
    except Exception as exc:
        RPPG_IMPORT_ERROR = str(exc)
        raise

    rppg_config.FACE_MODEL_PATH = str((PROJECT_ROOT / "runtime" / "vision_worker" / "assets" / "face_landmarker.task").resolve())
    rppg_config.FPS_TARGET = int(round(fps)) or 15

    _rppg_device_pref = os.getenv("NEURO_MIRROR_RPPG_DEVICE", _GLOBAL_DEVICE).strip().lower()
    _cuda_available = torch.cuda.is_available()
    if _rppg_device_pref == "cuda":
        device_name = "cuda" if _cuda_available else "cpu"
    elif _rppg_device_pref == "cpu":
        device_name = "cpu"
    else:  # "auto"
        device_name = "cuda" if _cuda_available else "cpu"
    device = torch.device(device_name)
    if RPPG_MODEL is None or RPPG_MODEL_DEVICE != str(device):
        RPPG_MODEL = load_model(str(RPPG_MODEL_PATH), device)
        RPPG_MODEL_DEVICE = str(device)
    if RPPG_FACE_DETECTOR is None:
        RPPG_FACE_DETECTOR = FaceDetector()

    patch_buffer = []
    max_frames = int(getattr(rppg_config, "CNN_WINDOW", 300) or 300)
    for frame in frames[-max_frames:]:
        landmarks = RPPG_FACE_DETECTOR.get_landmarks(frame)
        if landmarks is None:
            continue
        patch_buffer.append(extract_multi_rois_patches(RPPG_FACE_DETECTOR, frame, landmarks))

    if len(patch_buffer) < max(int(fps * 8), 60):
        raise RuntimeError(f"недостаточно кадров с лицом для PhysNet: {len(patch_buffer)}")

    bvp = predict_bvp(RPPG_MODEL, patch_buffer, device, RPPG_USE_FRAME_DIFF)
    bpm = estimate_hr(bvp, fps)
    if bpm is None:
        raise RuntimeError("PhysNet не вернул частоту пульса")

    return {
        "heart_rate_bpm": round(float(bpm), 1),
        "heart_rate_status": "ok",
        "heart_rate_algorithm": "PhysNet",
        "heart_rate_error": "",
    }


def estimate_heart_rate_pos(frames: list[np.ndarray], *, fps: float) -> dict[str, Any]:
    if not RPPG_REPO_PATH.exists():
        raise RuntimeError(f"rPPG repo not found: {RPPG_REPO_PATH}")
    if str(RPPG_REPO_PATH) not in sys.path:
        sys.path.insert(0, str(RPPG_REPO_PATH))

    from models.pos import POS  # type: ignore
    from src.utils import estimate_hr  # type: ignore

    rgb_values: list[np.ndarray] = []
    for frame in frames:
        faces = detect_face_regions(frame)
        if not faces:
            continue
        x, y, w, h = max(faces, key=lambda box: box[2] * box[3])
        y1 = max(y + int(h * 0.12), 0)
        y2 = min(y + int(h * 0.72), frame.shape[0])
        x1 = max(x + int(w * 0.18), 0)
        x2 = min(x + int(w * 0.82), frame.shape[1])
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            continue
        mean_bgr = roi.reshape(-1, 3).mean(axis=0)
        rgb_values.append(np.array([mean_bgr[2], mean_bgr[1], mean_bgr[0]], dtype=np.float32))

    if len(rgb_values) < max(int(fps * 6), 30):
        raise RuntimeError(f"недостаточно кадров с лицом для POS: {len(rgb_values)}")

    bvp = POS(float(fps)).run(np.asarray(rgb_values, dtype=np.float32))
    bpm = estimate_hr(bvp, fps)
    if bpm is None:
        raise RuntimeError("POS не вернул частоту пульса")

    return {
        "heart_rate_bpm": round(float(bpm), 1),
        "heart_rate_status": "ok",
        "heart_rate_algorithm": "POS",
        "heart_rate_error": "",
    }


def open_capture(index: int, backend_value: int | None):
    capture = cv2.VideoCapture(index) if backend_value is None else cv2.VideoCapture(index, backend_value)
    if not capture.isOpened():
        capture.release()
        return None

    capture.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    if hasattr(cv2, "VideoWriter_fourcc"):
        capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return capture


def read_active_frame():
    global ACTIVE_CAPTURE
    if ACTIVE_CAPTURE is None:
        return None

    frame = read_frame(ACTIVE_CAPTURE, flush_reads=1)
    if frame is not None:
        return frame

    release_active_capture()
    return None


def read_frame(capture, *, flush_reads: int):
    frame = None
    for _ in range(max(flush_reads, 1)):
        ok, candidate = capture.read()
        if ok and candidate is not None:
            frame = candidate
    return frame


def set_active_capture(capture, index: int, backend_name: str, attempts: list[str]) -> None:
    global ACTIVE_CAPTURE, ACTIVE_CAMERA_INDEX, ACTIVE_BACKEND_NAME, ACTIVE_ATTEMPTS
    release_active_capture()
    ACTIVE_CAPTURE = capture
    ACTIVE_CAMERA_INDEX = index
    ACTIVE_BACKEND_NAME = backend_name
    ACTIVE_ATTEMPTS = list(attempts)


def release_active_capture() -> None:
    global ACTIVE_CAPTURE, ACTIVE_CAMERA_INDEX, ACTIVE_BACKEND_NAME
    if ACTIVE_CAPTURE is not None:
        ACTIVE_CAPTURE.release()
    ACTIVE_CAPTURE = None
    ACTIVE_CAMERA_INDEX = None
    ACTIVE_BACKEND_NAME = ""


def prepare_preview_frame(frame):
    height, width = frame.shape[:2]
    scale = min(PREVIEW_MAX_WIDTH / width, PREVIEW_MAX_HEIGHT / height, 1.0)
    if scale >= 0.999:
        return frame

    new_size = (max(int(width * scale), 1), max(int(height * scale), 1))
    return cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)


def detect_face_regions(frame) -> list[tuple[int, int, int, int]]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = FACE_CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
    result: list[tuple[int, int, int, int]] = []
    for x, y, w, h in faces:
        result.append((int(x), int(y), int(w), int(h)))
    return result


def run_emotion_model(frame) -> dict[str, Any] | None:
    if ensure_emotion_model_ready():
        return None
    if _emotion_recognizer is None:
        return None

    try:
        face_boxes = detect_face_regions(frame)
        if not face_boxes:
            return {
                "dominant_emotion": "",
                "confidence": 0.0,
                "face_detected": False,
                "face_count": 0,
            }

        face_box = max(face_boxes, key=lambda box: box[2] * box[3])
        face_crop = crop_face(frame, face_box)
        if face_crop.size == 0:
            return {
                "dominant_emotion": "",
                "confidence": 0.0,
                "face_detected": False,
                "face_count": len(face_boxes),
            }

        face_rgb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
        features = _emotion_recognizer.extract_features(face_rgb)
        labels, scores = _emotion_recognizer.classify_emotions(features, logits=False)
        raw_label = str(labels[0]) if labels else ""
        normalized_scores = np.asarray(scores[0])
        confidence = float(np.max(normalized_scores)) if normalized_scores.size else 0.0
        return {
            "dominant_emotion": normalize_emotion_label(raw_label),
            "confidence": round(confidence, 4),
            "face_detected": True,
            "face_count": len(face_boxes),
            "raw_emotion_label": raw_label,
        }
    except Exception as exc:
        return {"error": str(exc)}


def crop_face(frame, box: tuple[int, int, int, int]) -> np.ndarray:
    x, y, w, h = box
    height, width = frame.shape[:2]
    pad_x = int(w * 0.12)
    pad_y = int(h * 0.18)
    x1 = max(x - pad_x, 0)
    y1 = max(y - pad_y, 0)
    x2 = min(x + w + pad_x, width)
    y2 = min(y + h + pad_y, height)
    return frame[y1:y2, x1:x2]


def normalize_emotion_label(raw_label: str) -> str:
    normalized = raw_label.strip().lower()
    mapping = {
        "anger": "злость",
        "angry": "злость",
        "happiness": "радость",
        "happy": "радость",
        "sadness": "грусть",
        "sad": "грусть",
        "surprise": "удивление",
        "fear": "страх",
        "neutral": "спокойствие",
        "disgust": "отвращение",
        "contempt": "презрение",
    }
    return mapping.get(normalized, normalized)


def ensure_emotion_model_ready() -> str:
    global EMOTIEFFLIB_RUNTIME_ERROR, EMOTIEFFLIB_WARMED, _emotion_recognizer

    if not EMOTIEFFLIB_AVAILABLE:
        return EMOTIEFFLIB_IMPORT_ERROR
    if EMOTIEFFLIB_WARMED:
        return EMOTIEFFLIB_RUNTIME_ERROR

    try:
        if get_model_list is None or EmotiEffLibRecognizer is None:
            EMOTIEFFLIB_RUNTIME_ERROR = "EmotiEffLib API is unavailable"
            return EMOTIEFFLIB_RUNTIME_ERROR

        supported_models = set(get_model_list())
        if EMOTION_MODEL_NAME not in supported_models:
            EMOTIEFFLIB_RUNTIME_ERROR = (
                f"unsupported model: {EMOTION_MODEL_NAME}. Supported: {', '.join(sorted(supported_models))}"
            )
            return EMOTIEFFLIB_RUNTIME_ERROR

        if EMOTION_ENGINE not in {"onnx", "torch"}:
            EMOTIEFFLIB_RUNTIME_ERROR = f"unsupported engine: {EMOTION_ENGINE}"
            return EMOTIEFFLIB_RUNTIME_ERROR

        if EMOTION_DEVICE == "auto":
            try:
                import torch as _torch  # type: ignore
                _resolved_emotion_device = "cuda" if _torch.cuda.is_available() else "cpu"
            except Exception:
                _resolved_emotion_device = "cpu"
        else:
            _resolved_emotion_device = EMOTION_DEVICE
        _emotion_recognizer = EmotiEffLibRecognizer(
            engine=EMOTION_ENGINE,
            model_name=EMOTION_MODEL_NAME,
            device=_resolved_emotion_device,
        )

        dummy = np.zeros((224, 224, 3), dtype=np.uint8)
        features = _emotion_recognizer.extract_features(dummy)
        _emotion_recognizer.classify_emotions(features, logits=False)
        EMOTIEFFLIB_RUNTIME_ERROR = ""
        return ""
    except Exception as exc:
        _emotion_recognizer = None
        EMOTIEFFLIB_RUNTIME_ERROR = str(exc)
        return EMOTIEFFLIB_RUNTIME_ERROR
    finally:
        EMOTIEFFLIB_WARMED = True


def _safe_id(raw_line: str) -> str:
    try:
        return str(json.loads(raw_line).get("id") or "")
    except Exception:
        return ""


if __name__ == "__main__":
    raise SystemExit(main())
