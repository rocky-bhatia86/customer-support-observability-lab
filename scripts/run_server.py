#!/usr/bin/env python3
"""Run the Support AI Lab chat UI + API locally.

Usage:
    python scripts/run_server.py
Then open http://localhost:8000
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from support_ai.api import create_app

if __name__ == "__main__":
    app = create_app()
    print("Support AI Lab running at http://localhost:8000")
    app.run(host="127.0.0.1", port=8000, debug=False)
