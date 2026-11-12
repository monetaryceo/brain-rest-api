import urllib.request
import json

BASE = "https://thebrain.137-184-23-228.sslip.io/brain-api"
API_KEY = "tFYk0cxOHPl_31VevnrcFgNYzGjEJHUgxjt0TLGzHe4"

def req(method, path, data=None, auth=True):
    url = f"{BASE}{path}"
    body = json.dumps(data).encode() if data else None
    r = urllib.request.Request(url, data=body, method=method)
    r.add_header("Content-Type", "application/json")
    if auth:
        r.add_header("Authorization", f"Bearer {API_KEY}")
    try:
        resp = urllib.request.urlopen(r)
        return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode()) if e.read() else {}

# Test 1: Health (no auth needed)
status, body = req("GET", "/v1/health", auth=False)
print(f"1. Health: {status} - {body.get('status')}")

# Test 2: Models with auth
status, body = req("GET", "/v1/models")
print(f"2. Models: {status} - {len(body.get('data', []))} models")

# Test 3: Tools
status, body = req("GET", "/v1/tools")
print(f"3. Tools: {status} - {len(body.get('data', []))} tools")

# Test 4: Chat completions (non-streaming)
status, body = req("POST", "/v1/chat/completions", {
    "model": "isis-trained",
    "messages": [{"role": "user", "content": "Hello, are you working?"}]
})
print(f"4. Chat: {status} - model={body.get('model')}, choices={len(body.get('choices', []))}")

# Test 5: MCP tools/list via POST
status, body = req("POST", "/mcp", {
    "jsonrpc": "2.0",
    "method": "tools/list",
    "id": 1
})
print(f"5. MCP tools/list: {status} - {len(body.get('result', {}).get('tools', []))} tools")

# Test 6: MCP initialize
status, body = req("POST", "/mcp", {
    "jsonrpc": "2.0",
    "method": "initialize",
    "id": 2
})
print(f"6. MCP initialize: {status} - {body.get('result', {}).get('serverInfo', {}).get('name')}")

# Test 7: MCP resources/list
status, body = req("POST", "/mcp", {
    "jsonrpc": "2.0",
    "method": "resources/list",
    "id": 3
})
print(f"7. MCP resources/list: {status} - {len(body.get('result', {}).get('resources', []))} resources")

# Test 8: Generate API key (no auth)
status, body = req("POST", "/v1/auth/keys", {"name": "test-key"}, auth=False)
print(f"8. Auth keys: {status} - key_prefix={body.get('api_key', '')[:12]}...")

print("\nALL_HTTPS_TESTS_DONE")