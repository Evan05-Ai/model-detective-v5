#!/usr/bin/env python3
"""
Model Detective Web - Alibaba Cloud Function Compute Adapter

This file adapts the Flask app for Alibaba Cloud Function Compute (FC).
FC uses a handler function format similar to AWS Lambda.
"""

import os
import sys
import base64
from io import BytesIO
from urllib.parse import urlparse

# ── path setup ──────────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _PROJECT_ROOT)

# ── import Flask app ────────────────────────────────────────
from web.app import app

# ── FC Handler ──────────────────────────────────────────────
def handler(environ, start_response):
    """
    Alibaba Cloud Function Compute handler.
    
    Args:
        environ: WSGI environ dict from FC
        start_response: WSGI start_response function
    
    Returns:
        Response body iterable
    """
    # FC may pass the request through differently, normalize it
    return app(environ, start_response)


# Alternative: Use Flask's built-in wsgi_app for simpler integration
def simple_handler(event, context):
    """
    Simple HTTP trigger handler for Function Compute.
    
    For HTTP triggers, FC invokes this function with:
    - event: Contains HTTP request info
    - context: Runtime context
    """
    import json
    from flask import Request
    
    # Parse the event
    if isinstance(event, str):
        event = json.loads(event)
    
    # Extract HTTP method, path, headers, body
    http_method = event.get('httpMethod', 'GET')
    path = event.get('path', '/')
    headers = event.get('headers', {})
    query_params = event.get('queryParameters', {})
    body = event.get('body', '')
    
    # Build WSGI environ
    environ = {
        'REQUEST_METHOD': http_method,
        'SCRIPT_NAME': '',
        'PATH_INFO': path,
        'QUERY_STRING': '&'.join([f"{k}={v}" for k, v in query_params.items()]),
        'SERVER_NAME': headers.get('Host', 'localhost'),
        'SERVER_PORT': '80',
        'HTTP_HOST': headers.get('Host', 'localhost'),
        'CONTENT_TYPE': headers.get('Content-Type', ''),
        'CONTENT_LENGTH': str(len(body)) if body else '0',
        'wsgi.version': (1, 0),
        'wsgi.url_scheme': 'https',
        'wsgi.input': BytesIO(body.encode() if body else b''),
        'wsgi.errors': sys.stderr,
        'wsgi.multithread': False,
        'wsgi.multiprocess': False,
        'wsgi.run_once': False,
    }
    
    # Add HTTP headers to environ
    for header_name, header_value in headers.items():
        key = 'HTTP_' + header_name.upper().replace('-', '_')
        environ[key] = header_value
    
    # Response collector
    response_status = None
    response_headers = []
    response_body = []
    
    def start_response(status, headers):
        nonlocal response_status, response_headers
        response_status = status
        response_headers = headers
        return response_body.append
    
    # Call Flask app
    response_iter = app(environ, start_response)
    
    # Collect response
    for chunk in response_iter:
        response_body.append(chunk)
    
    # Build FC response
    response_body_bytes = b''.join(response_body)
    
    # Check if response is binary
    content_type = dict(response_headers).get('Content-Type', '')
    is_binary = not content_type.startswith(('text/', 'application/json', 'application/javascript'))
    
    if is_binary:
        body_content = base64.b64encode(response_body_bytes).decode('utf-8')
        is_base64 = True
    else:
        body_content = response_body_bytes.decode('utf-8', errors='replace')
        is_base64 = False
    
    return {
        'statusCode': int(response_status.split()[0]),
        'headers': dict(response_headers),
        'body': body_content,
        'isBase64Encoded': is_base64
    }
