from collections.abc import Iterable

from core.schema import Resume


def optimize_bullet_text(bullet: str) -> str:
    text = " ".join(bullet.split()).strip()
    if not text:
        return ""

    if text and not text[0].isupper():
        text = text[0].upper() + text[1:]

    return _trim_sentence(text)


def optimize_resume_bullets(resume: Resume, locked_sections: Iterable[str] | None = None) -> Resume:
    locked = set(locked_sections or [])
    optimized = resume.model_copy(deep=True)

    if "experience" not in locked:
        for experience in optimized.experience:
            experience.bullets = [optimize_bullet_text(bullet) for bullet in experience.bullets if bullet.strip()]

    if "projects" not in locked:
        for project in optimized.projects:
            project.bullets = [optimize_bullet_text(bullet) for bullet in project.bullets if bullet.strip()]

    return optimized


def bullet_diff(original: Resume, rewritten: Resume) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    _collect_section_diff(rows, "Experience", _experience_bullets(original), _experience_bullets(rewritten))
    _collect_section_diff(rows, "Projects", _project_bullets(original), _project_bullets(rewritten))
    return rows


def _trim_sentence(text: str) -> str:
    words = text.rstrip(".").split()
    if len(words) > 28:
        text = " ".join(words[:28])
    return text.rstrip(".") + "."


def _experience_bullets(resume: Resume) -> list[str]:
    return [bullet for item in resume.experience for bullet in item.bullets]


def _project_bullets(resume: Resume) -> list[str]:
    return [bullet for item in resume.projects for bullet in item.bullets]


def _collect_section_diff(rows: list[dict[str, str]], section: str, before: list[str], after: list[str]) -> None:
    max_len = max(len(before), len(after))
    for index in range(max_len):
        old = before[index] if index < len(before) else ""
        new = after[index] if index < len(after) else ""
        if old != new:
            rows.append({"section": section, "before": old, "after": new})
