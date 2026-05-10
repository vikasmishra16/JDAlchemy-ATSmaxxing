from functools import lru_cache
from pathlib import Path

import config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = PROJECT_ROOT / "prompts"


@lru_cache(maxsize=None)
def load_prompt(file_name: str) -> str:
    prompt_path = get_prompt_path(file_name)
    return prompt_path.read_text(encoding="utf-8")


def get_prompt_path(file_name: str) -> Path:
    prompt_path = PROMPTS_DIR / config.PROMPT_VERSION / file_name
    if not prompt_path.exists():
        prompt_path = PROMPTS_DIR / file_name
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return prompt_path
