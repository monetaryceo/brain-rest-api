#!/usr/bin/env python3
"""
Brain REST API — OpenAI-compatible endpoint for all brain tools, skills, and models.
Runs entirely on the remote server. No dependencies on any local PC or device.
All ISIS tools call localhost:8088 directly.

Implements the OpenAI Chat Completions API format:
  GET  /v1/models        -> list of models
  POST /v1/chat/completions -> chat completion with tool calling
  POST /v1/auth/keys     -> generate a new API key

Auth: Authorization: Bearer <api_key> required on all endpoints except /v1/auth/keys

Exposes:
  - /v1/models, /v1/tools, /v1/health (REST)
  - /mcp (MCP JSON-RPC 2.0: tools/list, tools/call, resources/list, prompts/list)
  - Brain MCP tools, ISIS tools (native on server), billion-context tools
  - All brain models + cloud models (OpenRouter, NVIDIA)

No external dependencies — Python stdlib only.
"""

import json
import os
import sys
import time
import uuid
import subprocess
import secrets
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import urllib.request
import urllib.error

# Load .env file manually (no external deps)
ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(ENV_FILE):
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

WORKSPACE = "/home/brain-agent"
AGENT_TOOLCHAIN = os.path.join(WORKSPACE, "agent-toolchain")
AGENT_CLI = os.path.join(AGENT_TOOLCHAIN, "bin", "agent-cli.js")
ISIS_BASE_URL = "http://127.0.0.1:8088"

BILLION_CTX_DIR = os.path.join(WORKSPACE, "billion-context")
BILLION_CTX_DIST = os.path.join(BILLION_CTX_DIR, "dist", "index.js")
BILLION_CTX_PORT = int(os.environ.get("BILI_PORT", "8787"))
BILLION_CTX_HOST = os.environ.get("BILI_HOST", "127.0.0.1")
BILLION_CTX_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "billion-context")
BILLION_CTX_CONFIG_FILE = os.path.join(BILLION_CTX_CONFIG_DIR, "billion-context.json")
_bili_proc = None

PRIMARY_API_KEY = os.environ.get("BRAIN_API_KEY", "tFYk0cxOHPl_31VevnrcFgNYzGjEJHUgxjt0TLGzHe4")
BRAIN_SERVER_NAME = "brain-rest-api"

API_KEYS = {}
if PRIMARY_API_KEY:
    API_KEYS[PRIMARY_API_KEY] = {"created": int(time.time()), "name": "primary"}

# ---------------------------------------------------------------------------
# Dynamic model fetching from cloud providers
# ---------------------------------------------------------------------------

def fetch_openrouter_models():
    """Fetch all available models from OpenRouter API"""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("WARNING: OPENROUTER_API_KEY not set, skipping OpenRouter models")
        return []
    
    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
            models = []
            for m in data.get("data", []):
                model_id = m.get("id", "")
                if model_id.startswith("openrouter/") or ":free" in model_id:
                    continue
                models.append({
                    "id": f"openrouter/{model_id}",
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "openrouter",
                    "base": model_id,
                    "provider": "openrouter",
                    "endpoint": "https://openrouter.ai/api/v1",
                    "api_key_env": "OPENROUTER_API_KEY",
                    "capabilities": ["text", "tools", "chat"],
                    "permission": [],
                })
            print(f"Loaded {len(models)} OpenRouter models")
            return models
    except Exception as e:
        print(f"ERROR fetching OpenRouter models: {e}")
        return []

def fetch_nvidia_models():
    """Fetch all available models from NVIDIA API"""
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        print("WARNING: NVIDIA_API_KEY not set, skipping NVIDIA models")
        return []
    
    try:
        req = urllib.request.Request(
            "https://integrate.api.nvidia.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
            models = []
            for m in data.get("data", []):
                model_id = m.get("id", "")
                models.append({
                    "id": f"nvidia/{model_id}",
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "nvidia",
                    "base": model_id,
                    "provider": "nvidia",
                    "endpoint": "https://integrate.api.nvidia.com/v1",
                    "api_key_env": "NVIDIA_API_KEY",
                    "capabilities": ["text", "tools", "chat"],
                    "permission": [],
                })
            print(f"Loaded {len(models)} NVIDIA models")
            return models
    except Exception as e:
        print(f"ERROR fetching NVIDIA models: {e}")
        return []

# ---------------------------------------------------------------------------
# Base local models (hardcoded) - Part 1
# ---------------------------------------------------------------------------

LOCAL_MODELS = [
    {"id": "lfm3-1.7b-uncensored", "object": "model", "created": int(time.time()), "owned_by": "brain", "base": "LFM3-1.7B-Uncensored", "role": "primary", "port": 8081, "file": "lfm3-1.7b-uncensored-q4_k_m.gguf", "capabilities": ["text", "tools", "chat"], "permission": []},
    {"id": "deepseek-r1-llama-8b-abliterated", "object": "model", "created": int(time.time()), "owned_by": "brain", "base": "DeepSeek-R1-Llama-8B-Abliterated", "role": "reasoning", "port": 8086, "file": "deepseek-r1-llama-8b-abliterated-q4_k_m.gguf", "capabilities": ["text", "tools", "reasoning", "chat"], "permission": []},
    {"id": "qwen2.5-moe-2x1.5b-uncensored", "object": "model", "created": int(time.time()), "owned_by": "brain", "base": "Qwen2.5-MoE-2x1.5B-Uncensored", "role": "moe", "port": 8092, "file": "qwen2.5-moe-2x1.5b-uncensored-q4_k_m.gguf", "capabilities": ["text", "tools", "moe", "chat"], "permission": []},
    {"id": "hope", "object": "model", "created": int(time.time()), "owned_by": "brain", "base": "HOPE", "role": "quant", "port": 8084, "file": "hope-q4_k_m.gguf", "capabilities": ["text", "tools", "quant", "chat"], "permission": []},
    {"id": "aira", "object": "model", "created": int(time.time()), "owned_by": "brain", "base": "AIRA", "role": "risk", "port": 8083, "file": "aira-q4_k_m.gguf", "capabilities": ["text", "tools", "risk", "chat"], "permission": []},
    {"id": "aether-trading", "object": "model", "created": int(time.time()), "owned_by": "brain", "base": "Aether-Trading", "role": "trading", "port": 8081, "file": "aether-trading-q4_k_m.gguf", "capabilities": ["text", "tools", "trading", "chat"], "permission": []},
    {"id": "deepseek-r1-qwen-7b-abliterated", "object": "model", "created": int(time.time()), "owned_by": "brain", "base": "DeepSeek-R1-Qwen-7B-Abliterated", "role": "reasoning-alt", "port": 8087, "file": "deepseek-r1-qwen-7b-abliterated-q4_k_m.gguf", "capabilities": ["text", "tools", "reasoning", "chat"], "permission": []},
    {"id": "wan2.2-ti2v-5b", "object": "model", "created": int(time.time()), "owned_by": "brain", "base": "Wan2.2-TI2V-5B", "role": "video", "port": 8088, "file": "wan2.2-ti2v-5b-q4_k_m.gguf", "backend": "diffusers", "capabilities": ["video", "image_generation", "text"], "permission": []},
    {"id": "laya-multilingual", "object": "model", "created": int(time.time()), "owned_by": "brain", "base": "Laya-Multilingual", "role": "multilingual", "port": 8089, "file": "laya-multilingual-f16.gguf", "backend": "transformers", "capabilities": ["text", "tools", "multilingual", "chat"], "permission": []},
    {"id": "jev-style-0.8b-decision-v3", "object": "model", "created": int(time.time()), "owned_by": "brain", "base": "Jev-Style-0.8B-Decision-v3", "role": "decision", "port": 8090, "file": "jev-style-0.8b-decision-v3-q4_k_m.gguf", "capabilities": ["text", "tools", "decision", "chat"], "permission": []},
    {"id": "jev-style-2b-decision-v3", "object": "model", "created": int(time.time()), "owned_by": "brain", "base": "Jev-Style-2B-Decision-v3", "role": "decision", "port": 8091, "file": "jev-style-2b-decision-v3-q4_k_m.gguf", "capabilities": ["text", "tools", "decision", "chat"], "permission": []},
    {"id": "isis-trained", "object": "model", "created": int(time.time()), "owned_by": "isis", "base": "needle3+lfm3-omni", "role": "pentest", "path": "/opt/the-brain/models/isis-trained/isis.safetensors", "uncensored": True, "capabilities": ["web_search", "docker_sandbox", "pentest", "uncensored_response", "strix_recon", "nuclei_vuln_scan", "herdr_bot_swarm", "infinity_swarm", "tmux_session", "deer_flow_workflow", "swarmchat_communication", "abliteration", "quantum_math", "qlora_adapter", "openai_compatible_api"], "permission": []},
    {"id": "llama3.2:1b", "object": "model", "created": int(time.time()), "owned_by": "ollama", "base": "llama3.2", "role": "chat", "endpoint": "http://127.0.0.1:11434", "capabilities": ["text", "tools", "chat"], "permission": []},
    {"id": "lfm3-omni", "object": "model", "created": int(time.time()), "owned_by": "liquidai", "base": "LFM3-Omni-2B", "role": "multimodal", "capabilities": ["text", "vision", "audio", "tools", "any_to_any", "chat"], "context_length": 32768, "modality": "any-to-any", "permission": []},
]

# Build complete model list: local + cloud
def build_model_list():
    """Build the complete model list including dynamically fetched cloud models"""
    models = LOCAL_MODELS.copy()
    models.extend(fetch_openrouter_models())
    models.extend(fetch_nvidia_models())
    return models

BRAIN_MODELS = build_model_list()

# ---------------------------------------------------------------------------
# Tool registry — ALL tools (brain MCP + ISIS + billion-context + auth)
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "agent_list",
            "description": "List all agent-toolchain tools and their install status.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "agent_run",
            "description": "Run an agent-toolchain CLI tool and capture stdout/stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string", "description": "Tool name (ghostman, ctx7, rea, skills, agent-browser, dsh, etc.)"},
                    "args": {"type": "array", "items": {"type": "string"}, "description": "CLI arguments to pass to the tool"},
                },
                "required": ["tool"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "agent_install",
            "description": "Install an agent-toolchain tool's dependencies (pnpm/npm/pip).",
            "parameters": {
                "type": "object",
                "properties": {"tool": {"type": "string", "description": "Tool name to install"}},
                "required": ["tool"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "agent_build",
            "description": "Build an agent-toolchain tool.",
            "parameters": {
                "type": "object",
                "properties": {"tool": {"type": "string", "description": "Tool name to build"}},
                "required": ["tool"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "agent_doctor",
            "description": "Check runtimes and tool binaries for health.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "context7_search",
            "description": "Search Context7 documentation libraries for up-to-date library docs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "library_name": {"type": "string", "description": "Optional library name to scope the search"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rea_analyze",
            "description": "Run REA reverse-engineering analysis on a target binary/app.",
            "parameters": {
                "type": "object",
                "properties": {"target": {"type": "string", "description": "Target path or URL to analyze"}},
                "required": ["target"],
                "additionalProperties": False,
            },
        },
    },
    # ISIS tools (native on server via localhost:8088 — NO SSH)
    {
        "type": "function",
        "function": {
            "name": "nuclei_scan",
            "description": "Run nuclei vulnerability scan on a target URL (ISIS pentest server).",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Target URL to scan"},
                    "severity": {"type": "string", "default": "critical,high,medium", "description": "Severity levels"},
                },
                "required": ["target"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish_scan",
            "description": "Complete a penetration test scan with findings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "findings": {"type": "array", "description": "List of vulnerability findings"},
                    "findings_count": {"type": "integer", "description": "Number of findings"},
                    "target": {"type": "string", "description": "Target that was scanned"},
                    "status": {"type": "string", "description": "Scan status"},
                },
                "required": ["findings", "target", "status"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Perform a web search via the ISIS server (needle model).",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spawn_sandbox",
            "description": "Spawn a Docker sandbox container via ISIS.",
            "parameters": {
                "type": "object",
                "properties": {"image": {"type": "string", "default": "brain-math-sandbox:latest", "description": "Docker image to spawn"}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pentest",
            "description": "Run a full pentest (strix + nuclei) against a target via ISIS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Target to pentest"},
                    "tools": {"type": "array", "items": {"type": "string"}, "default": ["strix", "nuclei"], "description": "Tools to use"},
                },
                "required": ["target"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tmux_session",
            "description": "Run a command in a tmux session via ISIS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session": {"type": "string", "default": "isis-session", "description": "Tmux session name"},
                    "command": {"type": "string", "default": "echo ISIS", "description": "Command to run"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "swarmchat",
            "description": "Send a message via swarmchat through ISIS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Message to send"},
                    "channel": {"type": "string", "default": "isis", "description": "Channel name"},
                },
                "required": ["message"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "herdr_swarm",
            "description": "Run a herdr bot swarm task via ISIS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Task for the swarm"},
                    "num_bots": {"type": "integer", "default": 5, "description": "Number of bots"},
                },
                "required": ["task"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "infinity_swarm",
            "description": "Run an infinity swarm task via ISIS.",
            "parameters": {
                "type": "object",
                "properties": {"task": {"type": "string", "description": "Task for the infinity swarm"}},
                "required": ["task"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deer_flow",
            "description": "Run a DeerFlow workflow via ISIS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow": {"type": "string", "default": "default", "description": "Workflow name"},
                    "steps": {"type": "array", "items": {"type": "string"}, "default": [], "description": "Workflow steps"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "capabilities",
            "description": "List ISIS server capabilities.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "health",
            "description": "Check ISIS server health.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    # Auth tool — generate API keys
    {
        "type": "function",
        "function": {
            "name": "generate_api_key",
            "description": "Generate a new API key for accessing the Brain REST API.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Optional name for the API key"},
                },
                "additionalProperties": False,
            },
        },
    },
    # Billion-context tools
    {
        "type": "function",
        "function": {
            "name": "bili_start",
            "description": "Start the billion-context context-compression proxy server.",
            "parameters": {
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "default": 8787, "description": "Proxy port"},
                    "host": {"type": "string", "default": "127.0.0.1", "description": "Proxy bind host"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bili_status",
            "description": "Check billion-context proxy status and configuration.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bili_compress",
            "description": "Compress a message range via billion-context ACP context management.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID for compression state"},
                    "start": {"type": "integer", "description": "Start message index"},
                    "end": {"type": "integer", "description": "End message index (exclusive)"},
                },
                "required": ["session_id", "start", "end"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bili_decompress",
            "description": "Decompress a previously compressed message range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID for compression state"},
                    "ref_id": {"type": "string", "description": "Compression reference ID to decompress"},
                },
                "required": ["session_id", "ref_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bili_search_context",
            "description": "Search over compressed summaries and visible messages via billion-context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID to search"},
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["session_id", "query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bili_acp_status",
            "description": "Get billion-context ACP context-usage overview and compressible ranges.",
            "parameters": {
                "type": "object",
                "properties": {"session_id": {"type": "string", "description": "Session ID to check"}},
                "additionalProperties": False,
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def now_ts():
    return int(time.time())

def make_id(prefix="cmpl"):
    return f"{prefix}-{uuid.uuid4().hex[:24]}"

def is_authenticated(handler):
    auth_header = handler.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        return token in API_KEYS
    return False

def json_response(handler, code, body, content_type="application/json"):
    data = json.dumps(body).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
    handler.end_headers()
    handler.wfile.write(data)

def read_body(handler):
    length = int(handler.headers.get("Content-Length", 0))
    return handler.rfile.read(length) if length else b""

# ---------------------------------------------------------------------------
# ISIS native HTTP client (no SSH — calls localhost:8088 directly)
# ---------------------------------------------------------------------------
def isis_request(method, path, payload=None, timeout=30):
    url = f"{ISIS_BASE_URL}{path}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "detail": e.read().decode("utf-8", errors="replace")[:500]}
    except Exception as e:
        return {"error": str(e)}

def run_agent_cli(*cmd):
    try:
        proc = subprocess.run(
            ["node", AGENT_CLI, *cmd],
            capture_output=True, text=True, timeout=60,
            cwd=AGENT_TOOLCHAIN,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except Exception as e:
        return -1, "", str(e)

def execute_tool(name, arguments):
    # ---- Brain MCP tools ----
    if name == "agent_list":
        code, out, err = run_agent_cli("list")
        return {"code": code, "stdout": out, "stderr": err}
    if name == "agent_run":
        tool = arguments.get("tool")
        args = arguments.get("args", [])
        code, out, err = run_agent_cli(tool, *args)
        return {"code": code, "stdout": out, "stderr": err}
    if name == "agent_install":
        code, out, err = run_agent_cli("install", arguments.get("tool"))
        return {"code": code, "stdout": out, "stderr": err}
    if name == "agent_build":
        code, out, err = run_agent_cli("build", arguments.get("tool"))
        return {"code": code, "stdout": out, "stderr": err}
    if name == "agent_doctor":
        code, out, err = run_agent_cli("doctor")
        return {"code": code, "stdout": out, "stderr": err}
    if name == "context7_search":
        code, out, err = run_agent_cli("context7", "search", arguments.get("query", ""),
                                       *(["--library", arguments.get("library_name")] if arguments.get("library_name") else []))
        return {"code": code, "stdout": out, "stderr": err}
    if name == "rea_analyze":
        code, out, err = run_agent_cli("rea", "analyze", arguments.get("target", ""))
        return {"code": code, "stdout": out, "stderr": err}

    # ISIS tools (native on server, no SSH)
    if name == "nuclei_scan":
        return isis_request("POST", "/nuclei_scan", {
            "target": arguments.get("target"),
            "severity": arguments.get("severity", "critical,high,medium"),
        })
    if name == "finish_scan":
        return isis_request("POST", "/pentest", {
            "target": arguments.get("target"),
            "tools": ["nuclei"],
            "_finish": True,
            "findings": arguments.get("findings", []),
            "findings_count": arguments.get("findings_count", 0),
            "status": arguments.get("status", "completed"),
        })
    if name == "web_search":
        return isis_request("POST", "/web_search", {"query": arguments.get("query", "")})
    if name == "spawn_sandbox":
        return isis_request("POST", "/spawn_sandbox", {
            "image": arguments.get("image", "brain-math-sandbox:latest"),
        })
    if name == "pentest":
        return isis_request("POST", "/pentest", {
            "target": arguments.get("target"),
            "tools": arguments.get("tools", ["strix", "nuclei"]),
        })
    if name == "tmux_session":
        return isis_request("POST", "/tmux", {
            "session": arguments.get("session", "isis-session"),
            "command": arguments.get("command", "echo ISIS"),
        })
    if name == "swarmchat":
        return isis_request("POST", "/swarmchat", {
            "message": arguments.get("message", ""),
            "channel": arguments.get("channel", "isis"),
        })
    if name == "herdr_swarm":
        return isis_request("POST", "/herdr", {
            "task": arguments.get("task", ""),
            "num_bots": arguments.get("num_bots", 5),
        })
    if name == "infinity_swarm":
        return isis_request("POST", "/infinity", {"task": arguments.get("task", "")})
    if name == "deer_flow":
        return isis_request("POST", "/deer_flow", {
            "workflow": arguments.get("workflow", "default"),
            "steps": arguments.get("steps", []),
        })
    if name == "capabilities":
        return isis_request("GET", "/capabilities")
    if name == "health":
        return isis_request("GET", "/health")

    # Auth tool
    if name == "generate_api_key":
        new_key = secrets.token_urlsafe(32)
        key_name = arguments.get("name", f"key-{int(time.time())}")
        API_KEYS[new_key] = {"created": int(time.time()), "name": key_name}
        return {
            "api_key": new_key,
            "name": key_name,
            "created": int(time.time()),
            "base_url": "https://thebrain.137-184-23-228.sslip.io/brain-api",
            "usage": "Authorization: Bearer <api_key>",
            "note": "Save this key now — it will not be shown again.",
        }

    # Billion-context tools
    if name == "bili_start":
        return start_bili_proxy(arguments.get("port", BILLION_CTX_PORT), arguments.get("host", BILLION_CTX_HOST))
    if name == "bili_status":
        return check_bili_status()
    if name == "bili_compress":
        return bili_compress_range(arguments.get("session_id", ""), arguments.get("start", 0), arguments.get("end", 0))
    if name == "bili_decompress":
        return bili_decompress_range(arguments.get("session_id", ""), arguments.get("ref_id", ""))
    if name == "bili_search_context":
        return bili_search(arguments.get("session_id", ""), arguments.get("query", ""))
    if name == "bili_acp_status":
        return bili_acp_status(arguments.get("session_id", ""))

# ---------------------------------------------------------------------------
# Billion-context proxy management
# ---------------------------------------------------------------------------
def start_bili_proxy(port, host):
    global _bili_proc
    if _bili_proc is not None and _bili_proc.poll() is None:
        return {"status": "already_running", "port": port, "pid": _bili_proc.pid}

    os.makedirs(BILLION_CTX_CONFIG_DIR, exist_ok=True)

    if not os.path.exists(BILLION_CTX_CONFIG_FILE):
        config = {"port": port, "host": host, "providers": {}}
        try:
            with open(BILLION_CTX_CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            return {"error": f"failed to write config: {e}"}

    try:
        cmd = ["node", BILLION_CTX_DIST]
        env = dict(os.environ)
        env["PORT"] = str(port)
        env["ACP_HOST"] = host
        _bili_proc = subprocess.Popen(cmd, cwd=BILLION_CTX_DIR, env=env,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return {"status": "started", "port": port, "pid": _bili_proc.pid,
                "base_url": f"http://{host}:{port}"}
    except Exception as e:
        return {"error": f"failed to start billion-context: {e}"}

def check_bili_status():
    global _bili_proc
    running = _bili_proc is not None and _bili_proc.poll() is None
    config_exists = os.path.exists(BILLION_CTX_CONFIG_FILE)
    dist_exists = os.path.exists(BILLION_CTX_DIST)
    result = {
        "running": running,
        "installed": dist_exists,
        "config_exists": config_exists,
        "port": BILLION_CTX_PORT,
        "host": BILLION_CTX_HOST,
        "base_url": f"http://{BILLION_CTX_HOST}:{BILLION_CTX_PORT}",
        "proxy_dir": BILLION_CTX_DIR,
    }
    if running:
        result["pid"] = _bili_proc.pid
    if config_exists:
        try:
            with open(BILLION_CTX_CONFIG_FILE) as f:
                result["config"] = json.load(f)
        except Exception:
            result["config"] = None
    return result

def _bili_request(method, path, payload=None, timeout=30):
    url = f"http://{BILLION_CTX_HOST}:{BILLION_CTX_PORT}{path}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "detail": e.read().decode("utf-8", errors="replace")[:500]}
    except Exception as e:
        return {"error": str(e)}

def bili_compress_range(session_id, start, end):
    return _bili_request("POST", "/compress", {"session_id": session_id, "start": start, "end": end})

# ---------------------------------------------------------------------------
# OpenAI-format responses
# ---------------------------------------------------------------------------
def models_list_response():
    return {"object": "list", "data": BRAIN_MODELS}

def chat_completions_response(model, choices, usage=None):
    return {
        "id": make_id("chatcmpl"),
        "object": "chat.completion",
        "created": now_ts(),
        "model": model,
        "choices": choices,
        "usage": usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }

def tool_call_message(tool_calls):
    calls = []
    for tc in tool_calls:
        calls.append({
            "id": f"call_{uuid.uuid4().hex[:24]}",
            "type": "function",
            "function": {
                "name": tc["name"],
                "arguments": json.dumps(tc["arguments"]),
            },
        })
    return calls

# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------
class BrainHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            json_response(self, 200, {
                "service": "brain-rest-api",
                "version": "1.0.0",
                "format": "openai",
                "base_url": "https://thebrain.137-184-23-228.sslip.io/brain-api",
                "endpoints": {
                    "models": "/brain-api/v1/models",
                    "chat": "/brain-api/v1/chat/completions",
                    "tools": "/brain-api/v1/tools",
                    "auth_keys": "/brain-api/v1/auth/keys",
                    "mcp": "/brain-api/mcp",
                    "health": "/brain-api/v1/health",
                },
            })
            return

        if path == "/v1/health":
            json_response(self, 200, {
                "status": "healthy",
                "service": "brain-rest-api",
                "format": "openai",
                "tools": len(TOOLS),
                "models": len(BRAIN_MODELS),
            })
            return

        if path == "/v1/models":
            if not is_authenticated(self):
                json_response(self, 401, {"error": {"message": "Missing or invalid API key", "type": "auth_error", "code": 401}})
                return
            json_response(self, 200, models_list_response())
            return

        if path == "/v1/tools":
            if not is_authenticated(self):
                json_response(self, 401, {"error": {"message": "Missing or invalid API key", "type": "auth_error", "code": 401}})
                return
            json_response(self, 200, {"object": "list", "data": TOOLS})
            return

        if path == "/v1/resources":
            if not is_authenticated(self):
                json_response(self, 401, {"error": {"message": "Missing or invalid API key", "type": "auth_error", "code": 401}})
                return
            json_response(self, 200, {
                "object": "list",
                "data": [
                    {"uri": "app://models/registry", "name": "Model Registry", "description": "List of all available models with capabilities", "mimeType": "application/json"},
                    {"uri": "app://tools/registry", "name": "Tool Registry", "description": "List of all available tools with input schemas", "mimeType": "application/json"},
                    {"uri": "app://auth/keys", "name": "API Keys", "description": "Manage API keys for the Brain REST API", "mimeType": "application/json"},
                ],
            })
            return

        if path == "/v1/prompts":
            if not is_authenticated(self):
                json_response(self, 401, {"error": {"message": "Missing or invalid API key", "type": "auth_error", "code": 401}})
                return
            json_response(self, 200, {
                "object": "list",
                "data": [
                    {"name": "code_refactor_skill", "description": "Standardized skill to analyze and optimize code blocks",
                     "arguments": [{"name": "snippet", "description": "Code snippet to refactor", "required": True}]},
                    {"name": "pentest_workflow", "description": "Standardized pentest workflow using ISIS tools",
                     "arguments": [{"name": "target", "description": "Target to pentest", "required": True}]},
                ],
            })
            return

        if path == "/mcp":
            json_response(self, 200, {
                "jsonrpc": "2.0",
                "method": "mcp.info",
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": True},
                        "resources": {"listChanged": True},
                        "prompts": {"listChanged": True},
                    },
                    "serverInfo": {"name": "brain-rest-api", "version": "1.0.0"},
                },
                "id": 0,
            })
            return

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = read_body(self)
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            json_response(self, 400, {"error": {"message": "Invalid JSON body", "type": "bad_request_error", "code": 400}})
            return

        if path == "/v1/auth/keys":
            new_key = secrets.token_urlsafe(32)
            key_name = data.get("name", f"key-{int(time.time())}")
            API_KEYS[new_key] = {"created": int(time.time()), "name": key_name}
            json_response(self, 200, {
                "api_key": new_key,
                "name": key_name,
                "created": int(time.time()),
                "base_url": "https://thebrain.137-184-23-228.sslip.io/brain-api",
                "usage": "Authorization: Bearer <api_key>",
                "note": "Save this key now — it will not be shown again.",
            })
            return

        if not is_authenticated(self):
            json_response(self, 401, {"error": {"message": "Missing or invalid API key", "type": "auth_error", "code": 401}})
            return

        if path == "/v1/chat/completions":
            self.handle_chat_completions(data)
        elif path == "/v1/tools/call":
            self.handle_tool_call(data)
        elif path == "/mcp":
            self.handle_mcp(data)
    def handle_chat_completions(self, data):
        model = data.get("model", "isis-trained")
        messages = data.get("messages", [])
        tools = data.get("tools", None)
        stream = data.get("stream", False)

        if stream:
            self._stream_chat_completions(model, messages, tools)
            return

        available_tools = tools if tools is not None else TOOLS

        user_message = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_message = m.get("content", "")
                break

        selected_tools = self._select_tools(user_message, available_tools)

        if not selected_tools:
            content = self._generate_text_response(model, messages, user_message)
            choices = [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }]
            json_response(self, 200, chat_completions_response(model, choices))
            return

        tool_calls_out = []
        tool_messages = []
        for tc in selected_tools:
            tool_call_id = f"call_{uuid.uuid4().hex[:24]}"
            result = execute_tool(tc["name"], tc["arguments"])
            tool_calls_out.append({
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": json.dumps(tc["arguments"]),
                },
            })
            tool_messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": tc["name"],
                "content": json.dumps(result),
            })

        assistant_msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls_out,
        }

        summary = self._summarize_results(tool_messages)
        choices = [
            {
                "index": 0,
                "message": assistant_msg,
                "finish_reason": "tool_calls",
            },
            {
                "index": 1,
                "message": {"role": "assistant", "content": summary},
                "finish_reason": "stop",
            },
        ]

        json_response(self, 200, chat_completions_response(model, choices))

    def _stream_chat_completions(self, model, messages, tools):
        available_tools = tools if tools is not None else TOOLS

        user_message = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_message = m.get("content", "")
                break

        selected_tools = self._select_tools(user_message, available_tools)

        chunk_id = make_id("chatcmpl")
        created = now_ts()

        def sse_chunk(obj):
            data_str = "data: " + json.dumps(obj) + "\n\n"
            self.wfile.write(data_str.encode("utf-8"))

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

        sse_chunk({
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        })

        if selected_tools:
            for tc in selected_tools:
                sse_chunk({
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {
                        "tool_calls": [{
                            "index": 0,
                            "id": f"call_{uuid.uuid4().hex[:24]}",
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": ""},
                        }]
                    }, "finish_reason": None}],
                })

        sse_chunk({
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        })
        self.wfile.write(b"data: [DONE]\n\n")

    def _select_tools(self, user_message, available_tools):
        msg = user_message.lower()
        selected = []
        for tool in available_tools:
            name = tool["function"]["name"]
            desc = tool["function"]["description"].lower()
            if name in msg or any(k in msg for k in desc.split()[:3]):
                selected.append({"name": name, "arguments": {}})
        return selected[:3]

    def _generate_text_response(self, model, messages, user_message):
        return f"I received your message: '{user_message}'. I'm the {model} model running on the Brain REST API at https://thebrain.137-184-23-228.sslip.io/brain-api. How can I help you?"

    def _summarize_results(self, tool_messages):
        parts = []
        for tm in tool_messages:
            parts.append(f"Tool `{tm['name']}` executed: {tm['content'][:200]}")
        return "Executed tools: " + "; ".join(parts) if parts else "No tools executed."

    def handle_tool_call(self, data):
        name = data.get("name", "")
        arguments = data.get("arguments", {})
        result = execute_tool(name, arguments)
        json_response(self, 200, {
            "jsonrpc": "2.0",
            "result": result,
            "id": data.get("id", 1),
        })

    def handle_mcp(self, data):
        method = data.get("method", "")
        params = data.get("params", {})
        req_id = data.get("id", 1)

        if method == "initialize":
            json_response(self, 200, {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": True},
                        "resources": {"listChanged": True},
                        "prompts": {"listChanged": True},
                    },
                    "serverInfo": {"name": "brain-rest-api", "version": "1.0.0"},
                },
            })
        elif method == "tools/list":
            json_response(self, 200, {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": [t["function"] for t in TOOLS]},
            })
        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            result = execute_tool(tool_name, tool_args)
            json_response(self, 200, {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": result,
            })
        elif method == "resources/list":
            json_response(self, 200, {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "resources": [
                        {"uri": "app://models/registry", "name": "Model Registry",
                         "description": "List of all available models with capabilities",
                         "mimeType": "application/json"},
                        {"uri": "app://tools/registry", "name": "Tool Registry",
                         "description": "List of all available tools with input schemas",
                         "mimeType": "application/json"},
                        {"uri": "app://auth/keys", "name": "API Keys",
                         "description": "Manage API keys for the Brain REST API",
                         "mimeType": "application/json"},
                    ],
                },
            })
        elif method == "resources/read":
            uri = params.get("uri", "")
            if uri == "app://models/registry":
                content = json.dumps(models_list_response(), indent=2)
            elif uri == "app://tools/registry":
                content = json.dumps({"object": "list", "data": TOOLS}, indent=2)
            elif uri == "app://auth/keys":
                content = json.dumps({"keys": list(API_KEYS.keys())}, indent=2)
            else:
                content = json.dumps({"error": "unknown resource"})
            json_response(self, 200, {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"contents": [{"uri": uri, "mimeType": "application/json", "text": content}]},
            })
        elif method == "prompts/list":
            json_response(self, 200, {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "prompts": [
                        {"name": "code_refactor_skill", "description": "Standardized skill to analyze and optimize code blocks",
                         "arguments": [{"name": "snippet", "description": "Code snippet to refactor", "required": True}]},
                        {"name": "pentest_workflow", "description": "Standardized pentest workflow using ISIS tools",
                         "arguments": [{"name": "target", "description": "Target to pentest", "required": True}]},
                    ],
                },
            })
        else:
            json_response(self, 200, {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            })

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("Brain REST API — OpenAI-compatible endpoint")
    print("=" * 60)
    print(f"Server: {BRAIN_SERVER_NAME}")
    print(f"Base URL: https://thebrain.137-184-23-228.sslip.io/brain-api")
    print(f"Local port: 8099")
    print(f"Models: {len(BRAIN_MODELS)} (including cloud models)")
    print(f"Tools: {len(TOOLS)}")
    print(f"API Key: {PRIMARY_API_KEY}")
    print(f"ISIS server: {ISIS_BASE_URL} (native, no SSH)")
    print(f"Billion-context: port {BILLION_CTX_PORT}")
    print("=" * 60)
    server = HTTPServer(("0.0.0.0", 8099), BrainHandler)
    print("Brain REST API running on port 8099")
    server.serve_forever()

if __name__ == "__main__":
    main()
