# JDAlchemy ATS Resume Tailoring System

JDAlchemy is a local-first AI-powered resume tailoring tool designed to help users create stronger, ATS-friendly resumes tailored to specific job descriptions while preserving factual accuracy and minimizing hallucinations.

## Philosophy

**Local-first & Privacy-focused**: Everything runs locally or through OpenAI-compatible APIs. No data leaves your machine unless you explicitly choose to use external APIs.

**Accuracy over Keyword Stuffing**: Rewrites for impact and alignment, not blind keyword optimization. Preserves truthful resume content while improving relevance.

**Practical Engineering**: Modular, JSON-first pipeline with Pydantic validation, prompt versioning, caching, and evaluation harness - designed for real-world usage, not theoretical scalability.

## Supported Model Backends

- Local Ollama models (recommended: mistral, llama3, phi3)
- OpenAI-compatible APIs
- NVIDIA NIM models
- Configure via `config.py`

## Setup

```bash
# Clone repository
git clone https://github.com/vikasmishra16/JDAlchemy-ATSmaxxing.git
cd JDAlchemy-ATSmaxxing

# Create virtual environment
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix/MacOS: source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Ollama (for local models)
# https://ollama.com/download

# Pull configured model (default: mistral)
ollama pull mistral

# Install LaTeX (for PDF generation)
# MiKTeX (Windows) or TeX Live (Linux/Mac)
# Ensure pdflatex is in PATH
```

## Health Check

Run before first use:
```bash
python healthcheck.py
```
Checks Ollama, model availability, pdflatex, folders, and prompt files.

## Usage

### Web Interface (Recommended)
```bash
python app.py
```
Open the Gradio URL shown in terminal.

### Command Line Evaluation
```bash
# Standard evaluation
python evaluate.py

# Fast mode (skips expensive operations for rapid iteration)
python evaluate.py --fast

# Force re-evaluation (ignore cache)
python evaluate.py --force

# Combine options
python evaluate.py --fast --force
```

Fast mode skips: cover letters, hallucination analysis, strength analysis, LaTeX rendering - ideal for prompt/model iteration.

## Project Structure

```
jd-align/
├── evaluate.py          # CLI evaluation with optimizations
├── app.py               # Gradio web interface
├── config.py            # Configuration (models, prompts, etc.)
├── requirements.txt     # Dependencies
├── README.md            # This file
├── healthcheck.py       # System verification
├── core/                # Processing modules (parser, analyzer, rewrite, etc.)
├── utils/               # Helper functions (cache, prompts, hashing)
├── prompts/             # Prompt templates (v1, v2, ...)
├── templates/           # LaTeX templates
├── test_data/           # Sample inputs
│   ├── resumes/         # Test resume files (.json, .pdf, .docx)
│   └── jds/             # Test job descriptions (.txt)
├── output/              # Generated outputs (gitignored)
├── cache/               # Processing cache (gitignored)
└── debug/               # Debug logs (gitignored)
```

## Current Limitations

- Resume parsing quality depends on text extraction and LLM JSON fidelity
- Match scores are heuristic-based, not real ATS compatibility scores
- Anti-hallucination measures are prompt-driven with validation assistance
- Requires local LaTeX installation for PDF output generation
- Performance varies with hardware and selected model size
- Schema intentionally focused on common resume formats

## Roadmap

- [x] Core resume tailoring pipeline
- [x] Local-first architecture with caching
- [x] Evaluation harness with timing analysis
- [x] Fast iteration mode
- [ ] Enhanced PDF template customization
- [ ] Additional export formats (Word, HTML)
- [ ] Batch processing improvements
- [ ] Extended evaluation metrics

## Contributing

This is an open-source utility focused on practical, local resume optimization. Contributions aligned with the local-first, accuracy-focused philosophy are welcome.

## License

MIT License - see LICENSE file for details.
