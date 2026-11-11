# Brain REST API — OpenAI-Compatible

A clean REST API that exposes all **brain tools, skills, and models** in the exact OpenAI Chat Completions API format. Works with Cline and any OpenAI-compatible client.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/models` | List all available models (OpenAI format) |
| `POST` | `/v1/chat/completions` | Chat completions with tool calling (OpenAI format) |
| `POST` | `/v1/tools/call` | Direct tool execution |
| `GET` | `/v1/tools` | List all available tools |
| `GET` | `/health` | Health check |

## OpenAI Format (exact)

**GET /v1/models** response:
```json
{
  "object": "list",
  "data": [
    { "id": "lfm3-1.7b-uncensored", "object": "model", "created": 1234567890, "owned_by": "brain", ... },
    { "id": "isis-trained", "object": "model", "created": 1234567890, "owned_by": "isis", ... },
    { "id": "llama3.2:1b", "object": "model", "created": 1234567890, "owned_by": "ollama", ... }
  ]
}
```

**POST /v1/chat/completions** request:
```json
{
  "model": "isis-trained",
  "messages": [ { "role": "user", "content": "run a nuclei scan on example.com" }],
  "tools": [ { "type": "function", "function": { "name": "nuclei_scan", ... } } ],
  "tool_choice": "auto",
  "temperature": 0.7
}
```

**POST /v1/chat/completions** response (tool call):
```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "isis-trained",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": null,
        "tool_calls": [
          { "id": "call_xxx", "type": "function", "function": { "name": "nuclei_scan", "arguments": "{\"target\":\"example.com\"}" } }
        ]
      },
      "finish_reason": "tool_calls"
    }
  ],
  "usage": { "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0 }
}
```

## Tools Exposed (21 total)

### Brain MCP Tools (via agent-cli)
- `agent_list` — List agent-toolchain tools and status
- `agent_run` — Run an agent-toolchain CLI tool
- `agent_install` — Install tool dependencies
- `agent_build` — Build a tool
- `agent_doctor` — Check runtimes + binaries
- `context7_search` — Search Context7 documentation
- `rea_analyze` — REA reverse-engineering analysis

### ISIS Pentest Tools (via remote brain-agent)
- `nuclei_scan` — Nuclei vulnerability scan
- `finish_scan` — Complete pentest scan with findings
- `web_search` — Web search via ISIS
- `spawn_sandbox` — Spawn Docker sandbox
- `pentest` — Full pentest (strix + nuclei)
- `tmux_session` — Run command in tmux session
- `swarmchat` — Send swarmchat message
- `herdr_swarm` — Herdr bot swarm task
- `infinity_swarm` — Infinity swarm task
- `deer_flow` — DeerFlow workflow
- `capabilities` — List ISIS capabilities
- `health` — ISIS server health

## Models Exposed (12 total)

`lfm3-1.7b-uncensored`, `deepseek-r1-llama-8b-abliterated`, `qwen2.5-moe-2x1.5b-uncensored`, `hope`, `aira`, `aether-trading`, `deepseek-r1-qwen-7b-abliterated`, `wan2.2-ti2v-5b`, `laya-multilingual`, `jev-style-0.8b-decision-v3`, `jev-style-2b-decision-v3`, `isis-trained`, `llama3.2:1b`

## Quick Start

```bash
cd C:\Users\ADMIN\.cline\data\workspaces\chat\brain-rest-api
python server.py
```

Server listens on `http://0.0.0.0:8099` (set `PORT` env var to override).

## Cline Integration

Add this as an OpenAI-compatible model in Cline:
- **Base URL:** `http://localhost:8099/v1`
- **API Key:** `brain` (any value accepted)
- **Model:** any model ID from `/v1/models` (e.g. `isis-trained`)

Then Cline can call tools via the standard OpenAI tool-calling format.

## Architecture

- Zero external dependencies (Python stdlib `http.server`)
- Brain MCP tools run via `bin/agent-cli.js` (Node)
- ISIS tools run via SSH to `brain-agent@137.184.23.228:8088`
- Tool selection uses keyword matching (deterministic routing)
- All responses follow the OpenAI API spec exactly

## Model Capabilities Table

All models expose `capabilities` in `/v1/models`:

| Model | Capabilities | Role | Notes |
|-------|-------------|------|-------|
| `lfm3-1.7b-uncensored` | text, tools, chat | primary | Uncensored LFM3 1.7B |
| `deepseek-r1-llama-8b-abliterated` | text, tools, reasoning, chat | reasoning | DeepSeek R1 8B abliterated |
| `qwen2.5-moe-2x1.5b-uncensored` | text, tools, moe, chat | moe | Qwen2.5 MoE uncensored |
| `hope` | text, tools, quant, chat | quant | HOPE quant model |
| `aira` | text, tools, risk, chat | risk | AIRA risk model |
| `aether-trading` | text, tools, trading, chat | trading | Aether trading model |
| `deepseek-r1-qwen-7b-abliterated` | text, tools, reasoning, chat | reasoning-alt | DeepSeek-R1-Qwen 7B |
| `wan2.2-ti2v-5b` | video, image_generation, text | video | Wan2.2 video generation |
| `laya-multilingual` | text, tools, multilingual, chat | multilingual | Laya multilingual |
| `jev-style-0.8b-decision-v3` | text, tools, decision, chat | decision | Jev decision 0.8B |
| `jev-style-2b-decision-v3` | text, tools, decision, chat | decision | Jev decision 2B |
| `isis-trained` | web_search, docker_sandbox, pentest, uncensored_response, strix_recon, nuclei_vuln_scan, herdr_bot_swarm, infinity_swarm, tmux_session, deer_flow_workflow, swarmchat_communication, ablation, quantum_math, qlora_adapter, openai_compatible_api | pentest | ISIS pentest model (uncensored) |
| `llama3.2:1b` | text, tools, chat | chat | Ollama llama3.2 1B |
| **`lfm3-omni`** | **text, vision, audio, tools, any_to_any, chat** | **multimodal** | **LiquidAI LFM3-Omni-2B — any-to-any multimodal** |

Capability legend: `text`=text gen, `vision`=image understanding, `audio`=audio I/O, `tools`=OpenAI function calling, `any_to_any`=multimodal, `reasoning`=CoT, `uncensored_response`=no content filter.

## Billion-Context Setup (Context Compression)

[billion-context](https://github.com/ranxianglei/billion-context) is already cloned and built at:
`C:\Users\ADMIN\.cline\data\workspaces\chat\billion-context\`

It is an HTTP proxy (default port **8787**) that sits between your agent client and any model API, injecting ACP (Active Context Pruning) compression so sessions can run for billions of tokens without blowing the context window.

### 1. Start the proxy

Via the API:
```json
POST /v1/tools/call
{ "name": "bili_start", "arguments": { "port": 8787, "host": "127.0.0.1" } }
```

Or directly:
```bash
cd C:\Users\ADMIN\.cline\data\workspaces\chat\billion-context
npm start
```

### 2. Configure a target model API

Edit `~/.config/billion-context/billion-context.json`:
```json
{
  "port": 8787,
  "host": "127.0.0.1",
  "providers": {
    "http://localhost:8099": {
      "models": {
        "lfm3-omni": { "context": 32768 },
        "isis-trained": { "context": 32768 }
      }
    }
  }
}
```

### 3. Use billion-context as your base URL

Point your agent at `http://127.0.0.1:8787` instead of `http://localhost:8099`. The proxy forwards requests to the Brain REST API and compresses context automatically.

### 4. Context-management tools

The proxy injects four tools: `compress`, `decompress`, `search_context`, `acp_status`. Exposed via `bili_compress`, `bili_decompress`, `bili_search_context`, `bili_acp_status`.

## MCP Setup (Model Context Protocol)

The Brain MCP server is at:
`C:\Users\ADMIN\.cline\data\workspaces\chat\agent-toolchain\brain\mcp-server.js`

Register as stdio MCP server in your MCP client config:
```json
{
  "mcpServers": {
    "agent-toolchain": {
      "command": "node",
      "args": ["C:\\Users\\ADMIN\\.cline\\data\\workspaces\\chat\\agent-toolchain\\brain\\mcp-server.js"]
    }
  }
}
```

MCP tools: `agent-list`, `agent-run`, `agent-install`, `agent-build`, `agent-doctor`, `context7-search`, `rea-analyze`. The REST API wraps these same tools as OpenAI function calls.

## REST API Base URL Configuration

| Client | Base URL | Notes |
|--------|----------|-------|
| Direct API | `http://localhost:8099/v1` | Raw REST API |
| Via billion-context | `http://127.0.0.1:8787` | With context compression |
| Cline | `http://localhost:8099/v1` | OpenAI-compatible model |
| Any OpenAI SDK | `http://localhost:8099/v1` | Set base_url + API key |

### Cline Integration

1. Settings → Model providers → Add OpenAI-compatible
2. **Base URL:** `http://localhost:8099/v1`
3. **API Key:** `brain` (any value accepted)
4. **Model:** from `/v1/models` (e.g. `lfm3-omni`, `isis-trained`)
5. Enable tool calling

Cline will call all 26 tools via standard OpenAI tool-calling format.

---

## Model Context Protocol (MCP) — Universal for All Apps

The MCP server is available via **HTTP JSON-RPC 2.0** at `http://<YOUR-IP>:8099/mcp`. Works with any app that speaks MCP over HTTP (ChatGPT, Grok, Manus, Claude, Cline, Copilot, Codex, etc.).

### MCP Methods

| Method | Description |
|--------|-------------|
| `tools/list` | List all 25 tools with input schemas |
| `tools/call` | Execute a tool by name with arguments |
| `resources/list` | List workspace resources (state, models, tools) |
| `prompts/list` | List available skills/prompt templates |

### Example: `tools/list` Request
```json
{
  "jsonrpc": "2.0",
  "method": "tools/list",
  "params": {},
  "id": 1
}
```

### Example: `tools/call` Request
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "agent_list",
    "arguments": {}
  },
  "id": 2
}
```

### Example: `tools/call` Response
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [
      { "type": "text", "text": "{\"code\":0,\"stdout\":\"...\"}" }
    ],
    "isError": false
  }
}
```

### MCP Client Configuration

**Claude Desktop / Cursor / any MCP client (HTTP transport):**
```json
{
  "mcpServers": {
    "brain-rest-api": {
      "url": "http://<YOUR-IP>:8099/mcp"
    }
  }
}
```

**Stdio transport (agent-toolchain MCP server):**
```json
{
  "mcpServers": {
    "agent-toolchain": {
      "command": "node",
      "args": ["C:\\Users\\ADMIN\\.cline\\data\\workspaces\\chat\\agent-toolchain\\brain\\mcp-server.js"]
    }
  }
}
```

---

## App-Specific Integration

### Cline (VS Code)
Settings → Model providers → Add OpenAI-compatible:
- **Base URL:** `http://localhost:8099/v1`
- **API Key:** `brain` (any value)
- **Model:** from `/v1/models` (e.g. `lfm3-omni`, `isis-trained`)
- Enable tool calling

### PocketPal AI (Mobile)
- **Server URL:** `http://<YOUR-IP>:8099/v1` (use `http://` for raw IP connections)
- Models auto-populate from `/v1/models`
- Supports streaming chat

### ChatGPT / Grok / Manus / Copilot / Codex
- **Base URL:** `http://<YOUR-IP>:8099/v1`
- **API Key:** any value
- Models auto-populate from `/v1/models`

### Any OpenAI SDK
```python
from openai import OpenAI
client = OpenAI(base_url="http://<YOUR-IP>:8099/v1", api_key="brain")
models = client.models.list()  # Auto-populates all 14 models
```

---

## CORS (Required for PocketPal, Browser Clients, Mobile Apps)

All responses include:
```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization, X-Requested-With
```

PocketPal AI: Use Server URL `http://<YOUR-IP>:8099/v1` (use `http://`, not `https://`, for raw IP connections).

---

## Streaming (SSE)

`POST /v1/chat/completions` with `"stream": true` returns `text/event-stream`:
```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":...,"model":"lfm3-omni","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":...,"model":"lfm3-omni","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}
data: [DONE]
```

---

## Additional REST Discovery Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/resources` | List MCP resources (workspace state, model registry, tool registry) |
| `GET` | `/v1/prompts` | List MCP prompts/skills |
| `GET` / `OPTIONS` | `/mcp` | MCP server info / CORS preflight |
| `POST` | `/mcp` | MCP JSON-RPC 2.0 (`tools/list`, `tools/call`, `resources/list`, `prompts/list`) |