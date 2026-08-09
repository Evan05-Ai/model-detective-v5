#!/usr/bin/env python3
"""
Model Detective Web - Launcher

Quick start:
  python run_web.py            # Start on http://localhost:5000
  PORT=8080 python run_web.py  # Custom port

Then open your browser to http://localhost:5000
"""

import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web.app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"")
    print(f"  [Model Detective Web] Starting server...")
    print(f"  URL: http://localhost:{port}")
    print(f"  Host: {host}")
    print(f"  Press Ctrl+C to stop")
    print(f"")
    app.run(host=host, port=port, debug=False, threaded=True)
