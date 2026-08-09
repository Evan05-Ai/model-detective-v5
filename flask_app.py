#!/usr/bin/env python3
"""
Model Detective Web - PythonAnywhere Entry Point

This file is the WSGI entry point for PythonAnywhere deployment.
It exposes the 'application' variable that PythonAnywhere expects.
"""

import os
import sys

# ── path setup ──────────────────────────────────────────────
# Get the directory containing this file
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _PROJECT_ROOT)

# ── import the Flask app ────────────────────────────────────
from web.app import app

# PythonAnywhere expects 'application' variable
application = app

# For local testing
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
