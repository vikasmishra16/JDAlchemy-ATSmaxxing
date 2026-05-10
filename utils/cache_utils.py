import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

import config
from utils.hash_utils import text_hash


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = PROJECT_ROOT / "cache"


def cache_key(*parts: Any) -> str:
    payload = json.dumps(parts, sort_keys=True, default=str)
    return text_hash(payload)


def llm_cache_key(prompt_text: str, *parts: Any) -> str:
    return cache_key(
        {
            "prompt_version": config.PROMPT_VERSION,
            "model": config.OLLAMA_MODEL,
            "prompt_hash": text_hash(prompt_text),
            "parts": parts,
        }
    )


def cache_path(namespace: str, key: str) -> Path:
    path = CACHE_DIR / namespace
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{key}.json"


def load_cache(namespace: str, key: str) -> dict[str, Any] | None:
    path = cache_path(namespace, key)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_cache(namespace: str, key: str, data: BaseModel | dict[str, Any]) -> None:
    path = cache_path(namespace, key)
    if isinstance(data, BaseModel):
        payload = data.model_dump()
    else:
        payload = data
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
