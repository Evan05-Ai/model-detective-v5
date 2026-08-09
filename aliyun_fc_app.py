#!/usr/bin/env python3
"""
Model Detective Web - Alibaba Cloud Function Compute Adapter

This file adapts the Flask app for Alibaba Cloud Function Compute (FC).
Uses simple WSGI handler for HTTP triggers.
"""

import os
import sys

# ── path setup ──────────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _PROJECT_ROOT)

# ── import Flask app ────────────────────────────────────────
from web.app import app

# ── FC Handler for HTTP Triggers ────────────────────────────
def handler(environ, start_response):
    """
    Alibaba Cloud Function Compute WSGI handler.
    
    For HTTP triggers, FC calls this handler with WSGI environ.
    """
    return app(environ, start_response)


# For custom runtime or event triggers (if needed)
def handle_event(event, context):
    """
    Event trigger handler (not used for HTTP triggers).
    """
    import json
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({'message': 'Event received', 'event': event})
    }
