import json
from collections.abc import Iterable

from core.llm_engine import call_llm
from core.result import ErrorResult, SuccessResult
from core.schema import JobDescription, Resume
from core.skills import reorder_skills_by_relevance
from utils.bullet_optimizer import optimize_resume_bullets
from utils.cache_utils import llm_cache_key, load_cache, save_cache
from utils.hash_utils import file_hash
from utils.json_utils import safe_json_loads, validate_resume_json
from utils.prompt_loader import get_prompt_path, load_prompt


def tailor_resume(
    resume: Resume,
    job_description: JobDescription,
    mode: str = "Balanced",
    locked_sections: Iterable[str] | None = None,
) -> SuccessResult[Resume] | ErrorResult:
    locked = set(locked_sections or [])
    prompt_file = get_prompt_path("rewrite_prompt.txt")
    prompt = load_prompt("rewrite_prompt.txt").format(
        resume_json=json.dumps(resume.model_dump(), indent=2),
        jd_json=json.dumps(job_description.model_dump(), indent=2),
        mode=mode,
        locked_sections=", ".join(sorted(locked)) or "none",
    )
    key = llm_cache_key(
        prompt,
        {"prompt_file_hash": file_hash(prompt_file)},
        resume.model_dump(),
        job_description.model_dump(),
        mode,
        sorted(locked),
    )
    cached = load_cache("rewritten_resumes", key)
    if cached:
        try:
            tailored = validate_resume_json(cached)
            return SuccessResult(data=tailored, debug={"cache_hit": True})
        except ValueError:
            pass

    response = call_llm(prompt)
    debug = {"cache_hit": False, "llm_attempts": response.attempts}
    if response.ok:
        try:
            tailored = _load_tailored_resume(response.text)
            tailored = _post_process_resume(resume, tailored, job_description, locked)
            save_cache("rewritten_resumes", key, tailored)
            return SuccessResult(data=tailored, debug=debug)
        except ValueError as exc:
            debug["primary_parse_error"] = str(exc)

    retry_prompt = _json_retry_prompt(prompt, response.text if response.ok else response.error)
    retry = call_llm(retry_prompt)
    debug["retry_attempts"] = retry.attempts
    if retry.ok:
        try:
            tailored = _load_tailored_resume(retry.text)
            tailored = _post_process_resume(resume, tailored, job_description, locked)
            save_cache("rewritten_resumes", key, tailored)
            return SuccessResult(data=tailored, debug=debug)
        except ValueError as exc:
            return ErrorResult(error=f"Rewrite returned malformed JSON: {exc}", debug=debug)

    return ErrorResult(error=retry.error or response.error or "Resume rewrite failed.", debug=debug)


def _load_tailored_resume(llm_response: str) -> Resume:
    try:
        parsed = safe_json_loads(llm_response)
        return validate_resume_json(parsed)
    except (ValueError, TypeError):
        raise ValueError("Could not parse rewritten resume JSON.")


def _post_process_resume(
    original: Resume,
    tailored: Resume,
    job_description: JobDescription,
    locked_sections: set[str],
) -> Resume:
    result = tailored.model_copy(deep=True)

    if "education" in locked_sections:
        result.education = original.education
        result.certifications = original.certifications
    if "projects" in locked_sections:
        result.projects = original.projects
    if "skills" in locked_sections:
        result.skills = original.skills
    else:
        result = reorder_skills_by_relevance(result, job_description)
    if "experience" in locked_sections:
        result.experience = original.experience

    return optimize_resume_bullets(result, locked_sections)


def _json_retry_prompt(original_prompt: str, bad_response: str) -> str:
    return (
        f"{original_prompt}\n\n"
        "The previous response was not valid JSON. Return only corrected JSON with no markdown, no comments, and no explanatory text.\n\n"
        f"Previous response:\n{bad_response}"
    )
