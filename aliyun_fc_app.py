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


# Aliyun FC 3.0 HTTP handler format
def fc_handler(event, context):
    """
    FC 3.0 HTTP trigger handler.
    
    Args:
        event: HTTP request event dict
        context: FC context
    
    Returns:
        HTTP response dict
    """
    import json
    from io import BytesIO
    
    # Parse event
    if isinstance(event, str):
        event = json.loads(event)
    
    # Extract request info
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
        'SERVER_PORT': '443',
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
    
    # Add HTTP headers
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
    
    # Build response
    body_content = b''.join(response_body)
    
    # Check if binary
    content_type = dict(response_headers).get('Content-Type', '')
    is_binary = not content_type.startswith(('text/', 'application/json', 'application/javascript'))
    
    if is_binary:
        import base64
        body_str = base64.b64encode(body_content).decode('utf-8')
        is_base64 = True
    else:
        body_str = body_content.decode('utf-8', errors='replace')
        is_base64 = False
    
    return {
        'statusCode': int(response_status.split()[0]),
        'headers': dict(response_headers),
        'body': body_str,
        'isBase64Encoded': is_base64
    }
