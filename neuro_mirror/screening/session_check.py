"""Контроль условий сессии (ТЗ п.6.3.2): анализ кадра перед тестом.

Проверяет по одному кадру с камеры:
  - есть ли лицо в кадре;
  - достаточно ли освещение (средняя яркость лица/кадра);
  - достаточно ли близко пользователь (доля кадра, занятая лицом).

Возвращает статусы и человекочитаемые подсказки («включите свет»,
«приблизьтесь к экрану», «расположитесь напротив камеры»).
"""
from __future__ import annotations

from typing import Any

# Пороговые значения (яркость 0–255, доля площади кадра 0–1)
BRIGHTNESS_DARK = 55.0      # темно — блокируем запуск
BRIGHTNESS_DIM = 95.0       # тускло — предупреждение
FACE_MIN_RATIO = 0.02       # лицо меньше 2% кадра — слишком далеко


def analyze_frame_conditions(jpeg_bytes: bytes) -> dict[str, Any]:
    import cv2
    import numpy as np

    result: dict[str, Any] = {
        "frame_ok": False,
        "face_detected": False,
        "face_count": 0,
        "face_ratio": 0.0,
        "face_close_enough": False,
        "brightness": 0.0,
        "brightness_ok": False,
        "advice": [],
    }

    array = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if frame is None:
        result["advice"].append("Не удалось получить кадр с камеры.")
        return result
    result["frame_ok"] = True

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    frame_height, frame_width = gray.shape[:2]

    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    faces = cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
    )

    result["face_count"] = len(faces)
    result["face_detected"] = len(faces) > 0

    if len(faces) > 0:
        # Берём самое крупное лицо; яркость меряем по области лица
        x, y, w, h = max(faces, key=lambda box: box[2] * box[3])
        result["face_ratio"] = round(float(w * h) / float(frame_width * frame_height), 4)
        result["face_close_enough"] = result["face_ratio"] >= FACE_MIN_RATIO
        face_region = gray[y:y + h, x:x + w]
        brightness = float(face_region.mean()) if face_region.size else float(gray.mean())
    else:
        brightness = float(gray.mean())

    result["brightness"] = round(brightness, 1)
    result["brightness_ok"] = brightness >= BRIGHTNESS_DARK

    advice = result["advice"]
    if brightness < BRIGHTNESS_DARK:
        advice.append("Слишком темно — включите свет или сядьте лицом к окну.")
    elif brightness < BRIGHTNESS_DIM:
        advice.append("Освещение тусклое — по возможности добавьте света.")
    if not result["face_detected"]:
        advice.append("Лицо не видно — расположитесь напротив камеры.")
    elif not result["face_close_enough"]:
        advice.append("Вы слишком далеко — приблизьтесь к экрану.")

    return result
