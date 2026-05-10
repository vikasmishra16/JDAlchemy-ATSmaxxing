import argparse
import json
import re
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import config
from core.analyzer import analyze_resume_match
from core.cover_letter import generate_cover_letter
from core.jd_analyzer import analyze_jd
from core.llm_engine import set_debug_output_dir
from core.parser import parse_resume
from core.renderer import render_outputs
from core.resume_strength import compare_resume_strength
from core.rewrite import tailor_resume
from core.schema import Resume
from utils.diff_utils import generate_bullet_diff
from utils.hallucination import detect_hallucination_risks
from utils.prompt_loader import load_prompt


PROJECT_ROOT = Path(__file__).resolve().parent
TEST_DATA_DIR = PROJECT_ROOT / "test_data"
RESUME_DIR = TEST_DATA_DIR / "resumes"
JD_DIR = TEST_DATA_DIR / "jds"
OUTPUT_DIR = TEST_DATA_DIR / "outputs"


def main() -> None:
    parser = argparse.ArgumentParser(description="JD-Align Evaluation")
    parser.add_argument(
        "--fast", action="store_true", help="Fast mode: skip expensive operations"
    )
    parser.add_argument(
        "--force", action="store_true", help="Force re-evaluation, skip cache"
    )
    args = parser.parse_args()

    resume_files = _input_files(RESUME_DIR, {".json", ".pdf", ".docx"})
    jd_files = _input_files(JD_DIR, {".txt"})
    prompt_versions = _prompt_versions()
    model_candidates = config.MODEL_CANDIDATES

    if not resume_files:
        print(f"No resumes found in {RESUME_DIR}")
        return
    if not jd_files:
        print(f"No JDs found in {JD_DIR}")
        return

    rows: list[dict[str, Any]] = []
    totals = defaultdict(int)

    # Initialize caches
    parsed_resume_cache: Dict[str, dict] = {}
    jd_analysis_cache: Dict[str, Any] = {}
    last_prompt_version: str = ""

    start_time = time.time()

    # Reordered loops: resume → JD → model → prompt for better cache reuse
    for resume_file in resume_files:
        # Parse resume once (or load from cache)
        resume_cache_key = _get_resume_cache_key(resume_file)
        if not args.force and resume_cache_key in parsed_resume_cache:
            parsed_result = parsed_resume_cache[resume_cache_key]
            cache_hit = True
        else:
            parsed_result = _load_or_parse_resume(resume_file)
            parsed_resume_cache[resume_cache_key] = parsed_result
            cache_hit = False

        totals["parse_attempts"] += 1
        if not parsed_result["success"]:
            totals["parse_failures"] += 1
            # Still need to record failures for all model/prompt combinations
            for model in model_candidates:
                config.OLLAMA_MODEL = model
                for prompt_version in prompt_versions:
                    config.PROMPT_VERSION = prompt_version
                    # Clear prompt cache only when version actually changes
                    if prompt_version != last_prompt_version:
                        load_prompt.cache_clear()
                        last_prompt_version = prompt_version
                    _write_parse_failure(
                        resume_file, model, prompt_version, parsed_result
                    )
            continue

        original_resume = parsed_result["original_resume"]
        parsed_resume = parsed_result["parsed_resume"]
        candidate_name = _candidate_name(parsed_resume, resume_file)

        for jd_file in jd_files:
            # Analyze JD once (or load from cache)
            jd_cache_key = _get_jd_cache_key(jd_file)
            if not args.force and jd_cache_key in jd_analysis_cache:
                jd_result = jd_analysis_cache[jd_cache_key]
                jd_cache_hit = True
            else:
                jd_result = analyze_jd(jd_file.read_text(encoding="utf-8"))
                jd_analysis_cache[jd_cache_key] = jd_result
                jd_cache_hit = False

            totals["jd_analysis_attempts"] += 1
            if not jd_result.success:
                totals["jd_failures"] += 1
                # Still need to record failures for all model/prompt combinations
                for model in model_candidates:
                    config.OLLAMA_MODEL = model
                    for prompt_version in prompt_versions:
                        config.PROMPT_VERSION = prompt_version
                        # Clear prompt cache only when version actually changes
                        if prompt_version != last_prompt_version:
                            load_prompt.cache_clear()
                            last_prompt_version = prompt_version
                    _failure_row(
                        OUTPUT_DIR
                        / _slug(resume_file.stem)
                        / _slug(jd_file.stem)
                        / f"{model}_{prompt_version}",
                        resume_file,
                        jd_file,
                        model,
                        prompt_version,
                        "jd_analysis",
                        jd_result.error,
                        parse_time=0.0,
                        jd_analysis_time=0.0,
                        rewrite_time=0.0,
                        total_time=0.0,
                    )
                continue

            job_description = jd_result.data

            for model in model_candidates:
                config.OLLAMA_MODEL = model
                for prompt_version in prompt_versions:
                    config.PROMPT_VERSION = prompt_version
                    # Clear prompt cache only when version actually changes
                    if prompt_version != last_prompt_version:
                        load_prompt.cache_clear()
                        last_prompt_version = prompt_version

                    jd_slug = _slug(jd_file.stem)
                    case_dir = (
                        OUTPUT_DIR
                        / candidate_name
                        / jd_slug
                        / f"{model}_{prompt_version}"
                    )

                    # Check for incremental evaluation - skip if already done and inputs unchanged
                    metrics_path = case_dir / "metrics.json"
                    if not args.force and metrics_path.exists():
                        # TODO: Add proper cache validation based on input hashes
                        # For now, we'll just check if the file exists
                        pass  # In a full implementation, we'd validate cache here

                    raw_dir = case_dir / "raw_llm_outputs"
                    case_dir.mkdir(parents=True, exist_ok=True)
                    raw_dir.mkdir(parents=True, exist_ok=True)
                    set_debug_output_dir(raw_dir)

                    try:
                        row = _run_case(
                            case_dir=case_dir,
                            resume_file=resume_file,
                            jd_file=jd_file,
                            original_resume=original_resume,
                            parsed_resume=parsed_resume,
                            job_description=job_description,
                            model=model,
                            prompt_version=prompt_version,
                            totals=totals,
                            fast=args.fast,
                        )
                        rows.append(row)
                    finally:
                        set_debug_output_dir(None)

    _print_summary(rows, totals)


def _run_case(
    case_dir: Path,
    resume_file: Path,
    jd_file: Path,
    original_resume: Resume,
    parsed_resume: Resume,
    job_description: Any,
    model: str,
    prompt_version: str,
    totals: dict[str, int],
    fast: bool = False,
) -> dict[str, Any]:
    # Track timing
    case_start_time = time.time()
    parse_time = 0.0
    jd_analysis_time = 0.0
    rewrite_time = 0.0
    total_time = 0.0

    jd_text = jd_file.read_text(encoding="utf-8")
    shutil.copy2(jd_file, case_dir / "source_jd.txt")
    _write_json(case_dir / "original_resume.json", original_resume.model_dump())
    _write_json(case_dir / "parsed_resume.json", parsed_resume.model_dump())

    # JD Analysis (always needed for context)
    jd_start = time.time()
    jd_result = analyze_jd(jd_text)
    jd_analysis_time = time.time() - jd_start
    _count_retries(totals, jd_result.debug)
    _count_malformed_json(totals, jd_result.debug, jd_result.error)
    if not jd_result.success:
        totals["jd_failures"] += 1
        return _failure_row(
            case_dir,
            resume_file,
            jd_file,
            model,
            prompt_version,
            "jd_analysis",
            jd_result.error,
            parse_time=parse_time,
            jd_analysis_time=jd_analysis_time,
            rewrite_time=rewrite_time,
            total_time=time.time() - case_start_time,
        )

    job_description = jd_result.data
    _write_json(case_dir / "jd_analysis.json", job_description.model_dump())

    # Resume Rewrite
    rewrite_start = time.time()
    rewrite_result = tailor_resume(parsed_resume, job_description, mode="Balanced")
    rewrite_time = time.time() - rewrite_start
    _count_retries(totals, rewrite_result.debug)
    _count_malformed_json(totals, rewrite_result.debug, rewrite_result.error)
    if not rewrite_result.success:
        totals["rewrite_failures"] += 1
        return _failure_row(
            case_dir,
            resume_file,
            jd_file,
            model,
            prompt_version,
            "rewrite",
            rewrite_result.error,
            parse_time=parse_time,
            jd_analysis_time=jd_analysis_time,
            rewrite_time=rewrite_time,
            total_time=time.time() - case_start_time,
        )

    tailored_resume = rewrite_result.data
    _write_json(case_dir / "tailored_resume.json", tailored_resume.model_dump())

    # Fast mode: skip expensive operations
    if fast:
        cover_letter = ""
        match_analysis = None
        strength = None
        hallucination = None
        latex_success = False
        resume_pdf = None
        cover_letter_pdf = None

        # Still create basic files for consistency
        (case_dir / "cover_letter.txt").write_text("", encoding="utf-8")
        diff_text = generate_bullet_diff(parsed_resume, tailored_resume)
        (case_dir / "rewrite_diff.txt").write_text(diff_text, encoding="utf-8")
    else:
        # Cover Letter Generation
        cover_result = generate_cover_letter(tailored_resume, job_description)
        _count_retries(totals, cover_result.debug)
        if not cover_result.success:
            totals["cover_letter_failures"] += 1
            return _failure_row(
                case_dir,
                resume_file,
                jd_file,
                model,
                prompt_version,
                "cover_letter",
                cover_result.error,
                parse_time=parse_time,
                jd_analysis_time=jd_analysis_time,
                rewrite_time=rewrite_time,
                total_time=time.time() - case_start_time,
            )

        cover_letter = cover_result.data
        (case_dir / "cover_letter.txt").write_text(cover_letter, encoding="utf-8")
        diff_text = generate_bullet_diff(parsed_resume, tailored_resume)
        (case_dir / "rewrite_diff.txt").write_text(diff_text, encoding="utf-8")

        # Analysis (skipped in fast mode)
        match_analysis = analyze_resume_match(tailored_resume, job_description)
        strength = compare_resume_strength(parsed_resume, tailored_resume)
        hallucination = detect_hallucination_risks(parsed_resume, tailored_resume)

        # Render Outputs (skipped in fast mode)
        render_result = render_outputs(tailored_resume, cover_letter)
        latex_success = render_result.success
        if not render_result.success:
            totals["latex_failures"] += 1
            (case_dir / "render_error.txt").write_text(
                render_result.error, encoding="utf-8"
            )
        else:
            resume_pdf, cover_letter_pdf = render_result.data
            shutil.copy2(resume_pdf, case_dir / "resume.pdf")
            shutil.copy2(cover_letter_pdf, case_dir / "cover_letter.pdf")

    if not fast:
        if (
            not cover_letter.strip()
            or not tailored_resume.experience
            and not tailored_resume.projects
        ):
            totals["empty_outputs"] += 1

        metrics = _case_metrics(
            model=model,
            prompt_version=prompt_version,
            jd_file=jd_file,
            match_analysis=match_analysis.model_dump() if match_analysis else {},
            strength=strength if strength else {},
            hallucination=hallucination if hallucination else {},
            tailored_resume=tailored_resume,
            latex_success=latex_success,
        )
        _write_json(case_dir / "metrics.json", metrics)

        totals["successful_cases"] += 1
        totals["latex_attempts"] += 1
        if latex_success:
            totals["latex_successes"] += 1
    else:
        # Fast mode metrics
        metrics = {
            "model": model,
            "prompt_version": prompt_version,
            "jd": jd_file.stem,
            "keyword_alignment_percent": 0,  # Placeholder
            "missing_jd_skills": [],
            "repeated_verbs": 0,
            "average_bullet_length": 0.0,
            "weak_bullet_count": 0,
            "generic_phrase_count": 0,
            "hallucination_indicators": {},
            "hallucination_risk_score": 0,
            "original_resume_strength": 0,
            "rewritten_resume_strength": 0,
            "resume_improvement_delta": 0,
            "latex_success": False,
            "composite_score": 0.0,
        }
        _write_json(case_dir / "metrics.json", metrics)

        totals["successful_cases"] += 1
        # Don't count LaTeX in fast mode

    total_time = time.time() - case_start_time

    return {
        "candidate": _candidate_name(parsed_resume, resume_file),
        "jd": jd_file.stem,
        "model": model,
        "prompt_version": prompt_version,
        "success": True,
        "parse_time": parse_time,
        "jd_analysis_time": jd_analysis_time,
        "rewrite_time": rewrite_time,
        "total_time": total_time,
        **metrics,
    }


def _case_metrics(
    model: str,
    prompt_version: str,
    jd_file: Path,
    match_analysis: Optional[dict[str, Any]],
    strength: Optional[dict[str, Any]],
    hallucination: Optional[dict[str, Any]],
    tailored_resume: Resume,
    latex_success: bool,
) -> dict[str, Any]:
    bullets = _bullets(tailored_resume)
    starts = [
        bullet.split()[0].lower().rstrip(".,:;") for bullet in bullets if bullet.split()
    ]
    repeated_verbs = sum(
        1 for index in range(1, len(starts)) if starts[index] == starts[index - 1]
    )

    # Handle None values in fast mode
    keyword_alignment = match_analysis["match_score"] if match_analysis else 0
    missing_jd_skills = match_analysis["missing_skills"] if match_analysis else []
    weak_bullet_count = (
        strength["after"]["weak_bullet_count"]
        if strength and "after" in strength
        else 0
    )
    generic_phrase_count = (
        strength["after"]["generic_wording_count"]
        if strength and "after" in strength
        else 0
    )
    hallucination_indicators = hallucination if hallucination else {}
    hallucination_risk_score = (
        hallucination["risk_score"]
        if hallucination and "risk_score" in hallucination
        else 0
    )
    original_resume_strength = (
        strength["before"]["score"] if strength and "before" in strength else 0
    )
    rewritten_resume_strength = (
        strength["after"]["score"] if strength and "after" in strength else 0
    )
    resume_improvement_delta = (
        strength["improvement_delta"]
        if strength and "improvement_delta" in strength
        else 0
    )

    return {
        "model": model,
        "prompt_version": prompt_version,
        "jd": jd_file.stem,
        "keyword_alignment_percent": keyword_alignment,
        "missing_jd_skills": missing_jd_skills,
        "repeated_verbs": repeated_verbs,
        "average_bullet_length": _average_bullet_length(bullets),
        "weak_bullet_count": weak_bullet_count,
        "generic_phrase_count": generic_phrase_count,
        "hallucination_indicators": hallucination_indicators,
        "hallucination_risk_score": hallucination_risk_score,
        "original_resume_strength": original_resume_strength,
        "rewritten_resume_strength": rewritten_resume_strength,
        "resume_improvement_delta": resume_improvement_delta,
        "latex_success": latex_success,
        "composite_score": _composite_score(
            keyword_alignment,
            hallucination_risk_score,
            resume_improvement_delta,
        ),
    }


def _load_or_parse_resume(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        resume = Resume.model_validate(json.loads(path.read_text(encoding="utf-8")))
        return {
            "success": True,
            "original_resume": resume,
            "parsed_resume": resume,
            "debug": {},
        }

    result = parse_resume(str(path))
    if not result.success:
        return {"success": False, "error": result.error, "debug": result.debug}
    return {
        "success": True,
        "original_resume": result.data,
        "parsed_resume": result.data,
        "debug": result.debug,
    }


def _write_parse_failure(
    resume_file: Path, model: str, prompt_version: str, parsed_result: dict[str, Any]
) -> None:
    case_dir = (
        OUTPUT_DIR
        / _slug(resume_file.stem)
        / "_parse_failure"
        / f"{model}_{prompt_version}"
    )
    case_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        case_dir / "metrics.json",
        {
            "model": model,
            "prompt_version": prompt_version,
            "success": False,
            "stage": "parse",
            "error": parsed_result.get("error", "Unknown parse failure."),
            "debug": parsed_result.get("debug", {}),
        },
    )


def _failure_row(
    case_dir: Path,
    resume_file: Path,
    jd_file: Path,
    model: str,
    prompt_version: str,
    stage: str,
    error: str,
    parse_time: float = 0.0,
    jd_analysis_time: float = 0.0,
    rewrite_time: float = 0.0,
    total_time: float = 0.0,
) -> dict[str, Any]:
    metrics = {
        "model": model,
        "prompt_version": prompt_version,
        "jd": jd_file.stem,
        "success": False,
        "stage": stage,
        "error": error,
        "keyword_alignment_percent": 0,
        "hallucination_risk_score": 0,
        "resume_improvement_delta": 0,
        "latex_success": False,
        "composite_score": 0.0,
        "parse_time": parse_time,
        "jd_analysis_time": jd_analysis_time,
        "rewrite_time": rewrite_time,
        "total_time": total_time,
    }
    _write_json(case_dir / "metrics.json", metrics)
    (case_dir / "failure.txt").write_text(f"{stage} failed: {error}", encoding="utf-8")
    return {
        "candidate": _slug(resume_file.stem),
        "jd": jd_file.stem,
        "model": model,
        "prompt_version": prompt_version,
        **metrics,
    }


def _input_files(folder: Path, suffixes: set[str]) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    return sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in suffixes
    )


def _prompt_versions() -> list[str]:
    versions = sorted(
        path.name
        for path in (PROJECT_ROOT / "prompts").iterdir()
        if path.is_dir() and path.name.startswith("v")
    )
    return versions or [config.PROMPT_VERSION]


def _candidate_name(resume: Resume, path: Path) -> str:
    return _slug(resume.contact.name.strip() or path.stem)


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_").lower() or "item"


def _get_resume_cache_key(resume_file: Path) -> str:
    """Generate cache key for parsed resume."""
    from utils.hash_utils import file_hash

    return (
        f"{file_hash(str(resume_file))}_{config.PROMPT_VERSION}_{config.OLLAMA_MODEL}"
    )


def _get_jd_cache_key(jd_file: Path) -> str:
    """Generate cache key for JD analysis."""
    from utils.hash_utils import file_hash

    return f"{file_hash(str(jd_file))}_{config.PROMPT_VERSION}_{config.OLLAMA_MODEL}"


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _bullets(resume: Resume) -> list[str]:
    bullets = [bullet for item in resume.experience for bullet in item.bullets]
    bullets += [bullet for project in resume.projects for bullet in project.bullets]
    return bullets


def _average_bullet_length(bullets: list[str]) -> float:
    if not bullets:
        return 0.0
    return round(sum(len(bullet.split()) for bullet in bullets) / len(bullets), 2)


def _composite_score(
    keyword_alignment: int, hallucination_risk: int, improvement_delta: int
) -> float:
    normalized_delta = max(0, min(100, 50 + improvement_delta))
    return round(
        (keyword_alignment * 0.4)
        + (hallucination_risk * 0.35)
        + (normalized_delta * 0.25),
        2,
    )


def _count_retries(totals: dict[str, int], debug: dict[str, Any]) -> None:
    retry_attempts = int(debug.get("retry_attempts", 0) or 0)
    if retry_attempts:
        totals["retries_used"] += retry_attempts


def _count_malformed_json(
    totals: dict[str, int], debug: dict[str, Any], error: str = ""
) -> None:
    if (
        debug.get("primary_parse_error")
        or debug.get("retry_parse_error")
        or "json" in error.lower()
    ):
        totals["malformed_json_failures"] += 1


def _print_summary(rows: list[dict[str, Any]], totals: dict[str, int]) -> None:
    if not rows:
        print("No evaluation rows generated.")
        return

    successful = [row for row in rows if row.get("success")]
    parse_success_rate = _percent(
        totals["parse_attempts"] - totals["parse_failures"], totals["parse_attempts"]
    )
    latex_success_rate = _percent(totals["latex_successes"], totals["latex_attempts"])
    avg_hallucination = _avg(row["hallucination_risk_score"] for row in successful)
    avg_alignment = _avg(row["keyword_alignment_percent"] for row in successful)
    avg_improvement = _avg(row["resume_improvement_delta"] for row in successful)
    best_model = _best_group(successful, "model")
    best_prompt = _best_group(successful, "prompt_version")

    print("\nJD-Align Empirical Evaluation")
    print("-" * 118)
    print(
        f"{'Candidate':20} {'JD':18} {'Model':10} {'Prompt':8} {'Align':>7} {'Truth':>7} {'Delta':>7} {'Score':>7}"
    )
    print("-" * 118)
    for row in rows:
        print(
            f"{row['candidate'][:20]:20} "
            f"{row['jd'][:18]:18} "
            f"{row['model'][:10]:10} "
            f"{row['prompt_version'][:8]:8} "
            f"{row.get('keyword_alignment_percent', 0):>7} "
            f"{row.get('hallucination_risk_score', 0):>7} "
            f"{row.get('resume_improvement_delta', 0):>7} "
            f"{row.get('composite_score', 0):>7}"
        )

    print("-" * 118)
    print(f"Best performing model: {best_model}")
    print(f"Best prompt version: {best_prompt}")
    print(f"Parse success rate: {parse_success_rate}%")
    print(f"LaTeX success rate: {latex_success_rate}%")
    print(f"Average hallucination risk score: {avg_hallucination}")
    print(f"Average keyword alignment: {avg_alignment}")
    print(f"Average resume improvement score: {avg_improvement}")
    print("\nFailure Metrics")
    print("-" * 118)
    for key in [
        "parse_failures",
        "jd_failures",
        "rewrite_failures",
        "cover_letter_failures",
        "latex_failures",
        "empty_outputs",
        "malformed_json_failures",
        "retries_used",
    ]:
        print(f"{key:28} {totals[key]}")
    print(f"\nOutputs saved to: {OUTPUT_DIR}")


def _best_group(rows: list[dict[str, Any]], field: str) -> str:
    if not rows:
        return "n/a"
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[str(row[field])].append(float(row["composite_score"]))
    best = max(grouped.items(), key=lambda item: sum(item[1]) / len(item[1]))
    return f"{best[0]} ({round(sum(best[1]) / len(best[1]), 2)})"


def _avg(values) -> float:
    values = list(values)
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _percent(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


if __name__ == "__main__":
    main()
