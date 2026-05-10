import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from config import DEBUG
from core.schema import Resume
from utils.privacy import redact_sensitive_text


def extract_json(text: str) -> str:
    cleaned = _strip_code_fence(text.strip())
    if not cleaned:
        return ""

    parsed = _balanced_json(cleaned, "{", "}")
    if parsed:
        return parsed

    parsed = _balanced_json(cleaned, "[", "]")
    if parsed:
        return parsed

    return cleaned


def safe_json_loads(text: str) -> Any:
    json_text = extract_json(text)
    attempts = [
        json_text,
        _remove_trailing_commas(json_text),
        _quote_unquoted_keys(_remove_trailing_commas(json_text)),
    ]

    last_error = None
    for attempt in attempts:
        try:
            return json.loads(attempt)
        except json.JSONDecodeError as exc:
            last_error = exc

    _save_malformed_json(text)
    raise ValueError(f"Could not parse valid JSON from LLM response: {last_error}")


def validate_resume_json(data: Any) -> Resume:
    return Resume.model_validate(data)


def _strip_code_fence(text: str) -> str:
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _balanced_json(text: str, opening: str, closing: str) -> str:
    start = text.find(opening)
    if start == -1:
        return ""

    depth = 0
    in_string = False
    escape = False

    for index in range(start, len(text)):
        char = text[index]
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    return text[start:].strip()


def _remove_trailing_commas(text: str) -> str:
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _quote_unquoted_keys(text: str) -> str:
    return re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_ -]*)(\s*:)', r'\1"\2"\3', text)


def _save_malformed_json(text: str) -> None:
    if not DEBUG:
        return

    debug_dir = Path(__file__).resolve().parents[1] / "debug" / "malformed_json"
    debug_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    (debug_dir / f"{timestamp}.txt").write_text(redact_sensitive_text(text), encoding="utf-8")
