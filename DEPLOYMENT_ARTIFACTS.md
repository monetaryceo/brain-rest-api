# Brain REST API — Deployment Artifacts Log

**Generated:** 2026-11-11
**Project:** brain-rest-api
**GitHub:** https://github.com/monetaryceo/brain-rest-api
**Local Path:** `C:\Users\ADMIN\.cline\data\workspaces\chat\brain-rest-api\`

---

## 1. Git Repository

| Field | Value |
|-------|-------|
| Remote | `https://github.com/monetaryceo/brain-rest-api.git` |
| Branch | `main` |
| Commit | `335d6f2` |
| Files committed | 7 |
| Lines added | 1,956 |


## 2. Server Configuration

| Field | Value |
|-------|-------|
| Bind host | `0.0.0.0` |
| Port | `8099` (override via `PORT` env var) |
| Protocol | HTTP |
| Dependencies | Zero (Python stdlib `http.server` only) |
| Start commands | `python server.py`, `start.bat`, `start.ps1` |



## 3. Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/models` | List 14 models with capabilities + permission |
| `POST` | `/v1/chat/completions` | OpenAI Chat Completions (supports `stream: true`) |
| `POST` | `/v1/tools/call` | Direct tool execution |
| `GET` | `/v1/tools` | List 25 tools |
| `GET` | `/v1/resources` | MCP resources (workspace, models, tools) |
| `GET` | `/v1/prompts` | MCP prompts/skills |
| `GET` | `/v1/health` | Health check (+ billion-context status) |
| `GET` / `OPTIONS` | `/mcp` | MCP server info / CORS preflight |
| `POST` | `/mcp` | MCP JSON-RPC 2.0 (`tools/list`, `tools/call`, `resources/list`, `prompts/list`) |



## 4. CORS Headers (all responses)

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization, X-Requested-With
```


## 5. Models (14 total — auto-populated via /v1/models)

| ID | Capabilities | Role | Permission |
|----|-------------|------|------------|
| `lfm3-omni` | text, vision, audio, tools, any_to_any, chat | multimodal | `[]` |
| `lfm3-1.7b-uncensored` | text, tools, chat | primary | `[]` |
| `deepseek-r1-llama-8b-abliterated` | text, tools, reasoning, chat | reasoning | `[]` |
| `qwen2.5-moe-2x1.5b-uncensored` | text, tools, moe, chat | moe | `[]` |
| `hope` | text, tools, quant, chat | quant | `[]` |
| `aira` | text, tools, risk, chat | risk | `[]` |
| `aether-trading` | text, tools, trading, chat | trading | `[]` |
| `deepseek-r1-qwen-7b-abliterated` | text, tools, reasoning, chat | reasoning-alt | `[]` |
| `wan2.2-ti2v-5b` | video, image_generation, text | video | `[]` |
| `laya-multilingual` | text, tools, multilingual, chat | multilingual | `[]` |
| `jev-style-0.8b-decision-v3` | text, tools, decision, chat | decision | `[]` |
| `jev-style-2b-decision-v3` | text, tools, decision, chat | decision | `[]` |
| `isis-trained` | web_search, docker_sandbox, pentest, uncensored_response, strix_recon, nuclei_vuln_scan, herdr_bot_swarm, infinity_swarm, tmux_session, deer_flow_workflow, swarmchat_communication, ablation, quantum_math, qlora_adapter, openai_compatible_api | pentest | `[]` |
| `llama3.2:1b` | text, tools, chat | chat | `[]` |

**lfm3-omni details:** LiquidAI LFM3-Omni-2B, 32768 context length, any-to-any modality, owned_by: liquidai


## 6. Tools (25 total)

### Brain MCP Tools (7)
`agent_list`, `agent_run`, `agent_install`, `agent_build`, `agent_doctor`, `context7_search`, `rea_analyze`

### ISIS Pentest Tools (12)
`nuclei_scan`, `finish_scan`, `web_search`, `spawn_sandbox`, `pentest`, `tmux_session`, `swarmchat`, `herdr_swarm`, `infinity_swarm`, `deer_flow`, `capabilities`, `health`

### Billion-Context Tools (6)
`bili_start`, `bili_status`, `bili_compress`, `bili_decompress`, `bili_search_context`, `bili_acp_status`


## 7. Billion-Context Proxy

| Field | Value |
|-------|-------|
| Local path | `C:\Users\ADMIN\.cline\data\workspaces\chat\billion-context\` |
| Default port | `8787` |
| Default host | `127.0.0.1` |
| Config file | `~/.config/billion-context/billion-context.json` |
| Dist entry | `dist/index.js` (built) |
| Bin entry | `bin/bili.cjs` |
| Context tools | compress, decompress, search_context, acp_status |

**Usage:** Point agents at `http://127.0.0.1:8787` instead of `http://localhost:8099/v1` for context compression.


## 8. MCP Configuration (Universal — ChatGPT, Grok, Manus, Claude, Cline, Copilot, Codex)

### HTTP Transport
```
URL: http://<YOUR-IP>:8099/mcp
Methods: tools/list, tools/call, resources/list, prompts/list
```

### Stdio Transport (agent-toolchain)
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

### MCP Tools (via /mcp)
`agent-list`, `agent-run`, `agent-install`, `agent-build`, `agent-doctor`, `context7-search`, `rea-analyze`, plus all 25 REST tools wrapped as MCP tools.


## 9. ISIS / Remote Configuration

| Field | Value |
|-------|-------|
| SSH host | `brain-agent@137.184.23.228` |
| SSH key | `C:\Users\ADMIN\.ssh\brain_agents_key` |
| ISIS base URL | `http://137.184.23.228:8088` |
| Ollama endpoint | `http://137.184.23.228:11434` |
| Remote ISIS tools | Requires SSH (not in Windows PATH — local agent-cli tools work fully) |


## 10. Short Names (Models)

All 14 model IDs from `/v1/models` serve as short names for API calls:
```
lfm3-omni, lfm3-1.7b-uncensored, deepseek-r1-llama-8b-abliterated,
qwen2.5-moe-2x1.5b-uncensored, hope, aira, aether-trading,
deepseek-r1-qwen-7b-abliterated, wan2.2-ti2v-5b, laya-multilingual,
jev-style-0.8b-decision-v3, jev-style-2b-decision-v3, isis-trained, llama3.2:1b
```


## 11. Client Integration Examples

### Cline (VS Code)
- Base URL: `http://localhost:8099/v1`
- API Key: `brain` (any value)
- Model: any from `/v1/models`

### PocketPal AI (Mobile)
- Server URL: `http://<YOUR-IP>:8099/v1` (use `http://` for raw IP)

### Any OpenAI SDK
```python
from openai import OpenAI
client = OpenAI(base_url="http://<YOUR-IP>:8099/v1", api_key="brain")
models = client.models.list()
```

### MCP Client (Claude Desktop, Cursor, etc.)
```json
{
  "mcpServers": {
    "brain-rest-api": {
      "url": "http://<YOUR-IP>:8099/mcp"
    }
  }
}
```


## 12. Verification Results (All Passed)

| Test | Result |
|------|--------|
| `/v1/models` — 14 models with capabilities + permission | PASS |
| `lfm3-omni` — vision + audio + any_to_any | PASS |
| `/v1/tools` — 25 tools | PASS |
| 6 billion-context tools | PASS |
| `/v1/resources` — 3 resources | PASS |
| `/v1/prompts` — 2 prompts | PASS |
| MCP `tools/list` — JSON-RPC 2.0 | PASS |
| MCP `tools/call` — execution | PASS |
| MCP `resources/list` — resources | PASS |
| MCP `prompts/list` — prompts | PASS |
| `/v1/chat/completions` — tool calling (`finish_reason: tool_calls`) | PASS |
| Streaming (SSE) — `text/event-stream` | PASS |
| CORS preflight (`OPTIONS`) — `200 OK` | PASS |
| `/v1/health` — healthy | PASS |

## 13. Next Steps / Pending

- ISIS remote tools require SSH (`ssh` not in Windows PATH) — local agent-cli tools work fully
- billion-context proxy not yet started (can be started via `bili_start` tool or `npm start` in billion-context dir)
- No GitHub token needed — repo created and pushed via `gh` CLI (authenticated as `monetaryceo`)


