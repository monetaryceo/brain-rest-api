import urllib.request
import json

base = "http://127.0.0.1:8099"

# Test root endpoint
try:
    r = urllib.request.urlopen(f"{base}/")
    print("ROOT:", r.read().decode()[:200])
except Exception as e:
    print("ROOT ERROR:", e)

# Test health endpoint
try:
    r = urllib.request.urlopen(f"{base}/v1/health")
    print("HEALTH:", r.read().decode())
except Exception as e:
    print("HEALTH ERROR:", e)

# Test models endpoint (without auth - should fail)
try:
    r = urllib.request.urlopen(f"{base}/v1/models")
    print("MODELS (no auth):", r.read().decode()[:200])
except urllib.error.HTTPError as e:
    print("MODELS (no auth) status:", e.code)

# Test models endpoint (with auth)
try:
    req = urllib.request.Request(f"{base}/v1/models")
    req.add_header("Authorization", "Bearer tFYk0cxOHPl_31VevnrcFgNYzGjEJHUgxjt0TLGzHe4")
    r = urllib.request.urlopen(req)
    data = json.loads(r.read().decode())
    print("MODELS count:", len(data.get("data", [])))
except Exception as e:
    print("MODELS (auth) ERROR:", e)

# Test chat/completions
try:
    payload = {
        "model": "isis-trained",
        "messages": [{"role": "user", "content": "Hello, are you working?"}],
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{base}/v1/chat/completions", data=data)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer tFYk0cxOHPl_31VevnrcFgNYzGjEJHUgxjt0TLGzHe4")
    r = urllib.request.urlopen(req)
    result = json.loads(r.read().decode())
    print("CHAT:", json.dumps(result)[:300])
except Exception as e:
    print("CHAT ERROR:", e)

print("TESTS_DONE")