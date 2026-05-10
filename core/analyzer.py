from pydantic import BaseModel, Field

from core.schema import JobDescription, Resume


class ResumeMatchAnalysis(BaseModel):
    match_score: int = 0
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    strongest_alignment_areas: list[str] = Field(default_factory=list)


def analyze_resume_match(resume: Resume, job_description: JobDescription) -> ResumeMatchAnalysis:
    resume_skills = _resume_skills(resume)
    jd_skills = _jd_skills(job_description)

    matched = sorted(skill for skill in jd_skills if _contains_skill(skill, resume_skills))
    missing = sorted(skill for skill in jd_skills if skill not in matched)
    score = round((len(matched) / len(jd_skills)) * 100) if jd_skills else 0

    alignment = _alignment_areas(resume, job_description, matched)
    return ResumeMatchAnalysis(
        match_score=score,
        matched_skills=matched,
        missing_skills=missing,
        strongest_alignment_areas=alignment,
    )


def _resume_skills(resume: Resume) -> set[str]:
    values = (
        resume.skills.technical
        + resume.skills.tools
        + resume.skills.languages
        + resume.skills.soft_skills
    )
    return {value.lower() for value in values if value}


def _jd_skills(job_description: JobDescription) -> set[str]:
    values = job_description.required_skills + job_description.preferred_skills + job_description.keywords
    return {value.lower() for value in values if value}


def _contains_skill(skill: str, resume_skills: set[str]) -> bool:
    return any(skill == existing or skill in existing or existing in skill for existing in resume_skills)


def _alignment_areas(resume: Resume, job_description: JobDescription, matched: list[str]) -> list[str]:
    areas = []
    if matched:
        areas.append(f"Skill alignment: {', '.join(matched[:8])}")
    if resume.experience and job_description.responsibilities:
        areas.append("Experience section can be aligned to the role responsibilities.")
    if resume.projects and (job_description.required_skills or job_description.preferred_skills):
        areas.append("Projects can reinforce relevant technical evidence.")
    return areas
