OLLAMA_MODEL = "mistral:latest"
OLLAMA_URL = "http://localhost:11434/api/generate"
REQUEST_TIMEOUT = 120
PROMPT_VERSION = "v3"
DEBUG = True
MODEL_CANDIDATES = ["mistral"]
OLLAMA_OPTIONS = {
    "num_ctx": 2048,
    "num_predict": 384,
    "temperature": 0.2,
}
