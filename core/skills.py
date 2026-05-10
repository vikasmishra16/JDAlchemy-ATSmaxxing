from core.schema import JobDescription, Resume


def reorder_skills_by_relevance(resume: Resume, job_description: JobDescription) -> Resume:
    reordered = resume.model_copy(deep=True)
    terms = _jd_terms(job_description)

    reordered.skills.technical = _reorder(reordered.skills.technical, terms)
    reordered.skills.tools = _reorder(reordered.skills.tools, terms)
    reordered.skills.languages = _reorder(reordered.skills.languages, terms)
    reordered.skills.soft_skills = _reorder(reordered.skills.soft_skills, terms)
    return reordered


def _jd_terms(job_description: JobDescription) -> set[str]:
    values = (
        job_description.required_skills
        + job_description.preferred_skills
        + job_description.keywords
        + job_description.responsibilities
    )
    return {value.lower() for value in values if value}


def _reorder(skills: list[str], terms: set[str]) -> list[str]:
    indexed = list(enumerate(skills))
    indexed.sort(key=lambda item: (-_score(item[1], terms), item[0]))
    return [skill for _, skill in indexed]


def _score(skill: str, terms: set[str]) -> int:
    skill_text = skill.lower()
    score = 0
    for term in terms:
        if skill_text == term:
            score += 3
        elif skill_text in term or term in skill_text:
            score += 1
    return score
