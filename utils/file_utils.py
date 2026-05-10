import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_json(path: Path, data: BaseModel | dict[str, Any]) -> None:
    ensure_directory(path.parent)
    if isinstance(data, BaseModel):
        payload = data.model_dump()
    else:
        payload = data
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
