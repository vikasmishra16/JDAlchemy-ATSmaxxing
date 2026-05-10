from core.llm_engine import call_llm
from core.result import ErrorResult, SuccessResult
from core.schema import JobDescription
from utils.cache_utils import llm_cache_key, load_cache, save_cache
from utils.hash_utils import file_hash
from utils.json_utils import safe_json_loads
from utils.prompt_loader import get_prompt_path, load_prompt


def analyze_jd(jd_text: str) -> SuccessResult[JobDescription] | ErrorResult:
    if len(jd_text.split()) < 20:
        return ErrorResult(
            error="Job description is too short to analyze reliably.",
            debug={"word_count": len(jd_text.split())},
        )

    prompt_file = get_prompt_path("jd_prompt.txt")
    prompt = load_prompt("jd_prompt.txt").format(jd_text=jd_text)
    key = llm_cache_key(prompt, {"prompt_file_hash": file_hash(prompt_file)}, jd_text)
    cached = load_cache("analyzed_jds", key)
    if cached:
        try:
            job_description = JobDescription.model_validate(cached)
            quality_error = _jd_quality_error(job_description)
            if quality_error:
                return ErrorResult(error=quality_error, debug={"source": "cache"})
            return SuccessResult(data=job_description, debug={"cache_hit": True})
        except ValueError:
            pass

    response = call_llm(prompt)
    debug = {"cache_hit": False, "llm_attempts": response.attempts}
    if response.ok:
        try:
            job_description = _load_jd_model(response.text)
            quality_error = _jd_quality_error(job_description)
            if not quality_error:
                save_cache("analyzed_jds", key, job_description)
                return SuccessResult(data=job_description, debug=debug)
            debug["quality_error"] = quality_error
        except (ValueError, TypeError) as exc:
            debug["primary_parse_error"] = str(exc)

    retry_prompt = _json_retry_prompt(prompt, response.text if response.ok else response.error)
    retry = call_llm(retry_prompt)
    debug["retry_attempts"] = retry.attempts
    if retry.ok:
        try:
            job_description = _load_jd_model(retry.text)
            quality_error = _jd_quality_error(job_description)
            if not quality_error:
                save_cache("analyzed_jds", key, job_description)
                return SuccessResult(data=job_description, debug=debug)
            return ErrorResult(error=quality_error, debug=debug)
        except (ValueError, TypeError) as exc:
            debug["retry_parse_error"] = str(exc)
            return ErrorResult(error=f"JD analysis returned malformed JSON: {exc}", debug=debug)

    return ErrorResult(error=retry.error or response.error or "JD analysis failed.", debug=debug)


def _load_jd_model(llm_response: str) -> JobDescription:
    parsed = safe_json_loads(llm_response)
    return JobDescription.model_validate(parsed)


def _json_retry_prompt(original_prompt: str, bad_response: str) -> str:
    return (
        f"{original_prompt}\n\n"
        "The previous response was not valid JSON. Return only corrected JSON with no markdown, no comments, and no explanatory text.\n\n"
        f"Previous response:\n{bad_response}"
    )


def _jd_quality_error(job_description: JobDescription) -> str:
    has_skills = bool(job_description.required_skills or job_description.preferred_skills or job_description.keywords)
    has_responsibilities = bool(job_description.responsibilities)
    if not has_skills and not has_responsibilities:
        return "JD analysis returned no skills, keywords, or responsibilities."
    return ""
