import sys
import subprocess
import time
import os
import signal

def main():
    python_exe = sys.executable
    print("=" * 65)
    print(" 📑 IndicDoc-AI: Unified Application Launcher")
    print("=" * 65)
    print(f"[*] Python Runtime: {python_exe}")
    print("[*] Starting Backend (FastAPI on http://127.0.0.1:8000)...")

    # Start FastAPI backend
    backend_cmd = [python_exe, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"]
    backend_proc = subprocess.Popen(backend_cmd)

    # Give backend a moment to initialize
    time.sleep(2)

    print("[*] Starting Frontend (Streamlit on http://localhost:8501)...")
    frontend_cmd = [python_exe, "-m", "streamlit", "run", "frontend/app.py", "--server.port", "8501", "--server.headless", "true"]
    frontend_proc = subprocess.Popen(frontend_cmd)

    print("\n" + "=" * 65)
    print(" 🚀 IndicDoc-AI is LIVE!")
    print(" -------------------------------------------------------------")
    print(" 🌐 Interactive Web UI : http://localhost:8501")
    print(" 📖 REST API Swagger   : http://127.0.0.1:8000/docs")
    print(" 💚 Health Check       : http://127.0.0.1:8000/")
    print(" -------------------------------------------------------------")
    print(" Press Ctrl+C in this terminal to safely stop all services.")
    print("=" * 65 + "\n")

    try:
        while True:
            time.sleep(1)
            # If any process terminated prematurely, break
            if backend_proc.poll() is not None or frontend_proc.poll() is not None:
                break
    except KeyboardInterrupt:
        print("\n[!] Shutting down IndicDoc-AI services...")
    finally:
        for p, name in [(backend_proc, "Backend"), (frontend_proc, "Frontend")]:
            if p and p.poll() is None:
                print(f"[*] Terminating {name}...")
                p.terminate()
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.kill()
        print("[✓] All services stopped cleanly. Goodbye!")

if __name__ == "__main__":
    main()
