"""Remove direct identifier fields and contacts from persisted test data."""
from __future__ import annotations

from copy import deepcopy
import re

DROP_KEYS = {
    "user_name", "name", "full_name", "fio", "email", "phone", "address",
    "passport", "document_number", "institution", "avatar", "photo",
    "photo_base64", "frame_base64", "image_base64", "audio_path", "video_path",
}
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-zА-Яа-я]{2,}\b")
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+7|8)[\s()\-]*\d{3}[\s()\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)"
)


def redact_test_data(value):
    """Keep pseudonymous user IDs; do not claim to detect names in free text."""
    if isinstance(value, dict):
        return {
            key: redact_test_data(item)
            for key, item in value.items()
            if str(key).lower() not in DROP_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [redact_test_data(item) for item in value]
    if isinstance(value, str):
        return PHONE_RE.sub("[удалено]", EMAIL_RE.sub("[удалено]", value))
    return deepcopy(value)
