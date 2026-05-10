import json

from core.llm_engine import call_llm
from core.result import ErrorResult, SuccessResult
from core.schema import JobDescription, Resume
from utils.prompt_loader import load_prompt


def generate_cover_letter(resume: Resume, job_description: JobDescription) -> SuccessResult[str] | ErrorResult:
    prompt = load_prompt("cover_letter_prompt.txt").format(
        resume_json=json.dumps(resume.model_dump(), indent=2),
        jd_json=json.dumps(job_description.model_dump(), indent=2),
    )
    response = call_llm(prompt)
    if not response.ok:
        return ErrorResult(error=response.error or "Cover letter generation failed.", debug={"llm_attempts": response.attempts})

    cover_letter = _limit_words(response.text.strip(), 300)
    if not cover_letter:
        return ErrorResult(error="Cover letter generation returned empty output.", debug={"llm_attempts": response.attempts})

    return SuccessResult(data=cover_letter, debug={"llm_attempts": response.attempts})


def _limit_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(".,;:") + "."
