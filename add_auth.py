#!/usr/bin/env python3
"""Add API key authentication to server.py on the remote server."""
import re

with open("server.py", "r") as f:
    content = f.read()

# 1. Add API_KEY config after _bili_proc line
content = content.replace(
    '_bili_proc = None  # holds the running billion-context proxy subprocess',
    '_bili_proc = None  # holds the running billion-context proxy subprocess\n\nAPI_KEY = os.environ.get("BRAIN_API_KEY", "tFYk0cxOHPl_31VevnrcFgNYzGjEJHUgxjt0TLGzHe4")\nBRAIN_SERVER_NAME = "brain-rest-api"'
)

# 2. Add is_authenticated function before def json_response
auth_func = '''

def is_authenticated(handler):
    """Check API key authentication via Authorization: Bearer <token> header."""
    if not API_KEY:
        return True
    auth_header = handler.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        return token == API_KEY
    return False

'''
content = content.replace(
    'def json_response(handler, code, body, content_type="application/json"):',
    auth_func + 'def json_response(handler, code, body, content_type="application/json"):'
)

# 3. Add auth check at start of do_GET
content = content.replace(
    '    def do_GET(self):\n        parsed = urlparse(self.path)\n        path = parsed.path\n\n        if path == "/v1/models":',
    '    def do_GET(self):\n        parsed = urlparse(self.path)\n        path = parsed.path\n\n        if not is_authenticated(self):\n            json_response(self, 401, {"error": {"message": "Missing or invalid API key", "type": "auth_error", "code": 401}})\n            return\n\n        if path == "/v1/models":'
)

# 4. Add auth check at start of do_POST (after JSON parse, before route matching)
content = content.replace(
    '        if path == "/v1/chat/completions":',
    '        if not is_authenticated(self):\n            json_response(self, 401, {"error": {"message": "Missing or invalid API key", "type": "auth_error", "code": 401}})\n            return\n\n        if path == "/v1/chat/completions":'
)

with open("server.py", "w") as f:
    f.write(content)

print("server.py modified with API key authentication")
