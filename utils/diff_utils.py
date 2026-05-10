from core.schema import Resume


def generate_bullet_diff(original: Resume, rewritten: Resume) -> str:
    sections = [
        ("EXPERIENCE", _experience_bullets(original), _experience_bullets(rewritten)),
        ("PROJECTS", _project_bullets(original), _project_bullets(rewritten)),
    ]
    parts = []
    for section, before, after in sections:
        section_diff = _section_diff(section, before, after)
        if section_diff:
            parts.append(section_diff)
    return "\n\n".join(parts) if parts else "No bullet changes detected."


def _section_diff(section: str, before: list[str], after: list[str]) -> str:
    rows = []
    max_len = max(len(before), len(after))
    for index in range(max_len):
        old = before[index] if index < len(before) else ""
        new = after[index] if index < len(after) else ""
        if old == new:
            continue
        rows.append(f"BEFORE:\n* {old or '[missing]'}\n\nAFTER:\n* {new or '[removed]'}")

    if not rows:
        return ""
    return f"{section}\n" + "\n\n---\n\n".join(rows)


def _experience_bullets(resume: Resume) -> list[str]:
    return [bullet for item in resume.experience for bullet in item.bullets]


def _project_bullets(resume: Resume) -> list[str]:
    return [bullet for item in resume.projects for bullet in item.bullets]
