from dataclasses import dataclass
from datetime import datetime
import hashlib
from pathlib import Path
import time
from typing import Any, Dict

import requests

import config
from utils.privacy import redact_sensitive_text


MAX_RETRIES = 2
DEBUG_OUTPUT_DIR: Path | None = None


@dataclass
class LLMResponse:
    ok: bool
    text: str = ""
    error: str = ""
    attempts: int = 0


def call_llm(prompt: str) -> LLMResponse:
    payload: Dict[str, Any] = {
        "model": config.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    if hasattr(config, "OLLAMA_OPTIONS"):
        payload["options"] = config.OLLAMA_OPTIONS

    last_error = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                config.OLLAMA_URL,
                json=payload,
                timeout=config.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            text = data.get("response", "").strip()
            _save_debug_response(prompt, text)
            return LLMResponse(
                ok=True,
                text=text,
                attempts=attempt,
            )
        except requests.Timeout:
            last_error = f"Ollama request timed out after {config.REQUEST_TIMEOUT} seconds."
        except requests.ConnectionError:
            last_error = f"Could not connect to Ollama at {config.OLLAMA_URL}. Is Ollama running?"
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            last_error = f"Ollama returned HTTP {status}: {exc}"
        except requests.RequestException as exc:
            last_error = f"Ollama request failed: {exc}"
        except ValueError as exc:
            last_error = f"Ollama API returned invalid JSON: {exc}"

        if attempt < MAX_RETRIES:
            time.sleep(0.6 * attempt)

    return LLMResponse(ok=False, error=last_error, attempts=MAX_RETRIES)


def _save_debug_response(prompt: str, response_text: str) -> None:
    if not config.DEBUG:
        return

    debug_dirs = [Path(__file__).resolve().parents[1] / "debug" / "raw_llm_outputs"]
    if DEBUG_OUTPUT_DIR is not None:
        debug_dirs.append(DEBUG_OUTPUT_DIR)

    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    for debug_dir in debug_dirs:
        debug_dir.mkdir(parents=True, exist_ok=True)
        path = debug_dir / f"{timestamp}_{digest}.txt"
        path.write_text(redact_sensitive_text(response_text), encoding="utf-8")


def set_debug_output_dir(path: Path | None) -> None:
    global DEBUG_OUTPUT_DIR
    DEBUG_OUTPUT_DIR = path
