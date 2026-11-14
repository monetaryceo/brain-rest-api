# OPENCODE MIGRATION GUIDE
## Complete Infrastructure & Application Handoff for opencode

**Status**: Production running on Digital Ocean droplet (137.184.23.228)  
**Last Updated**: 2026-11-13  
**Target**: opencode agent (replacing VS Code + Cline)

---

## 1. ARCHITECTURE OVERVIEW

`
Digital Ocean Droplet: 137.184.23.228 (thebrain.137-184-23-228.sslip.io)
User: brain-agent | SSH: ~/.ssh/brain_agents_key
`

### Services & Ports

| Service | Port | Protocol | Purpose |
|---------|------|----------|---------|
| brain-rest-api | 8099 | HTTP | OpenAI-compatible REST + MCP |
| billion-context | 8787 | HTTP | ACP context compression |
| ISIS Server | 8088 | HTTP | Native pentest/swarm tools |
| Caddy | 443 | HTTPS | Public TLS termination |
| Open WebUI | 8080 | HTTP | Chat interface |
| Aether Fleet | - | - | Trading bot (background) |

---

## 2. BRAIN REST API � PRIMARY INTERFACE

### File: /home/brain-agent/brain-rest-api/server.py (52KB, production)

**Capabilities:**
- 514 models exposed via /v1/models (dynamic fetch at startup)
- OpenAI-compatible: /v1/chat/completions, /v1/models, /v1/tools
- MCP JSON-RPC 2.0: /mcp (tools/list, tools/call, resources/list, prompts/list)
- 26 tools registered (agent-list, agent-run, herdr-swarm, infinity-swarm, deer-flow, bili_*, ISIS tools, auth)
- API Key auth: Authorization: Bearer <YOUR_BRAIN_API_KEY>

### Model Breakdown (Auto-fetched at startup)

| Provider | Count | Prefix | Endpoint |
|----------|-------|--------|----------|
| Local (brain) | 11 | lfm3-1.7b-uncensored, deepseek-r1-llama-8b-abliterated, etc. | llama.cpp on ports 8081-8092 |
| ISIS | 1 | isis-trained | /opt/the-brain/models/isis-trained/ |
| LiquidAI | 1 | lfm3-omni | Multimodal any-to-any |
| Ollama | 1 | llama3.2:1b | http://127.0.0.1:11434 |
| NVIDIA | 83 | nvidia/* | https://integrate.api.nvidia.com/v1 |
| OpenRouter | 417 | openrouter/* | https://openrouter.ai/api/v1 |

### Dynamic Model Fetching (Critical)

`python
# In server.py runs at startup
def fetch_openrouter_models():
    api_key = os.environ[OPENROUTER_API_KEY]
    req = Request(https://openrouter.ai/api/v1/models, headers={Authorization: fBearer {api_key}})
    # Returns 417 models: openrouter/google/gemini-4-hydrogen, openrouter/anthropic/claude-3.5-sonnet, etc.

def fetch_nvidia_models():
    api_key = os.environ[NVIDIA_API_KEY]
    req = Request(https://integrate.api.nvidia.com/v1/models, headers={Authorization: fBearer {api_key}})
    # Returns 83 models: nvidia/01-ai/yi-large, nvidia/deepseek-ai/deepseek-v4.1-flash, etc.

BRAIN_MODELS = build_model_list()  # 15 local + 417 OR + 83 NVIDIA = 515
`

### Environment Variables (in /home/brain-agent/brain-rest-api/.env)

`
OPENROUTER_API_KEY=sk-or-v1-<YOUR_OPENROUTER_KEY>
NVIDIA_API_KEY=nvapi-<YOUR_NVIDIA_KEY>
BRAIN_API_KEY=<YOUR_BRAIN_API_KEY>
`

### Start/Restart Commands

`ash
cd ~/brain-rest-api
pkill -f python3.*server.py
nohup python3 server.py > server.log 2>&1 &
tail -f server.log
`

### Health Check

`ash
curl -H Authorization: Bearer <YOUR_BRAIN_API_KEY> http://localhost:8099/health
curl -H Authorization: Bearer <YOUR_BRAIN_API_KEY> http://localhost:8099/v1/models | jq .data | length
`

---

## 3. DIGITAL OCEAN DROPLET CONFIGURATION

### Server Specs
- IP: 137.184.23.228
- Domain: thebrain.137-184-23-228.sslip.io (magic SSLIP domain)
- User: brain-agent (sudo access)
- SSH Key: ~/.ssh/brain_agents_key (on your local machine)

### Caddy Configuration (/home/brain-agent/Caddyfile)

`
thebrain.137-184-23-228.sslip.io {
    handle_path /brain-api/* { reverse_proxy localhost:8099 }
    handle_path /bili/* { reverse_proxy localhost:8787 }
    handle_path /mcp/* { reverse_proxy localhost:8088 }
    handle_path /chat/* { reverse_proxy localhost:8080 }
}
`

### SSL/TLS: Automatic via Caddy + SSLIP

### Systemd Service (Recommended)

Create /etc/systemd/system/brain-api.service:
`ini
[Unit]
Description=Brain REST API
After=network.target

[Service]
Type=simple
User=brain-agent
WorkingDirectory=/home/brain-agent/brain-rest-api
EnvironmentFile=/home/brain-agent/brain-rest-api/.env
ExecStart=/usr/bin/python3 server.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
`

Enable: sudo systemctl enable --now brain-api

---

## 4. AETHER & AETHER TRADING

### Aether Fleet (Background Trading Bot)
- Location: /opt/aether_fleet/ (runs as root via systemd)
- Process: aether_fleet_pro.py (PID 1789242, running since Nov 10)
- Database: /opt/aether_fleet/olympics.db (SQLite)
- Vault: /opt/aether_fleet/vault.json (encrypted credentials)

### Aether Trading Model (Local)
Exposed via brain-rest-api as aether-trading:
- Model file: aether-trading-q4_k_m.gguf
- Port: 8081 (llama.cpp server)
- Role: Trading decisions, risk analysis
- Capabilities: text, tools, trading, chat

### Olympics Database
/opt/aether_fleet/olympics.db contains: trading history, positions, P&L, strategy configs

### Access
`ash
ps aux | grep aether_fleet
sqlite3 /opt/aether_fleet/olympics.db .tables
sqlite3 /opt/aether_fleet/olympics.db SELECT * FROM positions;
journalctl -u aether-fleet -f
`

---

## 5. BILLION-CONTEXT (ACP Context Compression)

### Location: /home/brain-agent/billion-context/

Key Files:
- dist/index.js � Compiled proxy server
- package.json � Node.js dependencies
- AGENTS.md � 51KB agent instructions
- kernel/ � Core compression logic
- commands/ � CLI commands

### Running
`ash
cd ~/billion-context
npm run build
node dist/index.js --port 8787 --host 127.0.0.1
`

### API Endpoints (via Caddy at /bili/)
- POST /compress � Compress message range
- POST /decompress � Decompress by ref_id
- POST /search � Search compressed summaries
- GET /acp/status � Context usage overview

### Integration with brain-rest-api
Tools exposed: bili_start, bili_status, bili_compress, bili_decompress, bili_search_context, bili_acp_status


---

\n\n---\n\n## 6. ISIS SERVER (Native Pentest/Swarm Tools)\n\n### Location: /opt/isis-server/isis_server.py\n\nRunning as root: PID 1882812 on port 8088\n\n### Capabilities (26+ tools via MCP)\n- web_search - Search the web\n- docker_sandbox - Execute code in containers\n- pentest - Penetration testing workflows\n- strix_recon - Reconnaissance\n- nuclei_vuln_scan - Vulnerability scanning\n- herdr_bot_swarm - Bot swarm orchestration\n- infinity_swarm - Distributed task swarm\n- tmux_session - Persistent terminal sessions\n- deer_flow_workflow - Workflow automation\n- swarmchat_communication - Inter-agent messaging\n- abliteration - Model uncensoring\n- quantum_math - Mathematical reasoning\n- qlora_adapter - LoRA training\n- openai_compatible_api - Proxy to other APIs\n\n### ISIS-Trained Model\n- Path: /opt/the-brain/models/isis-trained/isis.safetensors\n- Base: needle3 + lfm3-omni\n- Exposed as: isis-trained (uncensored, full tool access)\n\n### Access via brain-rest-api\nAll ISIS tools are callable through /v1/chat/completions with model: isis-trained\n\n---\n\n## 7. AGENT TOOLCHAIN (Local Development)\n\n### Location: C:\\Users\\ADMIN\\.cline\\data\\workspaces\\chat\\agent-toolchain\\\n\nStructure:\nagent-toolchain/\n|-- bin/agent-cli.js          # Main CLI (on PATH as agent-cli)\n|-- brain/\n|   |-- mcp-server.js         # MCP stdio server\n|   |-- manifest.json         # Tool manifest\n|   |-- skills/               # Native skills (SKILL.md files)\n|-- herdr/                    # Rust bot swarm\n|-- Ghostman/                 # Python agent\n|-- context7/                 # Context7 MCP\n|-- deer-flow/                # Workflow engine (needs Docker)\n|-- agent-desktop/            # Rust desktop agent\n|-- agent-browser/            # Browser automation\n|-- craft-anything/           # Rust code generator\n|-- skills/                   # Skill registry\n|-- rea/                      # REA framework\n|-- replica-skill/            # Skill replication\n|-- dsh-superagent-prototype/ # Superagent\n\n### CLI Usage (on droplet after sync)\nagent-cli install all\nagent-cli build herdr\nagent-cli build agent-desktop\nagent-cli build craft-anything\nagent-cli herdr swarm task\nagent-cli agent-list\nagent-cli doctor\n\n### MCP Server (stdio)\nnode /home/brain-agent/agent-toolchain/brain/mcp-server.js\n# Tools: agent-list, agent-run, agent-install, agent-build, agent-doctor, context7-search, rea-analyze\n
---

## 8. LOCAL FILES TO SYNC TO SERVER

### Critical Files (Must be on server)

| Local Path | Server Path | Purpose |
|------------|-------------|---------|
| brain-rest-api/server_fixed.py | ~/brain-rest-api/server.py | Production API (514 models) |
| brain-rest-api/.env | ~/brain-rest-api/.env | API keys |
| agent-toolchain/ | ~/agent-toolchain/ | Full toolchain |
| billion-context/ | ~/billion-context/ | Context compression |
| C:\Users\ADMIN\.ssh\brain_agents_key | ~/.ssh/authorized_keys | SSH access |

### Sync Commands

scp -i ~/.ssh/brain_agents_key brain-rest-api/server_fixed.py brain-agent@137.184.23.228:~/brain-rest-api/server.py
scp -i ~/.ssh/brain_agents_key brain-rest-api/.env brain-agent@137.184.23.228:~/brain-rest-api/.env
scp -i ~/.ssh/brain_agents_key -r agent-toolchain brain-agent@137.184.23.228:~/
scp -i ~/.ssh/brain_agents_key -r billion-context brain-agent@137.184.23.228:~/
---

## 9. GITHUB REPOSITORIES

### Primary Repos (Push all local changes)

# Brain REST API
cd brain-rest-api
git init
git remote add origin https://github.com/YOUR_USERNAME/brain-rest-api.git
git add .
git commit -m "Production server with dynamic 514-model fetching"
git push -u origin main

# Agent Toolchain
cd ../agent-toolchain
git remote add origin https://github.com/YOUR_USERNAME/agent-toolchain.git
git push -u origin main

# Billion Context
cd ../billion-context
git remote add origin https://github.com/YOUR_USERNAME/billion-context.git
git push -u origin main

### Server-side Git Pull (for updates)

cd ~/brain-rest-api && git pull
cd ~/agent-toolchain && git pull
cd ~/billion-context && git pull
---

## 10. OPENCODE CONFIGURATION

### Required opencode Setup

Create ~/.opencode/config.json:
{
  "mcpServers": {
    "brain": {
      "command": "node",
      "args": ["/home/brain-agent/agent-toolchain/brain/mcp-server.js"],
      "env": {
        "BRAIN_API_URL": "https://thebrain.137-184-23-228.sslip.io/brain-api",
        "BRAIN_API_KEY": "<YOUR_BRAIN_API_KEY>"
      }
    },
    "billion-context": {
      "command": "node",
      "args": ["/home/brain-agent/billion-context/dist/index.js", "--port", "8787"]
    }
  },
  "models": {
    "default": "openrouter/google/gemini-4-hydrogen",
    "providers": {
      "openrouter": {
        "apiKey": "sk-or-v1-<YOUR_OPENROUTER_KEY>",
        "baseURL": "https://openrouter.ai/api/v1"
      },
      "nvidia": {
        "apiKey": "nvapi-<YOUR_NVIDIA_KEY>",
        "baseURL": "https://integrate.api.nvidia.com/v1"
      },
      "brain": {
        "baseURL": "https://thebrain.137-184-23-228.sslip.io/brain-api/v1",
        "apiKey": "<YOUR_BRAIN_API_KEY>"
      }
    }
  }
}

### opencode Skills to Install

cp -r agent-toolchain/brain/skills/* ~/.opencode/skills/

---

## 11. COMPLETE FILE INVENTORY

### On Droplet (Production)

/home/brain-agent/
|-- brain-rest-api/
|   |-- server.py          # 52KB - MAIN PRODUCTION FILE
|   |-- .env               # API keys (OPENROUTER, NVIDIA, BRAIN_API_KEY)
|   |-- server.log         # Runtime logs
|   |-- all_models.json    # Cached model list
|   |-- query_models.py    # Model query utility
|-- billion-context/       # Full Node.js project (git repo)
|-- agent-toolchain/       # Full toolchain (git repo)
|-- .ssh/
|   |-- authorized_keys    # Your public key
|-- Caddyfile              # Reverse proxy config
|-- Brain/                 # Brain workspace

/opt/
|-- aether_fleet/
|   |-- aether_fleet_pro.py    # Running trading bot
|   |-- olympics.db            # Trading database
|   |-- vault.json             # Encrypted credentials
|-- isis-server/
|   |-- isis_server.py         # MCP pentest/swarm server
|-- the-brain/
|   |-- models/isis-trained/   # ISIS model weights
|-- brain-venv/                # Python venv for ISIS

### Local (Development) — C:\Users\ADMIN\.cline\data\workspaces\chat\

chat/
|-- brain-rest-api/
|   |-- server_fixed.py      # Latest fixed version (SYNC THIS)
|   |-- server.py            # Old version
|   |-- .gitignore
|   |-- README.md
|   |-- DEPLOYMENT_ARTIFACTS.md
|   |-- test_*.py
|-- agent-toolchain/         # 12 sub-projects
|-- billion-context/         # Context compression
|-- OPENCODE_MIGRATION.md    # THIS FILE
|-- AGENTS.md                # Agent instructions
## 12. DAILY OPERATIONS FOR OPENCODE

### Morning Startup

```bash
# 1. Check all services
ssh brain-agent@137.184.23.228 "ps aux | grep -E 'server.py|isis_server|aether_fleet|billion-context'"

# 2. Verify model count
ssh brain-agent@137.184.23.228 "curl -s -H 'Authorization: Bearer <YOUR_BRAIN_API_KEY>' http://localhost:8099/v1/models | jq '.data | length'"

# 3. Check logs
ssh brain-agent@137.184.23.228 "tail -20 ~/brain-rest-api/server.log"
```

### Deploy Code Changes

```bash
# 1. Edit locally in opencode
# 2. Commit & push
git add -A && git commit -m "fix: description" && git push

# 3. Pull on server & restart
ssh brain-agent@137.184.23.228 "cd ~/brain-rest-api && git pull && pkill -f server.py && nohup python3 server.py > server.log 2>&1 &"
```

### Run Tests

```bash
# Test chat completion
curl -X POST https://thebrain.137-184-23-228.sslip.io/brain-api/v1/chat/completions   -H "Authorization: Bearer <YOUR_BRAIN_API_KEY>"   -H "Content-Type: application/json"   -d '{"model": "openrouter/google/gemini-4-hydrogen", "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 50}'

# Test ISIS tool
curl -X POST https://thebrain.137-184-23-228.sslip.io/brain-api/v1/chat/completions   -H "Authorization: Bearer <YOUR_BRAIN_API_KEY>"   -H "Content-Type: application/json"   -d '{"model": "isis-trained", "messages": [{"role": "user", "content": "Run strix_recon on example.com"}], "tools": [{"type": "function", "function": {"name": "strix_recon", "parameters": {"target": "example.com"}}}]}'
```

---

## 13. TROUBLESHOOTING

| Issue | Solution |
|-------|----------|
| Port 8099 in use | fuser -k 8099/tcp then restart |
| Model count < 500 | Check .env has valid API keys, restart server |
| 401 Unauthorized | Verify BRAIN_API_KEY matches in .env and request |
| Caddy 502 | Check upstream service running (systemctl status brain-api) |
| ISIS tools fail | Check /opt/isis-server/isis_server.py running on 8088 |
| Aether fleet down | systemctl restart aether-fleet or check olympics.db |

---

## 14. KEY CONTACTS & CREDENTIALS

| Service | Credential | Location |
|---------|------------|----------|
| OpenRouter | sk-or-v1-ddb69f15... | ~/.env + local |
| NVIDIA | nvapi-_FHc4--Usegv... | ~/.env + local |
| Brain API | <YOUR_BRAIN_API_KEY> | ~/.env + opencode config |
| SSH | brain_agents_key (private) | C:\Users\ADMIN\.ssh\ |
| Droplet | brain-agent@137.184.23.228 | Digital Ocean |

---

## 15. NEXT STEPS FOR OPENCODE

1. Sync this file to ~/OPENCODE_MIGRATION.md on droplet
2. Configure opencode with MCP servers (brain, billion-context)
3. Test model access � verify all 514 models work
4. Run aether trading check � query olympics.db for positions
5. Validate ISIS tools � run a pentest workflow
6. Set up auto-deploy � GitHub Actions to droplet pull + restart
7. Monitor � Add health checks to cron/systemd

---

**This document contains everything needed for opencode to operate the full stack independently. All production files live on the server. All development files are in GitHub. The local PC is no longer required.**
