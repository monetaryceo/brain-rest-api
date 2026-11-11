#!/usr/bin/env python3
"""
Example client for the Brain REST API (OpenAI-compatible).
Shows how Cline or any OpenAI-compatible client can use it.
"""

import json
import urllib.request

BASE = "http://localhost:8099/v1"


def get(path):
    req = urllib.request.Request(f"{BASE}{path}")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def post(path, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


if __name__ == "__main__":
    # 1. List models
    print("=== Models ===")
    models = get("/models")
    for m in models["data"]:
        print(f"  {m['id']} ({m.get('role', '?')})")

    # 2. Chat completion with tool calling (run nuclei scan)
    print("\n=== Chat Completion (nuclei scan) ===")
    resp = post("/chat/completions", {
        "model": "isis-trained",
        "messages": [
            {"role": "user", "content": "Run a nuclei vulnerability scan on https://example.com"}
        ],
        "tools": [{"type": "function", "function": {
            "name": "nuclei_scan",
            "description": "Run a nuclei vulnerability scan on a target URL",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Target URL to scan"},
                    "severity": {"type": "string", "default": "critical,high,medium"},
                },
                "required": ["target"],
            },
        }}],
        "tool_choice": "required",
    })
    print(json.dumps(resp, indent=2))

    # 3. Direct tool call
    print("\n=== Direct Tool Call (agent_list) ===")
    result = post("/tools/call", {"name": "agent_list", "arguments": {}})
    print(json.dumps(result, indent=2)[:1000])