import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base project paths
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploaded_pdfs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Google API Key
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# Prioritized list of Gemini models for automatic fallback
# Updated to current active Gemini models
MODEL_CANDIDATES = [
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-2.5-flash-lite",
    "gemini-pro-latest"
]

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# Server host and port defaults
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", "8501"))