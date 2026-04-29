import hashlib
import json
from typing import Any


def normalize_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def create_hash(payload: dict[str, Any]) -> str:
    normalized = normalize_payload(payload)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
