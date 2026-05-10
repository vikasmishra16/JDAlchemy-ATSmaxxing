import shutil
from pathlib import Path

import requests

from config import OLLAMA_MODEL, OLLAMA_URL, PROMPT_VERSION


PROJECT_ROOT = Path(__file__).resolve().parent
REQUIRED_FOLDERS = [
    "core",
    "utils",
    "templates",
    "prompts",
    f"prompts/{PROMPT_VERSION}",
    "data",
    "output",
    "cache",
    "test_data",
]
REQUIRED_PROMPTS = [
    "parser_prompt.txt",
    "jd_prompt.txt",
    "rewrite_prompt.txt",
    "cover_letter_prompt.txt",
]


def main() -> None:
    checks = [
        ("Ollama API", check_ollama_api()),
        (f"Ollama model '{OLLAMA_MODEL}'", check_ollama_model()),
        ("pdflatex", check_pdflatex()),
        ("required folders", check_folders()),
        ("prompt files", check_prompts()),
    ]

    print("JD-Align Health Check")
    print("-" * 72)
    for name, result in checks:
        status = "OK" if result["ok"] else "FAIL"
        print(f"{status:4} {name}: {result['message']}")
    print("-" * 72)
    failed = [name for name, result in checks if not result["ok"]]
    if failed:
        print("Health check failed. Fix the failed items before running the app.")
    else:
        print("Health check passed.")


def check_ollama_api() -> dict[str, object]:
    try:
        response = requests.get(_ollama_base_url() + "/api/tags", timeout=5)
        response.raise_for_status()
        return {"ok": True, "message": "Ollama is reachable."}
    except requests.RequestException as exc:
        return {"ok": False, "message": f"Ollama is not reachable: {exc}"}


def check_ollama_model() -> dict[str, object]:
    try:
        response = requests.get(_ollama_base_url() + "/api/tags", timeout=5)
        response.raise_for_status()
        models = response.json().get("models", [])
        names = {model.get("name", "").split(":")[0] for model in models}
        if OLLAMA_MODEL in names:
            return {"ok": True, "message": "Model is installed."}
        return {"ok": False, "message": f"Run: ollama pull {OLLAMA_MODEL}"}
    except requests.RequestException as exc:
        return {"ok": False, "message": f"Could not inspect models: {exc}"}


def check_pdflatex() -> dict[str, object]:
    path = shutil.which("pdflatex")
    if path:
        return {"ok": True, "message": path}
    return {"ok": False, "message": "pdflatex is not on PATH."}


def check_folders() -> dict[str, object]:
    missing = [folder for folder in REQUIRED_FOLDERS if not (PROJECT_ROOT / folder).exists()]
    if not missing:
        return {"ok": True, "message": "All required folders exist."}
    return {"ok": False, "message": "Missing: " + ", ".join(missing)}


def check_prompts() -> dict[str, object]:
    prompt_dir = PROJECT_ROOT / "prompts" / PROMPT_VERSION
    missing = [name for name in REQUIRED_PROMPTS if not (prompt_dir / name).exists()]
    if not missing:
        return {"ok": True, "message": f"Prompt version '{PROMPT_VERSION}' is complete."}
    return {"ok": False, "message": "Missing: " + ", ".join(missing)}


def _ollama_base_url() -> str:
    return OLLAMA_URL.replace("/api/generate", "").rstrip("/")


if __name__ == "__main__":
    main()
