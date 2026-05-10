import json
from pathlib import Path
from typing import Tuple

import gradio as gr
from pydantic import ValidationError

from core.analyzer import analyze_resume_match
from core.cover_letter import generate_cover_letter
from core.jd_analyzer import analyze_jd
from core.parser import parse_resume
from core.renderer import render_outputs
from core.rewrite import tailor_resume
from core.schema import Resume
from utils.bullet_optimizer import bullet_diff
from utils.file_utils import save_json


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"


def parse_resume_ui(file_path: str) -> Tuple[str, str, str]:
    if not file_path:
        return "", "Please upload a PDF or DOCX resume.", ""

    try:
        result = parse_resume(file_path)
        if not result.success:
            return "", f"Parse failed: {result.error}", _debug_json(result.debug)

        resume = result.data
        save_json(DATA_DIR / "base_resume.json", resume)
        return (
            json.dumps(resume.model_dump(), indent=2),
            "Resume parsed successfully. Review and edit the JSON before generating outputs.",
            _debug_json(result.debug),
        )
    except Exception as exc:
        return "", f"Could not parse resume: {exc}", ""


def generate_outputs_ui(
    resume_json_text: str,
    jd_text: str,
    mode: str,
    lock_education: bool,
    lock_projects: bool,
    lock_skills: bool,
    lock_experience: bool,
) -> Tuple[str, str, str, str, str, str, str]:
    if not resume_json_text.strip():
        return "", "", "", "", "", "Please parse or paste resume JSON first.", ""
    if not jd_text.strip():
        return "", "", resume_json_text, "", "", "Please paste a job description.", ""

    try:
        resume_data = json.loads(resume_json_text)
        resume = Resume.model_validate(resume_data)
        locked_sections = _locked_sections(lock_education, lock_projects, lock_skills, lock_experience)

        jd_result = analyze_jd(jd_text)
        if not jd_result.success:
            return "", "", resume_json_text, "", "", f"JD analysis failed: {jd_result.error}", _debug_json(jd_result.debug)
        job_description = jd_result.data

        rewrite_result = tailor_resume(resume, job_description, mode=mode, locked_sections=locked_sections)
        if not rewrite_result.success:
            return "", "", resume_json_text, "", "", f"Resume rewrite failed: {rewrite_result.error}", _debug_json(rewrite_result.debug)
        tailored_resume = rewrite_result.data

        cover_result = generate_cover_letter(tailored_resume, job_description)
        if not cover_result.success:
            return "", "", json.dumps(tailored_resume.model_dump(), indent=2), "", "", f"Cover letter failed: {cover_result.error}", _debug_json(cover_result.debug)
        cover_letter = cover_result.data

        match_analysis = analyze_resume_match(tailored_resume, job_description)
        diff = bullet_diff(resume, tailored_resume)

        save_json(DATA_DIR / "tailored_resume.json", tailored_resume)
        render_result = render_outputs(tailored_resume, cover_letter)
        if not render_result.success:
            return "", "", json.dumps(tailored_resume.model_dump(), indent=2), _format_diff(diff), _format_match_analysis(match_analysis.model_dump()), f"PDF rendering failed: {render_result.error}", _debug_json(render_result.debug)

        resume_pdf, cover_letter_pdf = render_result.data
        debug = {
            "jd": jd_result.debug,
            "rewrite": rewrite_result.debug,
            "cover_letter": cover_result.debug,
            "renderer": render_result.debug,
        }

        return (
            resume_pdf,
            cover_letter_pdf,
            json.dumps(tailored_resume.model_dump(), indent=2),
            _format_diff(diff),
            _format_match_analysis(match_analysis.model_dump()),
            "Tailored resume and cover letter generated.",
            _debug_json(debug),
        )
    except json.JSONDecodeError as exc:
        return "", "", resume_json_text, "", "", f"Resume JSON is invalid: {exc}", ""
    except ValidationError as exc:
        return "", "", resume_json_text, "", "", f"Resume JSON does not match the schema: {exc}", ""
    except RuntimeError as exc:
        return "", "", resume_json_text, "", "", f"Output generation failed: {exc}", ""
    except Exception as exc:
        return "", "", resume_json_text, "", "", f"Could not generate outputs: {exc}", ""


def _locked_sections(
    lock_education: bool,
    lock_projects: bool,
    lock_skills: bool,
    lock_experience: bool,
) -> list[str]:
    locked = []
    if lock_education:
        locked.append("education")
    if lock_projects:
        locked.append("projects")
    if lock_skills:
        locked.append("skills")
    if lock_experience:
        locked.append("experience")
    return locked


def _format_diff(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "No bullet changes."

    lines = ["| Section | Before | After |", "|---|---|---|"]
    for row in rows:
        lines.append(
            "| {section} | {before} | {after} |".format(
                section=_markdown_cell(row["section"]),
                before=_markdown_cell(row["before"]),
                after=_markdown_cell(row["after"]),
            )
        )
    return "\n".join(lines)


def _format_match_analysis(analysis: dict) -> str:
    return "\n".join(
        [
            f"**JD Match Score:** {analysis['match_score']}%",
            "",
            f"**Matched Skills:** {', '.join(analysis['matched_skills']) or 'None found'}",
            "",
            f"**Missing Skills:** {', '.join(analysis['missing_skills']) or 'None found'}",
            "",
            "**Strongest Alignment Areas:**",
            "\n".join(f"- {area}" for area in analysis["strongest_alignment_areas"]) or "- None found",
        ]
    )


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _debug_json(debug: dict) -> str:
    return json.dumps(debug or {}, indent=2)


def build_app() -> gr.Blocks:
    with gr.Blocks(title="JD-Align") as demo:
        gr.Markdown("# JD-Align")

        resume_file = gr.File(
            label="1. Upload Resume (PDF/DOCX)",
            file_types=[".pdf", ".docx"],
            type="filepath",
        )
        parse_button = gr.Button("2. Parse Resume")
        resume_json = gr.Code(
            label="3. Editable Structured Resume JSON",
            language="json",
            lines=18,
        )

        jd_text = gr.Textbox(
            label="4. Job Description",
            lines=10,
            placeholder="Paste the job description here.",
        )
        mode = gr.Dropdown(
            label="Resume Mode",
            choices=["Conservative", "Balanced", "Aggressive"],
            value="Balanced",
        )
        with gr.Row():
            lock_education = gr.Checkbox(label="Lock education")
            lock_projects = gr.Checkbox(label="Lock projects")
            lock_skills = gr.Checkbox(label="Lock skills")
            lock_experience = gr.Checkbox(label="Lock experience")

        generate_button = gr.Button("5. Generate Outputs")

        tailored_resume_json = gr.Code(
            label="Tailored Resume JSON",
            language="json",
            lines=18,
        )
        match_analysis = gr.Markdown(label="Resume Match Analysis")
        bullet_changes = gr.Markdown(label="Before/After Bullet Diff")
        resume_pdf = gr.File(label="6. Download Tailored Resume PDF")
        cover_letter_pdf = gr.File(label="Download Cover Letter PDF")
        status = gr.Textbox(label="Status", interactive=False)
        with gr.Accordion("Debug details", open=False):
            debug_details = gr.Code(label="Pipeline Debug", language="json", lines=10)

        parse_button.click(
            fn=parse_resume_ui,
            inputs=resume_file,
            outputs=[resume_json, status, debug_details],
        )
        generate_button.click(
            fn=generate_outputs_ui,
            inputs=[
                resume_json,
                jd_text,
                mode,
                lock_education,
                lock_projects,
                lock_skills,
                lock_experience,
            ],
            outputs=[
                resume_pdf,
                cover_letter_pdf,
                tailored_resume_json,
                bullet_changes,
                match_analysis,
                status,
                debug_details,
            ],
        )

    return demo


if __name__ == "__main__":
    app = build_app()
    app.launch()
