import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import DEBUG
from core.result import ErrorResult, SuccessResult
from core.schema import Resume
from utils.latex_utils import latex_escape
from utils.privacy import redact_sensitive_text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = PROJECT_ROOT / "templates"
OUTPUT_DIR = PROJECT_ROOT / "output"
RUNS_DIR = OUTPUT_DIR / "runs"


def _template_environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(disabled_extensions=("tex",)),
        block_start_string="<%",
        block_end_string="%>",
        variable_start_string="<<",
        variable_end_string=">>",
        comment_start_string="<#",
        comment_end_string="#>",
    )
    env.filters["latex_escape"] = latex_escape
    return env


def render_template(template_name: str, context: Dict[str, Any], output_tex: Path) -> Path:
    env = _template_environment()
    template = env.get_template(template_name)
    output_tex.parent.mkdir(parents=True, exist_ok=True)
    output_tex.write_text(template.render(**context), encoding="utf-8")
    return output_tex


def compile_pdf(tex_path: Path, output_pdf: Path) -> Path:
    if shutil.which("pdflatex") is None:
        _save_failed_latex_debug(tex_path, "", "pdflatex is not installed or not available on PATH.")
        raise RuntimeError("pdflatex is not installed or not available on PATH.")

    command = [
        "pdflatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        tex_path.name,
    ]

    result = subprocess.run(
        command,
        cwd=tex_path.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    latex_log_path = tex_path.with_suffix(".log")
    latex_log_path.write_text(
        "STDOUT:\n"
        + result.stdout
        + "\n\nSTDERR:\n"
        + result.stderr,
        encoding="utf-8",
    )

    if result.returncode != 0:
        _save_failed_latex_debug(tex_path, result.stdout, result.stderr)
        message = _readable_latex_error(result.stdout, result.stderr)
        raise RuntimeError(
            f"Failed to compile {tex_path.name}. "
            f"Temp file saved at {tex_path}. Log saved at {latex_log_path}.\n{message}"
        )

    compiled_pdf = tex_path.with_suffix(".pdf")
    if not compiled_pdf.exists():
        raise RuntimeError(
            f"Expected PDF was not created: {compiled_pdf}. "
            f"Temp file saved at {tex_path}. Log saved at {latex_log_path}."
        )

    if output_pdf.exists():
        output_pdf.unlink()
    compiled_pdf.replace(output_pdf)
    return output_pdf


def render_resume_pdf(resume: Resume) -> str:
    run_dir = _new_run_dir()
    tex_path = run_dir / "resume.tex"
    output_pdf = run_dir / "resume.pdf"
    render_template("resume.tex", {"resume": resume}, tex_path)
    return str(compile_pdf(tex_path, output_pdf))


def render_cover_letter_pdf(cover_letter_text: str, run_dir: Path | None = None) -> str:
    target_dir = run_dir or _new_run_dir()
    tex_path = target_dir / "cover_letter.tex"
    output_pdf = target_dir / "cover_letter.pdf"
    render_template("cover_letter.tex", {"cover_letter": cover_letter_text}, tex_path)
    return str(compile_pdf(tex_path, output_pdf))


def render_outputs(resume: Resume, cover_letter_text: str) -> SuccessResult[tuple[str, str]] | ErrorResult:
    run_dir = _new_run_dir()
    try:
        resume_tex = run_dir / "resume.tex"
        cover_letter_tex = run_dir / "cover_letter.tex"
        resume_pdf = run_dir / "resume.pdf"
        cover_letter_pdf = run_dir / "cover_letter.pdf"

        render_template("resume.tex", {"resume": resume}, resume_tex)
        compile_pdf(resume_tex, resume_pdf)
        render_template("cover_letter.tex", {"cover_letter": cover_letter_text}, cover_letter_tex)
        compile_pdf(cover_letter_tex, cover_letter_pdf)

        return SuccessResult(
            data=(str(resume_pdf), str(cover_letter_pdf)),
            debug={"run_dir": str(run_dir)},
        )
    except RuntimeError as exc:
        return ErrorResult(error=str(exc), debug={"run_dir": str(run_dir)})


def _readable_latex_error(stdout: str, stderr: str) -> str:
    combined = "\n".join(part for part in [stdout, stderr] if part)
    if not combined.strip():
        return "pdflatex failed without producing output."

    lines = combined.splitlines()
    important = [line for line in lines if line.startswith("!") or "Error" in line or "LaTeX" in line]
    if important:
        return "\n".join(important[-12:])
    return "\n".join(lines[-25:])


def _save_failed_latex_debug(tex_path: Path, stdout: str, stderr: str) -> None:
    if not DEBUG:
        return

    debug_dir = PROJECT_ROOT / "debug" / "failed_latex"
    debug_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    base = debug_dir / timestamp
    base.with_suffix(".tex").write_text(
        redact_sensitive_text(tex_path.read_text(encoding="utf-8", errors="ignore")),
        encoding="utf-8",
    )
    base.with_suffix(".log").write_text(
        redact_sensitive_text("STDOUT:\n" + stdout + "\n\nSTDERR:\n" + stderr),
        encoding="utf-8",
    )


def _new_run_dir() -> Path:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + uuid4().hex[:8]
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir
