import json
from collections.abc import Iterable

from core.llm_engine import call_llm
from core.result import ErrorResult, SuccessResult
from core.schema import JobDescription, Resume
from utils.bullet_optimizer import optimize_resume_bullets
from utils.cache_utils import llm_cache_key, load_cache, save_cache
from utils.hash_utils import file_hash
from utils.hallucination import detect_hallucination_risks
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
    prompt_template = load_prompt("rewrite_prompt.txt")
    key = llm_cache_key(
        prompt_template,
        {"prompt_file_hash": file_hash(prompt_file)},
        resume.model_dump(),
        job_description.model_dump(),
        mode,
        sorted(locked),
        "localized_bullet_rewrite",
    )
    cached = load_cache("rewritten_resumes", key)
    if cached:
        try:
            return SuccessResult(data=validate_resume_json(cached), debug={"cache_hit": True})
        except ValueError:
            pass

    tailored = resume.model_copy(deep=True)
    debug = {"cache_hit": False, "groups_rewritten": 0, "llm_attempts": 0, "retry_attempts": 0}

    if "experience" not in locked:
        for index, item in enumerate(resume.experience):
            if not item.bullets:
                continue
            result = _rewrite_bullet_group(
                bullets=item.bullets,
                context=f"Experience: {item.role} at {item.company}",
                job_description=job_description,
                mode=mode,
                prompt_template=prompt_template,
                job_title=job_description.title,
            )
            _merge_debug(debug, result.debug)
            if not result.success:
                return ErrorResult(error=result.error, debug=debug)
            tailored.experience[index].bullets = result.data
            debug["groups_rewritten"] += 1

    if "projects" not in locked:
        for index, item in enumerate(resume.projects):
            if not item.bullets:
                continue
            result = _rewrite_bullet_group(
                bullets=item.bullets,
                context=f"Project: {item.name}; allowed technologies: {', '.join(item.technologies)}",
                job_description=job_description,
                mode=mode,
                prompt_template=prompt_template,
                job_title=job_description.title,
            )
            _merge_debug(debug, result.debug)
            if not result.success:
                return ErrorResult(error=result.error, debug=debug)
            tailored.projects[index].bullets = result.data
            debug["groups_rewritten"] += 1

    tailored = optimize_resume_bullets(tailored, locked)
    grounding_error = _grounding_error(resume, tailored)
    if grounding_error:
        return ErrorResult(error=f"Rewrite rejected for unsupported additions: {grounding_error}", debug=debug)

    save_cache("rewritten_resumes", key, tailored)
    return SuccessResult(data=tailored, debug=debug)


def _rewrite_bullet_group(
    bullets: list[str],
    context: str,
    job_description: JobDescription,
    mode: str,
    prompt_template: str,
    job_title: str = "",
) -> SuccessResult[list[str]] | ErrorResult:
    prompt = prompt_template.format(
        mode=mode,
        context=context,
        job_title=job_title or job_description.title or "(not specified)",
        jd_json=json.dumps(job_description.model_dump(), indent=2),
        bullets_json=json.dumps(bullets, indent=2),
        bullet_count=len(bullets),
    )
    response = call_llm(prompt)
    debug = {"llm_attempts": response.attempts}
    if response.ok:
        try:
            return SuccessResult(data=_load_bullets(response.text, len(bullets)), debug=debug)
        except ValueError as exc:
            debug["primary_parse_error"] = str(exc)

    retry_prompt = (
        f"{prompt}\n\n"
        "The previous response was invalid. Return only a JSON array of strings with the same number of bullets. "
        "No markdown, no object, no explanations.\n\n"
        f"Previous response:\n{response.text if response.ok else response.error}"
    )
    retry = call_llm(retry_prompt)
    debug["retry_attempts"] = retry.attempts
    if retry.ok:
        try:
            return SuccessResult(data=_load_bullets(retry.text, len(bullets)), debug=debug)
        except ValueError as exc:
            return ErrorResult(error=f"Bullet rewrite returned malformed output: {exc}", debug=debug)

    return ErrorResult(error=retry.error or response.error or "Bullet rewrite failed.", debug=debug)


def _load_bullets(text: str, expected_count: int) -> list[str]:
    parsed = safe_json_loads(text)
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError("Expected a JSON array of strings.")
    if len(parsed) != expected_count:
        raise ValueError(f"Expected {expected_count} bullets, got {len(parsed)}.")
    return [" ".join(item.split()).strip() for item in parsed]


def _merge_debug(target: dict, source: dict) -> None:
    target["llm_attempts"] += int(source.get("llm_attempts", 0) or 0)
    target["retry_attempts"] += int(source.get("retry_attempts", 0) or 0)
    for key in ("primary_parse_error", "retry_parse_error"):
        if key in source:
            target[key] = source[key]


def _grounding_error(original: Resume, rewritten: Resume) -> str:
    risks = detect_hallucination_risks(original, rewritten)
    errors = []
    if risks["tools_not_present_in_original"]:
        errors.append(f"new tools/technologies: {', '.join(risks['tools_not_present_in_original'])}")
    if risks["invented_metrics"]:
        errors.append(f"new metrics: {', '.join(risks['invented_metrics'])}")
    if risks["invented_companies"]:
        errors.append(f"new companies: {', '.join(risks['invented_companies'])}")
    if risks["invented_projects"]:
        errors.append(f"new projects: {', '.join(risks['invented_projects'])}")
    if risks["invented_publication_indicators"]:
        errors.append(f"publication claims: {', '.join(risks['invented_publication_indicators'])}")

    if len(rewritten.experience) != len(original.experience):
        errors.append("experience count changed")
    if len(rewritten.projects) != len(original.projects):
        errors.append("project count changed")

    for index, (old_exp, new_exp) in enumerate(zip(original.experience, rewritten.experience), start=1):
        if old_exp.company != new_exp.company or old_exp.role != new_exp.role:
            errors.append(f"experience identity changed at item {index}")
        if len(new_exp.bullets) != len(old_exp.bullets):
            errors.append(f"experience bullet count changed at item {index}")

    for index, (old_project, new_project) in enumerate(zip(original.projects, rewritten.projects), start=1):
        if old_project.name != new_project.name or old_project.technologies != new_project.technologies:
            errors.append(f"project identity changed at item {index}")
        if len(new_project.bullets) != len(old_project.bullets):
            errors.append(f"project bullet count changed at item {index}")

    return "; ".join(errors)
