"""
IndicDoc-AI Streamlit Application Entrypoint
Redirects seamlessly to frontend/app.py so running 'streamlit run app.py' works out of the box.
"""
import runpy
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_APP = BASE_DIR / "frontend" / "app.py"

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

if __name__ == "__main__" or "streamlit" in sys.modules:
    runpy.run_path(str(FRONTEND_APP), run_name="__main__")