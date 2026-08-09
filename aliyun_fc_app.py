#!/usr/bin/env python3
"""
Model Detective Web - Alibaba Cloud Function Compute Adapter

This file adapts the Flask app for Alibaba Cloud Function Compute (FC).
Uses standard WSGI interface for HTTP triggers.
"""

import os
import sys

# ── path setup ──────────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _PROJECT_ROOT)

# ── import Flask app ────────────────────────────────────────
from web.app import app

# FC 3.0 HTTP trigger uses standard WSGI handler
def handler(environ, start_response):
    """
    WSGI entry point for Alibaba Cloud Function Compute.
    """
    return app(environ, start_response)
