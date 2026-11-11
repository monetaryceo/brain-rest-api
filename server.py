#!/usr/bin/env python3
"""
Brain REST API — OpenAI-compatible endpoint for all brain tools, skills, and models.

Implements the OpenAI Chat Completions API format (exact field names/types):
  GET  /v1/models        -> list of models { object: "list", data: [...] }
  POST /v1/chat/completions -> { id, object: "chat.completion", created, model,
                                 choices: [{ index, message, finish_reason }],
                                 usage: { prompt_tokens, completion_tokens, total_tokens } }

Tool calling follows the OpenAI format:
  Request  tools: [{ type: "function", function: { name, description, parameters } }]
  Response tool_calls: [{ id, type: "function", function: { name, arguments: "<JSON string>" } }]

Exposes:
  - Brain MCP tools (agent-list, agent-run, agent-install, agent-build, agent-doctor,
    context7-search, rea-analyze) via bin/agent-cli.js
  - All 12 native skills (ghostman, ctx7, context7-mcp, rea, agent-browser, skills,
    dsh, deer-flow, herdr, agent-desktop, craft-anything, replica-skill)
  - ISIS pentest tools (nuclei_scan, finish_scan, web_search, spawn_sandbox, pentest,
    tmux, swarmchat, herdr_swarm, infinity_swarm, deer_flow, capabilities, health)
  - All brain models (lfm3, deepseek-r1, qwen, hope, aira, aether, jev, laya, wan,
    isis-trained, etc.)

No external dependencies — uses Python stdlib only.
"""

import json
import os
import sys
import time
import uuid
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
WORKSPACE = r"C:\Users\ADMIN\.cline\data\workspaces\chat"
AGENT_TOOLCHAIN = os.path.join(WORKSPACE, "agent-toolchain")
AGENT_CLI = os.path.join(AGENT_TOOLCHAIN, "bin", "agent-cli.js")
BRAIN_MCP = os.path.join(AGENT_TOOLCHAIN, "brain", "mcp-server.js")
BRAIN_MANIFEST = os.path.join(AGENT_TOOLCHAIN, "brain", "manifest.json")
BRAIN_SKILLS_INDEX = os.path.join(AGENT_TOOLCHAIN, "brain", "skills", "index.json")

# Remote ISIS server (brain-agent)
ISIS_SSH_HOST = "brain-agent@137.184.23.228"
ISIS_SSH_KEY = r"C:\Users\ADMIN\.ssh\brain_agents_key"
ISIS_BASE_URL = "http://137.184.23.228:8088"

# ---------------------------------------------------------------------------
# Billion-context configuration (context-compression proxy)
# Installed at: C:\Users\ADMIN\.cline\data\workspaces\chat\billion-context\
# Proxy listens on port 8787 by default, sits between agents and model APIs
# ---------------------------------------------------------------------------
BILLION_CTX_DIR = os.path.join(WORKSPACE, "billion-context")
BILLION_CTX_BIN = os.path.join(BILLION_CTX_DIR, "bin", "bili.cjs")
BILLION_CTX_DIST = os.path.join(BILLION_CTX_DIR, "dist", "index.js")
BILLION_CTX_PORT = int(os.environ.get("BILI_PORT", "8787"))
BILLION_CTX_HOST = os.environ.get("BILI_HOST", "127.0.0.1")
BILLION_CTX_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "billion-context")
BILLION_CTX_CONFIG_FILE = os.path.join(BILLION_CTX_CONFIG_DIR, "billion-context.json")
_bili_proc = None  # holds the running billion-context proxy subprocess

# ---------------------------------------------------------------------------
# Model registry (from /opt/the-brain/short_names.json on brain-agent)
# Each model: { id, object, created, owned_by, ... }
# ---------------------------------------------------------------------------
BRAIN_MODELS = [
    {
        "id": "lfm3-1.7b-uncensored",
        "object": "model",
        "created": int(time.time()),
        "owned_by": "brain",
        "base": "LFM3-1.7B-Uncensored",
        "role": "primary",
        "port": 8081,
        "file": "lfm3-1.7b-uncensored-q4_k_m.gguf",
        "capabilities": ["text", "tools", "chat"],
        "permission": [],
    },
    {
        "id": "deepseek-r1-llama-8b-abliterated",
        "object": "model",
        "created": int(time.time()),
        "owned_by": "brain",
        "base": "DeepSeek-R1-Llama-8B-Abliterated",
        "role": "reasoning",
        "port": 8086,
        "file": "deepseek-r1-llama-8b-abliterated-q4_k_m.gguf",
        "capabilities": ["text", "tools", "reasoning", "chat"],
        "permission": [],
    },
    {
        "id": "qwen2.5-moe-2x1.5b-uncensored",
        "object": "model",
        "created": int(time.time()),
        "owned_by": "brain",
        "base": "Qwen2.5-MoE-2x1.5B-Uncensored",
        "role": "moe",
        "port": 8092,
        "file": "qwen2.5-moe-2x1.5b-uncensored-q4_k_m.gguf",
        "capabilities": ["text", "tools", "moe", "chat"],
        "permission": [],
    },
    {
        "id": "hope",
        "object": "model",
        "created": int(time.time()),
        "owned_by": "brain",
        "base": "HOPE",
        "role": "quant",
        "port": 8084,
        "file": "hope-q4_k_m.gguf",
        "capabilities": ["text", "tools", "quant", "chat"],
        "permission": [],
    },
    {
        "id": "aira",
        "object": "model",
        "created": int(time.time()),
        "owned_by": "brain",
        "base": "AIRA",
        "role": "risk",
        "port": 8083,
        "file": "aira-q4_k_m.gguf",
        "capabilities": ["text", "tools", "risk", "chat"],
        "permission": [],
    },
    {
        "id": "aether-trading",
        "object": "model",
        "created": int(time.time()),
        "owned_by": "brain",
        "base": "Aether-Trading",
        "role": "trading",
        "port": 8081,
        "file": "aether-trading-q4_k_m.gguf",
        "capabilities": ["text", "tools", "trading", "chat"],
        "permission": [],
    },
    {
        "id": "deepseek-r1-qwen-7b-abliterated",
        "object": "model",
        "created": int(time.time()),
        "owned_by": "brain",
        "base": "DeepSeek-R1-Qwen-7B-Abliterated",
        "role": "reasoning-alt",
        "port": 8087,
        "file": "deepseek-r1-qwen-7b-abliterated-q4_k_m.gguf",
        "capabilities": ["text", "tools", "reasoning", "chat"],
        "permission": [],
    },
    {
        "id": "wan2.2-ti2v-5b",
        "object": "model",
        "created": int(time.time()),
        "owned_by": "brain",
        "base": "Wan2.2-TI2V-5B",
        "role": "video",
        "port": 8088,
        "file": "wan2.2-ti2v-5b-q4_k_m.gguf",
        "backend": "diffusers",
        "capabilities": ["video", "image_generation", "text"],
        "permission": [],
    },
    {
        "id": "laya-multilingual",
        "object": "model",
        "created": int(time.time()),
        "owned_by": "brain",
        "base": "Laya-Multilingual",
        "role": "multilingual",
        "port": 8089,
        "file": "laya-multilingual-f16.gguf",
        "backend": "transformers",
        "capabilities": ["text", "tools", "multilingual", "chat"],
        "permission": [],
    },
    {
        "id": "jev-style-0.8b-decision-v3",
        "object": "model",
        "created": int(time.time()),
        "owned_by": "brain",
        "base": "Jev-Style-0.8B-Decision-v3",
        "role": "decision",
        "port": 8090,
        "file": "jev-style-0.8b-decision-v3-q4_k_m.gguf",
        "capabilities": ["text", "tools", "decision", "chat"],
        "permission": [],
    },
    {
        "id": "jev-style-2b-decision-v3",
        "object": "model",
        "created": int(time.time()),
        "owned_by": "brain",
        "base": "Jev-Style-2B-Decision-v3",
        "role": "decision",
        "port": 8091,
        "file": "jev-style-2b-decision-v3-q4_k_m.gguf",
        "capabilities": ["text", "tools", "decision", "chat"],
        "permission": [],
    },
    {
        "id": "isis-trained",
        "object": "model",
        "created": int(time.time()),
        "owned_by": "isis",
        "base": "needle3+lfm3-omni",
        "role": "pentest",
        "path": "/opt/the-brain/models/isis-trained/isis.safetensors",
        "uncensored": True,
        "capabilities": [
            "web_search", "docker_sandbox", "pentest", "uncensored_response",
            "strix_recon", "nuclei_vuln_scan", "herdr_bot_swarm", "infinity_swarm",
            "tmux_session", "deer_flow_workflow", "swarmchat_communication",
            "abliteration", "quantum_math", "qlora_adapter", "openai_compatible_api",
        ],
        "permission": [],
    },
    {
        "id": "llama3.2:1b",
        "object": "model",
        "created": int(time.time()),
        "owned_by": "ollama",
        "base": "llama3.2",
        "role": "chat",
        "endpoint": "http://137.184.23.228:11434",
        "capabilities": ["text", "tools", "chat"],
        "permission": [],
    },
    {
        "id": "lfm3-omni",
        "object": "model",
        "created": int(time.time()),
        "owned_by": "liquidai",
        "base": "LFM3-Omni-2B",
        "role": "multimodal",
        "capabilities": ["text", "vision", "audio", "tools", "any_to_any", "chat"],
        "context_length": 32768,
        "modality": "any-to-any",
        "permission": [],
    },
]

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
    {
        "type": "function",
        "function": {
            "name": "nuclei_scan",
            "description": "Run a nuclei vulnerability scan on a target URL (ISIS pentest server).",
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
            "description": "Perform a web search via the ISIS server.",
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
                "properties": {
                    "image": {"type": "string", "default": "brain-math-sandbox:latest", "description": "Docker image to spawn"},
                },
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
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID to check"},
                },
                "additionalProperties": False,
            },
        },
    },
]

TOOL_NAMES = {t["function"]["name"] for t in TOOLS}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def now_ts():
    return int(time.time())

def make_id(prefix="cmpl"):
    return f"{prefix}-{uuid.uuid4().hex[:24]}"

def json_response(handler, code, body, content_type="application/json"):
    data = json.dumps(body).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    # CORS headers — required for PocketPal, browser clients, and all apps
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
    handler.end_headers()
    handler.wfile.write(data)

def read_body(handler):
    length = int(handler.headers.get("Content-Length", 0))
    if length == 0:
        return b""
    return handler.rfile.read(length)

def run_agent_cli(*args):
    """Run bin/agent-cli.js with the given args; return (code, stdout, stderr)."""
    cmd = ["node", AGENT_CLI] + list(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "Command timed out after 120s"
    except Exception as e:
        return 1, "", str(e)

def ssh_isis(path, method="POST", payload=None):
    """Call the remote ISIS server via SSH curl (avoids opening a port locally)."""
    url = f"{ISIS_BASE_URL}{path}"
    if method == "GET":
        cmd = [
            "ssh", "-i", ISIS_SSH_KEY, "-o", "IdentitiesOnly=yes",
            "-o", "StrictHostKeyChecking=no", ISIS_SSH_HOST,
            f"curl -s {url}",
        ]
    else:
        data = json.dumps(payload or {})
        escaped = data.replace("'", "'\\''")
        cmd = [
            "ssh", "-i", ISIS_SSH_KEY, "-o", "IdentitiesOnly=yes",
            "-o", "StrictHostKeyChecking=no", ISIS_SSH_HOST,
            f"curl -s -X POST -H 'Content-Type: application/json' -d '{escaped}' {url}",
        ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return {"error": f"ssh failed: {result.stderr.strip()}"}
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"error": f"invalid json: {result.stdout[:500]}", "raw": result.stdout}
    except subprocess.TimeoutExpired:
        return {"error": "ISIS request timed out"}
    except Exception as e:
        return {"error": str(e)}

# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------
def execute_tool(name, arguments):
    """Execute a registered tool by name with arguments dict. Returns result dict."""
    # Brain MCP tools via agent-cli
    if name == "agent_list":
        code, out, err = run_agent_cli("list")
        return {"code": code, "stdout": out, "stderr": err}
    if name == "agent_run":
        tool = arguments.get("tool")
        args = arguments.get("args", [])
        code, out, err = run_agent_cli(tool, *args)
        return {"code": code, "stdout": out, "stderr": err}
    if name == "agent_install":
        tool = arguments.get("tool")
        code, out, err = run_agent_cli("install", tool)
        return {"code": code, "stdout": out, "stderr": err}
    if name == "agent_build":
        tool = arguments.get("tool")
        code, out, err = run_agent_cli("build", tool)
        return {"code": code, "stdout": out, "stderr": err}
    if name == "agent_doctor":
        code, out, err = run_agent_cli("doctor")
        return {"code": code, "stdout": out, "stderr": err}
    if name == "context7_search":
        cmd = ["context7-search"]
        if arguments.get("library_name"):
            cmd += ["--library", arguments["library_name"]]
        code, out, err = run_agent_cli(*cmd)
        return {"code": code, "stdout": out, "stderr": err}
    if name == "rea_analyze":
        target = arguments.get("target")
        code, out, err = run_agent_cli("rea", "analyze", target)
        return {"code": code, "stdout": out, "stderr": err}

    # ISIS tools via remote SSH
    if name == "nuclei_scan":
        return ssh_isis("/nuclei_scan", "POST", {
            "target": arguments.get("target"),
            "severity": arguments.get("severity", "critical,high,medium"),
        })
    if name == "finish_scan":
        return ssh_isis("/pentest", "POST", {
            "target": arguments.get("target"),
            "tools": ["nuclei"],
            "_finish": True,
            "findings": arguments.get("findings", []),
            "findings_count": arguments.get("findings_count", 0),
            "status": arguments.get("status", "completed"),
        })
    if name == "web_search":
        return ssh_isis("/web_search", "POST", {"query": arguments.get("query", "")})
    if name == "spawn_sandbox":
        return ssh_isis("/spawn_sandbox", "POST", {
            "image": arguments.get("image", "brain-math-sandbox:latest"),
        })
    if name == "pentest":
        return ssh_isis("/pentest", "POST", {
            "target": arguments.get("target"),
            "tools": arguments.get("tools", ["strix", "nuclei"]),
        })
    if name == "tmux_session":
        return ssh_isis("/tmux", "POST", {
            "session": arguments.get("session", "isis-session"),
            "command": arguments.get("command", "echo ISIS"),
        })
    if name == "swarmchat":
        return ssh_isis("/swarmchat", "POST", {
            "message": arguments.get("message", ""),
            "channel": arguments.get("channel", "isis"),
        })
    if name == "herdr_swarm":
        return ssh_isis("/herdr", "POST", {
            "task": arguments.get("task", ""),
            "num_bots": arguments.get("num_bots", 5),
        })
    if name == "infinity_swarm":
        return ssh_isis("/infinity", "POST", {"task": arguments.get("task", "")})
    if name == "deer_flow":
        return ssh_isis("/deer_flow", "POST", {
            "workflow": arguments.get("workflow", "default"),
            "steps": arguments.get("steps", []),
        })
    if name == "capabilities":
        return ssh_isis("/capabilities", "GET")
    if name == "health":
        return ssh_isis("/health", "GET")

    # ---- Billion-context tools ----
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

    return {"error": f"unknown tool: {name}"}


# ---------------------------------------------------------------------------
# Billion-context proxy management
# ---------------------------------------------------------------------------
def start_bili_proxy(port, host):
    """Start the billion-context proxy as a subprocess."""
    global _bili_proc
    if _bili_proc is not None and _bili_proc.poll() is None:
        return {"status": "already_running", "port": port, "pid": _bili_proc.pid}

    # Ensure config dir exists
    os.makedirs(BILLION_CTX_CONFIG_DIR, exist_ok=True)

    # Seed config if missing
    if not os.path.exists(BILLION_CTX_CONFIG_FILE):
        config = {
            "port": port,
            "host": host,
            "providers": {},
        }
        try:
            with open(BILLION_CTX_CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            return {"error": f"failed to write config: {e}"}

    # Start the proxy
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
    """Check billion-context proxy status."""
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
    """Make an HTTP request to the billion-context proxy."""
    import urllib.request
    import urllib.error
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
    """Compress a message range via billion-context."""
    return _bili_request("POST", "/compress", {
        "session_id": session_id, "start": start, "end": end,
    })


def bili_decompress_range(session_id, ref_id):
    """Decompress a message range via billion-context."""
    return _bili_request("POST", "/decompress", {
        "session_id": session_id, "ref_id": ref_id,
    })


def bili_search(session_id, query):
    """Search context via billion-context."""
    return _bili_request("POST", "/search_context", {
        "session_id": session_id, "query": query,
    })


def bili_acp_status(session_id=""):
    """Get ACP status via billion-context."""
    path = "/acp_status" + (f"?session_id={session_id}" if session_id else "")
    return _bili_request("GET", path)


# ---------------------------------------------------------------------------
# OpenAI-format responses
# ---------------------------------------------------------------------------
def models_list_response():
    return {
        "object": "list",
        "data": BRAIN_MODELS,
    }

def chat_completions_response(model, choices, usage=None):
    return {
        "id": make_id("chatcmpl"),
        "object": "chat.completion",
        "created": now_ts(),
        "model": model,
        "choices": choices,
        "usage": usage or {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
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
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": calls,
    }

def tool_result_message(tool_call_id, name, result):
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": name,
        "content": json.dumps(result),
    }

# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------
class BrainHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/v1/models":
            json_response(self, 200, models_list_response())
        elif path == "/v1/tools":
            json_response(self, 200, {
                "object": "list",
                "data": TOOLS,
            })
        elif path == "/health":
            json_response(self, 200, {
                "status": "healthy",
                "service": "brain-rest-api",
                "format": "openai",
                "tools": len(TOOLS),
                "models": len(BRAIN_MODELS),
                "billion_context": check_bili_status(),
            })
        elif path == "/v1/health":
            json_response(self, 200, {
                "status": "healthy",
                "service": "brain-rest-api",
                "format": "openai",
                "tools": len(TOOLS),
                "models": len(BRAIN_MODELS),
                "billion_context": check_bili_status(),
            })
        elif path == "/v1/resources":
            json_response(self, 200, {
                "object": "list",
                "data": [
                    {
                        "uri": "app://workspace/current-state",
                        "name": "Current Workspace State",
                        "description": "Exposes active UI state and component handles",
                        "mimeType": "application/json",
                    },
                    {
                        "uri": "app://models/registry",
                        "name": "Model Registry",
                        "description": "List of all available models with capabilities",
                        "mimeType": "application/json",
                    },
                    {
                        "uri": "app://tools/registry",
                        "name": "Tool Registry",
                        "description": "List of all available tools with input schemas",
                        "mimeType": "application/json",
                    },
                ],
            })
        elif path == "/v1/prompts":
            json_response(self, 200, {
                "object": "list",
                "data": [
                    {
                        "name": "code_refactor_skill",
                        "description": "Standardized skill to analyze and optimize code blocks",
                        "arguments": [
                            {
                                "name": "snippet",
                                "description": "Code snippet to refactor",
                                "required": True,
                            }
                        ],
                    },
                    {
                        "name": "pentest_workflow",
                        "description": "Standardized pentest workflow using ISIS tools",
                        "arguments": [
                            {
                                "name": "target",
                                "description": "Target to pentest",
                                "required": True,
                            }
                        ],
                    },
                ],
            })
        elif path == "/mcp":
            # MCP over HTTP GET — return capabilities info
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
                    "serverInfo": {
                        "name": "brain-rest-api",
                        "version": "1.0.0",
                    },
                },
                "id": 0,
            })
        else:
            json_response(self, 404, {
                "error": {
                    "message": f"Unknown endpoint: {path}",
                    "type": "not_found_error",
                    "code": 404,
                }
            })

    def do_OPTIONS(self):
        """CORS preflight handler for all apps (PocketPal, browsers, etc.)."""
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
            json_response(self, 400, {
                "error": {
                    "message": "Invalid JSON body",
                    "type": "bad_request_error",
                    "code": 400,
                }
            })
            return

        if path == "/v1/chat/completions":
            self.handle_chat_completions(data)
        elif path == "/v1/tools/call":
            self.handle_tool_call(data)
        elif path == "/mcp":
            self.handle_mcp(data)
        elif path == "/v1/embeddings":
            json_response(self, 400, {
                "error": {
                    "message": "Embeddings endpoint not implemented",
                    "type": "not_implemented_error",
                    "code": 400,
                }
            })
        else:
            json_response(self, 404, {
                "error": {
                    "message": f"Unknown endpoint: {path}",
                    "type": "not_found_error",
                    "code": 404,
                }
            })

    # ---- chat/completions ----
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

    # ---- chat/completions streaming (SSE) ----
    def _stream_chat_completions(self, model, messages, tools):
        """Stream chat completion as Server-Sent Events (text/event-stream)."""
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
            return f"data: {json.dumps(obj)}\n\n"

        # Send initial role chunk
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.end_headers()

        role_chunk = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        }
        self.wfile.write(sse_chunk(role_chunk).encode("utf-8"))

        if not selected_tools:
            content = self._generate_text_response(model, messages, user_message)
            content_chunk = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
            }
            self.wfile.write(sse_chunk(content_chunk).encode("utf-8"))
            stop_chunk = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            self.wfile.write(sse_chunk(stop_chunk).encode("utf-8"))
        else:
            tool_calls_out = []
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
            tool_chunk = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"tool_calls": tool_calls_out}, "finish_reason": None}],
            }
            self.wfile.write(sse_chunk(tool_chunk).encode("utf-8"))
            stop_chunk = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
            }
            self.wfile.write(sse_chunk(stop_chunk).encode("utf-8"))

        self.wfile.write(b"data: [DONE]\n\n")

    # ---- MCP JSON-RPC 2.0 (universal for ChatGPT, Grok, Manus, Claude, Cline, Copilot, Codex) ----
    def handle_mcp(self, data):
        """Handle MCP JSON-RPC 2.0 requests."""
        method = data.get("method", "")
        params = data.get("params", {})
        req_id = data.get("id", 0)

        if method == "tools/list":
            tools_out = []
            for t in TOOLS:
                fn = t["function"]
                tools_out.append({
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "inputSchema": fn.get("parameters", {"type": "object", "properties": {}}),
                })
            json_response(self, 200, {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": tools_out},
            })

        elif method == "tools/call":
            name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = execute_tool(name, arguments)
            json_response(self, 200, {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {"type": "text", "text": json.dumps(result)}
                    ],
                    "isError": False,
                },
            })

        elif method == "resources/list":
            json_response(self, 200, {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "resources": [
                        {
                            "uri": "app://workspace/current-state",
                            "name": "Current Workspace State",
                            "description": "Exposes active UI state and component handles",
                            "mimeType": "application/json",
                        },
                        {
                            "uri": "app://models/registry",
                            "name": "Model Registry",
                            "description": "List of all available models with capabilities",
                            "mimeType": "application/json",
                        },
                        {
                            "uri": "app://tools/registry",
                            "name": "Tool Registry",
                            "description": "List of all available tools with input schemas",
                            "mimeType": "application/json",
                        },
                    ],
                },
            })

        elif method == "prompts/list":
            json_response(self, 200, {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "prompts": [
                        {
                            "name": "code_refactor_skill",
                            "description": "Standardized skill to analyze and optimize code blocks",
                            "arguments": [
                                {
                                    "name": "snippet",
                                    "description": "Code snippet to refactor",
                                    "required": True,
                                }
                            ],
                        },
                        {
                            "name": "pentest_workflow",
                            "description": "Standardized pentest workflow using ISIS tools",
                            "arguments": [
                                {
                                    "name": "target",
                                    "description": "Target to pentest",
                                    "required": True,
                                }
                            ],
                        },
                    ],
                },
            })

        else:
            json_response(self, 400, {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}",
                },
            })

    # ---- tools/call (direct execution) ----
    def handle_tool_call(self, data):
        name = data.get("name")
        arguments = data.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        result = execute_tool(name, arguments)
        json_response(self, 200, {
            "name": name,
            "result": result,
        })

    # ---- tool selection heuristic ----
    def _select_tools(self, message, available_tools):
        msg = message.lower()
        selected = []
        keyword_map = [
            (["agent", "list", "tool", "status"], "agent_list"),
            (["run", "execute", "cli", "command"], "agent_run"),
            (["install", "dependency", "deps"], "agent_install"),
            (["build", "compile"], "agent_build"),
            (["doctor", "health", "runtime", "check"], "agent_doctor"),
            (["context7", "documentation", "docs", "library"], "context7_search"),
            (["rea", "reverse", "analyze", "binary"], "rea_analyze"),
            (["nuclei", "vulnerability", "scan", "cve", "ssrf"], "nuclei_scan"),
            (["finish", "scan_complete", "pentest_done"], "finish_scan"),
            (["web_search", "search", "search web"], "web_search"),
            (["sandbox", "docker", "spawn"], "spawn_sandbox"),
            (["pentest", "strix", "penetration"], "pentest"),
            (["tmux", "session"], "tmux_session"),
            (["swarmchat", "swarm chat"], "swarmchat"),
            (["herdr", "swarm", "bots"], "herdr_swarm"),
            (["infinity", "infinite"], "infinity_swarm"),
            (["deer", "flow", "workflow"], "deer_flow"),
            (["capabilities", "what can"], "capabilities"),
            (["health", "is alive", "ping"], "health"),
            (["billion", "context", "compress", "compression", "bili", "acp"], "bili_start"),
            (["bili", "status", "proxy"], "bili_status"),
            (["compress", "compression", "fold", "session"], "bili_compress"),
            (["decompress", "unfold", "restore"], "bili_decompress"),
            (["search_context", "search context", "search compressed"], "bili_search_context"),
            (["acp_status", "context usage", "context overview"], "bili_acp_status"),
        ]
        for keywords, tool_name in keyword_map:
            if not any(t["function"]["name"] == tool_name for t in available_tools):
                continue
            if any(k in msg for k in keywords):
                args = self._default_args(tool_name, msg)
                selected.append({"name": tool_name, "arguments": args})
        seen = set()
        unique = []
        for s in selected:
            if s["name"] not in seen:
                seen.add(s["name"])
                unique.append(s)
        return unique

    def _default_args(self, tool_name, msg):
        defaults = {
            "agent_list": {},
            "agent_run": {"tool": "", "args": []},
            "agent_install": {"tool": ""},
            "agent_build": {"tool": ""},
            "agent_doctor": {},
            "context7_search": {"query": msg},
            "rea_analyze": {"target": ""},
            "nuclei_scan": {"target": "", "severity": "critical,high,medium"},
            "finish_scan": {"findings": [], "findings_count": 0, "target": "", "status": "completed"},
            "web_search": {"query": msg},
            "spawn_sandbox": {"image": "brain-math-sandbox:latest"},
            "pentest": {"target": "", "tools": ["strix", "nuclei"]},
            "tmux_session": {"session": "isis-session", "command": "echo ISIS"},
            "swarmchat": {"message": msg, "channel": "isis"},
            "herdr_swarm": {"task": msg, "num_bots": 5},
            "infinity_swarm": {"task": msg},
            "deer_flow": {"workflow": "default", "steps": []},
            "capabilities": {},
            "health": {},
            "bili_start": {"port": 8787, "host": "127.0.0.1"},
            "bili_status": {},
            "bili_compress": {"session_id": "", "start": 0, "end": 0},
            "bili_decompress": {"session_id": "", "ref_id": ""},
            "bili_search_context": {"session_id": "", "query": ""},
            "bili_acp_status": {"session_id": ""},
        }
        return defaults.get(tool_name, {})

    def _generate_text_response(self, model, messages, user_message):
        if model == "isis-trained" or any(m.get("id") == "isis-trained" for m in BRAIN_MODELS):
            result = ssh_isis("/generate", "POST", {"prompt": user_message})
            if "response" in result:
                return result["response"]
        return (
            f"I received your message: '{user_message}'. "
            f"I'm the Brain REST API (OpenAI-compatible) with {len(TOOLS)} tools and "
            f"{len(BRAIN_MODELS)} models available. "
            f"Tell me which tool or model you'd like to use, e.g. 'run a nuclei scan on example.com' "
            f"or 'list all models'."
        )

    def _summarize_results(self, tool_messages):
        parts = []
        for tm in tool_messages:
            name = tm["name"]
            parts.append(f"Tool `{name}` completed.")
        return "Executed " + ", ".join(parts) + "."


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", "8099"))
    server = HTTPServer((host, port), BrainHandler)
    print("=" * 60)
    print("Brain REST API — OpenAI-compatible")
    print("=" * 60)
    print(f"Host: {host}:{port}")
    print(f"Format: OpenAI Chat Completions API")
    print(f"Endpoints:")
    print(f"  GET  http://{host}:{port}/v1/models")
    print(f"  POST http://{host}:{port}/v1/chat/completions")
    print(f"  POST http://{host}:{port}/v1/tools/call")
    print(f"  GET  http://{host}:{port}/v1/tools")
    print(f"Tools: {len(TOOLS)}")
    for t in TOOLS:
        print(f"  - {t['function']['name']}: {t['function']['description'][:60]}")
    print(f"Models: {len(BRAIN_MODELS)}")
    for m in BRAIN_MODELS:
        print(f"  - {m['id']} ({m.get('role', '?')})")
    print("=" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.server_close()


if __name__ == "__main__":
    main()
