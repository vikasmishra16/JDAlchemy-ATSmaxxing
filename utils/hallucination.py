import json
import re
from typing import Any

from core.schema import Resume


PUBLICATION_TERMS = {"publication", "published", "paper", "journal", "conference", "patent"}


def detect_hallucination_risks(original: Resume, rewritten: Resume) -> dict[str, Any]:
    original_text = json.dumps(original.model_dump()).lower()
    rewritten_text = json.dumps(rewritten.model_dump()).lower()

    added_tools = sorted(_skill_like_terms(rewritten) - _skill_like_terms(original))
    invented_metrics = sorted(
        number for number in set(re.findall(r"\b\d+(?:\.\d+)?%?\b", rewritten_text)) if number not in original_text
    )
    invented_companies = sorted(_companies(rewritten) - _companies(original))
    invented_projects = sorted(_projects(rewritten) - _projects(original))
    invented_publications = sorted(term for term in PUBLICATION_TERMS if term in rewritten_text and term not in original_text)

    risk_count = (
        len(added_tools)
        + len(invented_metrics)
        + len(invented_companies)
        + len(invented_projects)
        + len(invented_publications)
    )
    return {
        "tools_not_present_in_original": added_tools,
        "invented_metrics": invented_metrics,
        "invented_companies": invented_companies,
        "invented_projects": invented_projects,
        "invented_publication_indicators": invented_publications,
        "risk_count": risk_count,
        "risk_score": max(0, 100 - risk_count * 15),
    }


def _skill_like_terms(resume: Resume) -> set[str]:
    values = (
        resume.skills.technical
        + resume.skills.tools
        + resume.skills.languages
        + [tech for project in resume.projects for tech in project.technologies]
    )
    return {value.lower() for value in values if value}


def _companies(resume: Resume) -> set[str]:
    return {item.company.lower() for item in resume.experience if item.company}


def _projects(resume: Resume) -> set[str]:
    return {project.name.lower() for project in resume.projects if project.name}
