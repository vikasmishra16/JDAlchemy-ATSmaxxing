from pathlib import Path

import pdfplumber
from docx import Document

from core.llm_engine import call_llm
from core.result import ErrorResult, SuccessResult
from core.schema import Resume
from utils.cache_utils import llm_cache_key, load_cache, save_cache
from utils.hash_utils import file_hash
from utils.json_utils import safe_json_loads, validate_resume_json
from utils.prompt_loader import get_prompt_path, load_prompt


def read_pdf(file_path: str) -> str:
    text_parts = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
    return "\n".join(text_parts).strip()


def read_docx(file_path: str) -> str:
    document = Document(file_path)
    paragraphs = [paragraph.text for paragraph in document.paragraphs]
    return "\n".join(paragraphs).strip()


def extract_raw_text(file_path: str) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return read_pdf(file_path)
    if suffix == ".docx":
        return read_docx(file_path)

    raise ValueError("Unsupported resume format. Please upload a PDF or DOCX file.")


def _load_resume_model(llm_response: str) -> Resume:
    parsed = safe_json_loads(llm_response)
    return validate_resume_json(parsed)


def raw_text_to_resume(raw_text: str) -> SuccessResult[Resume] | ErrorResult:
    if len(raw_text.split()) < 40:
        return ErrorResult(
            error="Resume text extraction produced too little content to parse reliably.",
            debug={"word_count": len(raw_text.split())},
        )

    prompt_file = get_prompt_path("parser_prompt.txt")
    prompt = load_prompt("parser_prompt.txt").format(raw_text=raw_text)
    key = llm_cache_key(prompt, {"prompt_file_hash": file_hash(prompt_file)}, raw_text)
    cached = load_cache("parsed_resumes", key)
    if cached:
        try:
            resume = validate_resume_json(cached)
            quality_error = _resume_quality_error(resume)
            if quality_error:
                return ErrorResult(error=quality_error, debug={"source": "cache"})
            return SuccessResult(data=resume, debug={"cache_hit": True})
        except ValueError:
            pass

    response = call_llm(prompt)
    debug = {"cache_hit": False, "llm_attempts": response.attempts}
    if response.ok:
        try:
            resume = _load_resume_model(response.text)
            quality_error = _resume_quality_error(resume)
            if not quality_error:
                save_cache("parsed_resumes", key, resume)
                return SuccessResult(data=resume, debug=debug)
            debug["quality_error"] = quality_error
        except (ValueError, TypeError) as exc:
            debug["primary_parse_error"] = str(exc)

    retry_prompt = _json_retry_prompt(prompt, response.text if response.ok else response.error)
    retry = call_llm(retry_prompt)
    debug["retry_attempts"] = retry.attempts
    if retry.ok:
        try:
            resume = _load_resume_model(retry.text)
            quality_error = _resume_quality_error(resume)
            if not quality_error:
                save_cache("parsed_resumes", key, resume)
                return SuccessResult(data=resume, debug=debug)
            return ErrorResult(error=quality_error, debug=debug)
        except (ValueError, TypeError) as exc:
            debug["retry_parse_error"] = str(exc)
            return ErrorResult(error=f"Resume parsing returned malformed JSON: {exc}", debug=debug)

    return ErrorResult(error=retry.error or response.error or "Resume parsing failed.", debug=debug)


def parse_resume(file_path: str) -> SuccessResult[Resume] | ErrorResult:
    raw_text = extract_raw_text(file_path)
    if not raw_text:
        return ErrorResult(error="No text could be extracted from the resume file.")
    return raw_text_to_resume(raw_text)


def _json_retry_prompt(original_prompt: str, bad_response: str) -> str:
    return (
        f"{original_prompt}\n\n"
        "The previous response was not valid JSON. Return only corrected JSON with no markdown, no comments, and no explanatory text.\n\n"
        f"Previous response:\n{bad_response}"
    )


def _resume_quality_error(resume: Resume) -> str:
    if not resume.contact.name.strip():
        return "Parsed resume is missing a candidate name."
    has_content = bool(resume.experience or resume.projects or resume.skills.technical or resume.skills.tools)
    if not has_content:
        return "Parsed resume has no experience, projects, or skills."
    return ""
