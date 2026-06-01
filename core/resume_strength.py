import re
from typing import Any

from core.schema import Resume


ACTION_VERBS = {
    "analyzed",
    "automated",
    "built",
    "compared",
    "configured",
    "created",
    "debugged",
    "delivered",
    "deployed",
    "designed",
    "developed",
    "engineered",
    "evaluated",
    "implemented",
    "improved",
    "integrated",
    "migrated",
    "optimized",
    "ran",
    "reduced",
    "refactored",
    "streamlined",
    "tested",
    "trained",
    "wrote",
}
GENERIC_PHRASES = {
    "worked on",
    "helped with",
    "responsible for",
    "was responsible",
    "assisted in",
    "assisted with",
    "contributed to",
    "played a role",
    "was involved",
    "participated in",
    "passionate",
    "hardworking",
    "dynamic",
    "results-driven",
    "various tasks",
    "various",
    "in order to",
    "as part of",
    "spearheaded",
    "orchestrated",
    "leveraged",
    "utilized",
    "ensuring seamless",
    "driving key",
    "played a pivotal",
    "instrumental in",
}


def analyze_resume_strength(resume: Resume) -> dict[str, Any]:
    bullets = _bullets(resume)
    starts = [bullet.split()[0].lower().rstrip(".,:;") for bullet in bullets if bullet.split()]
    quantified = [bullet for bullet in bullets if re.search(r"\b\d+(?:\.\d+)?%?\b", bullet)]
    generic = [bullet for bullet in bullets if any(phrase in bullet.lower() for phrase in GENERIC_PHRASES)]
    technical_terms = _technical_terms(resume)

    score = 0
    if bullets:
        score += round((len(quantified) / len(bullets)) * 25)
        score += round((len(set(starts)) / len(starts)) * 25) if starts else 0
        score += round((sum(1 for start in starts if start in ACTION_VERBS) / len(starts)) * 20) if starts else 0
        score += round((sum(1 for bullet in bullets if 8 <= len(bullet.split()) <= 28) / len(bullets)) * 15)
    score += min(15, len(technical_terms))
    score -= min(25, len(generic) * 5)
    score = max(0, min(100, score))

    strengths = []
    weaknesses = []
    improvements = []

    if quantified:
        strengths.append("Contains quantified impact in some bullets.")
    else:
        weaknesses.append("No quantified bullets detected.")
        improvements.append("Add metrics only where the original evidence supports them.")

    if len(set(starts)) >= max(1, len(starts) - 1):
        strengths.append("Action verb openings are reasonably varied.")
    else:
        weaknesses.append("Repeated bullet openings detected.")
        improvements.append("Vary action verbs and sentence openings.")

    if technical_terms:
        strengths.append("Includes technical skills/tools.")
    else:
        weaknesses.append("Limited technical specificity detected.")
        improvements.append("Surface supported tools, languages, frameworks, and methods.")

    if generic:
        weaknesses.append("Generic wording detected.")
        improvements.append("Replace vague phrasing with specific actions and outcomes.")

    return {
        "score": score,
        "quantified_bullets": len(quantified),
        "action_verb_diversity": len(set(starts)),
        "average_bullet_length": _average_bullet_length(bullets),
        "ats_readability": _ats_readability(resume, bullets),
        "technical_specificity": len(technical_terms),
        "generic_wording_count": len(generic),
        "weak_bullet_count": len(generic) + sum(1 for bullet in bullets if len(bullet.split()) < 6),
        "strengths": strengths,
        "weaknesses": weaknesses,
        "improvement_areas": improvements,
    }


def compare_resume_strength(original: Resume, rewritten: Resume) -> dict[str, Any]:
    before = analyze_resume_strength(original)
    after = analyze_resume_strength(rewritten)
    return {
        "before": before,
        "after": after,
        "improvement_delta": after["score"] - before["score"],
    }


def _bullets(resume: Resume) -> list[str]:
    bullets = [bullet for item in resume.experience for bullet in item.bullets]
    bullets += [bullet for project in resume.projects for bullet in project.bullets]
    return bullets


def _technical_terms(resume: Resume) -> set[str]:
    values = (
        resume.skills.technical
        + resume.skills.tools
        + [tech for project in resume.projects for tech in project.technologies]
    )
    return {value.lower() for value in values if value}


def _average_bullet_length(bullets: list[str]) -> float:
    if not bullets:
        return 0.0
    return round(sum(len(bullet.split()) for bullet in bullets) / len(bullets), 2)


def _ats_readability(resume: Resume, bullets: list[str]) -> int:
    score = 0
    if resume.contact.name and resume.contact.email:
        score += 25
    if resume.skills.technical or resume.skills.tools:
        score += 25
    if resume.experience:
        score += 25
    if bullets and all(len(bullet.split()) <= 32 for bullet in bullets):
        score += 25
    return score
