import os, subprocess, sys

port = os.environ.get("PORT", "8501")
subprocess.run(
    [sys.executable, "-m", "streamlit", "run", "app.py",
     "--server.headless", "true",
     "--server.port", port],
    cwd=os.path.dirname(os.path.abspath(__file__)),
)
