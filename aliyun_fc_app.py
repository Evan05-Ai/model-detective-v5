#!/usr/bin/env python3
"""
Model Detective Web - Alibaba Cloud Function Compute Adapter

This file adapts the Flask app for Alibaba Cloud Function Compute (FC).
Compatible with FC 3.0 HTTP triggers.
"""

import os
import sys
import json
import base64
from io import BytesIO

# ── path setup ──────────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _PROJECT_ROOT)

# ── import Flask app ────────────────────────────────────────
from web.app import app


def handler(event, context):
    """
    Alibaba Cloud Function Compute 3.0 HTTP handler.
    
    Args:
        event: HTTP request event (bytes, string, or dict)
        context: FC context object
    
    Returns:
        HTTP response dict
    """
    # Handle different event types
    if isinstance(event, bytes):
        try:
            event = json.loads(event.decode('utf-8'))
        except:
            event = {}
    elif isinstance(event, str):
        try:
            event = json.loads(event)
        except:
            event = {}
    elif not isinstance(event, dict):
        event = {}
    
    # Get request info from event
    http_method = event.get('httpMethod', 'GET')
    path = event.get('path', '/')
    headers = event.get('headers', {}) or {}
    query_params = event.get('queryParameters', {}) or {}
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
    try:
        response_iter = app(environ, start_response)
        
        # Collect response body
        for chunk in response_iter:
            if isinstance(chunk, str):
                response_body.append(chunk.encode('utf-8'))
            else:
                response_body.append(chunk)
        
        # Build response
        body_content = b''.join(response_body)
        
        # Check if binary response
        content_type = ''
        for header_name, header_value in response_headers:
            if header_name.lower() == 'content-type':
                content_type = header_value
                break
        
        is_binary = not content_type.startswith(('text/', 'application/json', 'application/javascript'))
        
        if is_binary:
            body_str = base64.b64encode(body_content).decode('utf-8')
            is_base64 = True
        else:
            body_str = body_content.decode('utf-8', errors='replace')
            is_base64 = False
        
        # Build response headers dict
        headers_dict = {}
        for header_name, header_value in response_headers:
            headers_dict[header_name] = header_value
        
        return {
            'statusCode': int(response_status.split()[0]),
            'headers': headers_dict,
            'body': body_str,
            'isBase64Encoded': is_base64
        }
        
    except Exception as e:
        # Return error response
        import traceback
        error_msg = f'Error: {str(e)}\n{traceback.format_exc()}'
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'text/plain'},
            'body': error_msg
        }
