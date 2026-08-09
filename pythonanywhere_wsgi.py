#!/usr/bin/env python3
"""
PythonAnywhere WSGI Configuration File

This file should be referenced in the PythonAnywhere Web tab:
Source code: /home/YOUR_USERNAME/model-detective
Working directory: /home/YOUR_USERNAME/model-detective
WSGI configuration file: /var/www/YOUR_USERNAME_pythonanywhere_com_wsgi.py

Content for /var/www/YOUR_USERNAME_pythonanywhere_com_wsgi.py:
"""

import sys
import os

# Add your project directory to the sys.path
path = '/home/YOUR_USERNAME/model-detective'
if path not in sys.path:
    sys.path.insert(0, path)

# Set environment variables if needed
os.environ['FLASK_ENV'] = 'production'

# Import the application
from flask_app import application
