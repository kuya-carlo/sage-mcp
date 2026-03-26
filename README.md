# SAGE — Student Agent for Guided Education
> Your autonomous academic co-pilot, built purely on Notion and FastMCP.

![SAGE Demo](assets/demo.gif)

Built for **MLH Global Hack Week — Notion AI Challenge**

---

## What is SAGE?

SAGE is an advanced, multi-tenant Notion MCP-powered academic agent for Filipino university students. Tell it your program and year level — it securely authenticates your Notion workspace via OAuth, fetches your CHED-verified curriculum from the Ghost Commons registry, dynamically expands curriculum tags into functional study databases using AI, and builds your entire semester workspace in Notion automatically.

---

## Features

| Feature | Status |
|---|---|
| Pure Python FastMCP Proxy Architecture | ✅ Deployed |
| Multi-Tenant Notion OAuth & Encryption | ✅ Deployed |
| Dynamic AI Semester Builder | ✅ Deployed |
| ADHD Micro-Task Breakdown | ✅ Deployed |
| Burnout & Cognitive Load Sensor | ✅ Deployed |
| Web UI (Markdown, Themes, Abort Control) | ✅ Deployed |
| Ghost Commons Registry | ✅ Deployed |

---

## How it works
```
Student: "I'm a 2nd year BS CpE student, semester 1"
    ↓
SAGE authenticates via custom Notion OAuth & encrypts token to Supabase
    ↓
SAGE's Agent calls `create_semester_tree` natively via FastMCP
    ↓
Fetches CHED CMO-verified curriculum from Ghost Commons
    ↓
AI dynamically expands competencies into exact study prompts and summaries
    ↓
Spawns internal Pure Python FastMCP Server to execute secure I/O
    ↓
Hierarchical Notion Course Pages & Theme-tracked Topic Databases — done
```

---

## Tech stack

- **FastAPI** — High-performance backend & Chat Proxy
- **FastMCP (Pure Python)** — 100% Native Architecture for Notion I/O Operations
- **Notion OAuth 2.0** — Multi-tenant secure workspace integration
- **Qwen2.5-Coder-32B** via Vultr Serverless Inference (AI Curriculum Expansion)
- **Supabase** PostgreSQL — Core database & Fernet-encrypted Token Vault
- **Docker + Podman** — Containerized deployment
- **GitHub Container Registry** — Automated container publishing

---

## Setup
### Docker Compose (recommended)

```sh
# Run locally, has both db and server in.
docker compose up -d
```
### Bare Metal
```bash
# Clone
git clone https://github.com/kuya-carlo/sage-mcp
cd sage-mcp

# Copy env
cp .env.example .env
# Fill in your keys (see .env.example)

uv run fastapi dev sage/main.py
```

Then seed your programs

## Add it to your favourite MCP client

SAGE natively exposes its own macro-tools via a standard stdio FastMCP server.
```json
{
  "mcpServers": {
    "sage": {
      "command": "uv",
      "args": ["run", "fastmcp", "run", "sage/services/mcp_tools/server.py:mcp"]
    }
  }
}
```

### Required env vars

See `.env.example` for full list. Minimum to run:
- `DB_URL`
- `NOTION_CLIENT_ID` + `NOTION_CLIENT_SECRET` + `NOTION_REDIRECT_URI`
- `FERNET_KEY`

---

## Technical Caveats & Edge Cases

SAGE is currently in **v1.0 (Beta)**. Below are the known system behaviors and technical boundaries.

### ✅ What Works (Robustly Handled)
- **Fuzzy AI Output** — Uses regex to strip AI preambles and extract JSON from within chatty model responses.
- **Cold Boot Seeding** — Automatically triggers background ETL if a requested program is not in the Ghost Commons registry.
- **Idempotency** — Searches Notion for existing pages before building to prevent duplicate workspace clutter.
- **AI Fallback** — Reverts to raw competency tags if the AI expansion model fails to generate specific topics.

### ⚠️ Current Limitations
- **Cloudflare Interaction** — Automated syllabus extraction via `gaffa` has low success rates against sites protected by Cloudflare.
- **Cold Boot Instability** — Program seeding is partially volatile; fetching university-specific syllabi relies on open access which is sometimes blocked by institutional firewalls.
- **Permissions** — SAGE only sees what you share. You must explicitly share a parent page with the SAGE integration.
- **Rate Limiting** — No exponential backoff for Notion 429s yet; hits a limit and fails the current tool call.

### 🚨 Critical Risks (Technical Debt)
- **Process "Fork-Bombing"** — Every Notion tool call spawns a new Python process via `uv run fastmcp`. Large semesters (>8 courses) can trigger **300+ process spawns**, potentially causing HTTP timeouts or CPU exhaustion.
- **Fernet Key Persistence** — Rotating the `FERNET_KEY` without a migration plan will lock all existing users out of their encrypted tokens.
- **Notion Block Limit** — Appending >100 blocks at once (e.g., massive curriculum expansions) will fail due to Notion's batch API limits.

---

## Roadmap

- **v1.1** — pgvector semantic search on Ghost Commons
- **v1.2** — Chrome extension LMS bridge
- **v1.3** — Gmail receipt scraper (GCash/Maya burn-rate)
- **v1.5** — Live Opportunity Sentinel (Devpost/MLH)
- **v2.0** — Federated Ghost Commons, Tagalog/English bridges

---

**Built by:** kuya-carlo  — BS Computer Engineering student, Bulacan State University

**Solo submission** — MLH Global Hack Week 2026
