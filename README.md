<div align="center">

# The Orchestrator

**A local-first, multi-agent AI system that coordinates specialized agents to autonomously accomplish complex software development tasks.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-Orchestration-1C3C3C?logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Redis](https://img.shields.io/badge/Redis-DC382D?logo=redis&logoColor=white)](https://redis.io)
[![Ollama](https://img.shields.io/badge/Ollama-Local_LLM-000000)](https://ollama.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0-blue)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/yashasviudayan-py/the-orchestrator/pulls)

<br>

*Zero cloud dependencies. Zero API keys. Zero cost. Full privacy.*

[Getting Started](#getting-started) · [Features](#features) · [Architecture](#architecture) · [Documentation](#documentation) · [Contributing](#contributing)

</div>

---

## What is The Orchestrator?

The Orchestrator is a meta-agent system that takes a high-level software task — like *"Research OAuth2 best practices and implement it in my project"* — and autonomously coordinates three specialized AI agents to get it done:

| Agent | Role | Integration |
|-------|------|-------------|
| **Research Agent** | Finds best practices, patterns, and documentation | HTTP API |
| **Context Core** | Manages project memory, semantic search, and secret filtering | Python Import |
| **PR-Agent** | Generates code, creates branches, and opens pull requests | Subprocess |

A **Supervisor** node powered by Ollama intelligently routes tasks between agents, while a **Human-in-the-Loop safety gate** ensures destructive operations (git push, file delete) require explicit approval before execution.

Everything runs locally on your machine. No data ever leaves your environment.

---

## Features

### Intelligent Agent Orchestration
- **Adaptive Routing** — LLM analyzes objectives and routes to the right agent automatically
- **3 Routing Strategies** — Research-first, Context-first, or Adaptive (LLM-powered)
- **Context Summarization** — compresses agent outputs to prevent token overflow between handoffs
- **Max Iterations Safeguard** — prevents infinite agent loops (default: 10)

### Human-in-the-Loop Safety
- **4 Risk Levels** — LOW (auto-approve), MEDIUM, HIGH, CRITICAL
- **Automatic Risk Classification** — operations mapped to risk levels by type
- **Approval Dashboard** — web UI with diff viewer, countdown timer, and one-click approve/reject
- **Timeout Handling** — configurable per-operation timeouts (default: 300s)
- **Audit Trail** — every approval decision is logged with timestamp and notes

### Real-Time Web Dashboard
- **ChatGPT-style Interface** — submit tasks, see agent activity stream in real-time
- **SSE Streaming** — 12 event types for live progress updates (no WebSockets)
- **Session History** — browse and re-read past task executions
- **Analytics** — task success rates, agent usage, approval statistics
- **Health Monitoring** — live status for all 5 services (Ollama, Redis, Research, Context, PR)
- **Dark Theme** — jet black, Apple SF Pro-inspired design

### Security
- **Secret Filtering** — 15+ credential patterns (API keys, JWT, AWS, SSH) scanned and redacted between every agent handoff
- **Security Headers** — X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy, Permissions-Policy
- **CORS Restricted** — locked to localhost origins
- **XSS Prevention** — all user input HTML-escaped
- **Input Validation** — Pydantic v2 on every API boundary

### CLI
- `orchestrator serve` — start the Command Center web server
- `orchestrator run` — execute a task directly from the terminal
- `orchestrator status` — check system health

---

## Architecture

```
                          ┌──────────────────────┐
                          │    User (Web / CLI)   │
                          └──────────┬───────────┘
                                     │
                          ┌──────────▼───────────┐
                          │    Smart Router       │
                          │  conversational → LLM │
                          │  task → Agent Pipeline│
                          └──────────┬───────────┘
                                     │
               ┌─────────────────────▼─────────────────────┐
               │          LangGraph StateGraph              │
               │                                            │
               │  parse_objective                           │
               │       │                                    │
               │       ▼                                    │
               │  supervisor_entry (routing strategy)       │
               │       │                                    │
               │       ├──► Research Agent ──► Secret Filter│
               │       ├──► Context Core  ──► Secret Filter│
               │       └──► PR-Agent ─────► HITL Gate ─────┤
               │                                 │          │
               │  supervisor_route ◄─────────────┘          │
               │       │                                    │
               │       ▼                                    │
               │    finalize ──► Save to Vault              │
               └───────────────────┬────────────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │   Redis (Shared State)       │
                    │   SSE Event Queue → Browser  │
                    └─────────────────────────────┘
```

### Key Design Patterns

| Pattern | Where | Why |
|---------|-------|-----|
| **Blackboard** | Shared `TaskState` in Redis | Decouples agents — they never talk directly |
| **Supervisor** | Central routing node in LangGraph | Single point of control for agent orchestration |
| **Strategy** | Pluggable routing strategies | Swap routing behavior without changing the graph |
| **Observer** | SSE progress callbacks | Real-time UI without polling |
| **Gate** | HITL approval node | Blocks execution until human decision |
| **Interface** | `AgentInterface` ABC | All agents are interchangeable |

---

## Getting Started

### Prerequisites

- **Python 3.10+**
- **[Ollama](https://ollama.com)** — local LLM runtime
- **[Redis](https://redis.io)** — state persistence

```bash
# macOS (Homebrew)
brew install ollama redis

# Pull required models
ollama pull llama3.1:8b-instruct-q8_0
ollama pull nomic-embed-text
```

### Installation

```bash
# Clone the repository
git clone https://github.com/yashasviudayan-py/the-orchestrator.git
cd the-orchestrator

# Create virtual environment (recommended)
python -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your agent paths
```

### Quick Start

```bash
# 1. Start services
ollama serve &
redis-server &

# 2. Launch the Command Center
python -m src.cli.main serve

# 3. Open http://localhost:8080
```

### Usage

**Web Dashboard** — submit tasks via the chat interface at `http://localhost:8080`

**CLI** — run tasks directly from the terminal:
```bash
python -m src.cli.main run "Add input validation to the signup form"
```

**API** — integrate programmatically:
```bash
curl -X POST http://localhost:8080/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "objective": "Research and implement rate limiting",
    "max_iterations": 10,
    "routing_strategy": "adaptive",
    "enable_hitl": true
  }'
```

**Python**:
```python
import asyncio
from src.config import get_cached_settings
from src.agents import ResearchAgentInterface, ContextCoreInterface, PRAgentInterface
from src.orchestrator import EnhancedOrchestratorGraph, RoutingStrategy

async def main():
    settings = get_cached_settings()

    orchestrator = EnhancedOrchestratorGraph(
        research_agent=ResearchAgentInterface(settings.research_agent_url),
        context_agent=ContextCoreInterface(settings.context_core_path),
        pr_agent=PRAgentInterface(settings.pr_agent_path),
        routing_strategy=RoutingStrategy.ADAPTIVE,
    )

    result = await orchestrator.run(
        objective="Add dark mode toggle to the React app",
        user_context={"repo_path": "/path/to/repo"},
    )

    print(f"Status: {result.status}")
    print(f"Output:\n{result.final_output}")

asyncio.run(main())
```

---

## Project Structure

```
the-orchestrator/
├── src/
│   ├── orchestrator/              # LangGraph orchestration engine
│   │   ├── graph.py               # Base orchestrator graph
│   │   ├── graph_v2.py            # Enhanced graph with supervision
│   │   ├── nodes.py               # Node implementations
│   │   ├── edges.py               # Conditional routing logic
│   │   ├── supervisor.py          # Intelligent routing with strategies
│   │   ├── summarizer.py          # Context window management
│   │   └── hitl_integration.py    # HITL gate integration
│   │
│   ├── agents/                    # Agent interfaces
│   │   ├── base.py                # AgentInterface ABC
│   │   ├── research.py            # Research Agent (HTTP)
│   │   ├── context.py             # Context Core (Python import)
│   │   └── pr_agent.py            # PR-Agent (subprocess)
│   │
│   ├── state/                     # Redis-backed shared state
│   │   ├── schemas.py             # Pydantic models (TaskState, etc.)
│   │   ├── redis_client.py        # Async Redis with connection pooling
│   │   └── manager.py             # State CRUD operations
│   │
│   ├── api/                       # HITL approval system
│   │   ├── server.py              # Approval REST API
│   │   ├── approval.py            # Risk classification schemas
│   │   └── approval_manager.py    # Approval lifecycle management
│   │
│   ├── web/                       # Command Center web interface
│   │   ├── server.py              # Main FastAPI application
│   │   ├── task_manager.py        # Background task execution + SSE
│   │   ├── health_monitor.py      # Service health checks
│   │   ├── analytics.py           # Metrics and statistics
│   │   ├── process_manager.py     # Service start/stop control
│   │   ├── models.py              # Request/response models
│   │   ├── static/                # CSS, JS, images
│   │   └── templates/             # Jinja2 HTML templates
│   │
│   ├── cli/main.py                # Click CLI (serve, run, status)
│   └── config.py                  # Pydantic settings
│
├── tests/                         # pytest + pytest-asyncio
├── docs/                          # Architecture and usage guides
├── examples/                      # Demo scripts
├── requirements.txt
├── .env.example
├── LICENSE
└── README.md
```

---

## Configuration

All configuration is managed via environment variables (`.env` file) with Pydantic validation:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3.1:8b-instruct-q8_0` | LLM model for routing and generation |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model |
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `RESEARCH_AGENT_URL` | `http://localhost:8000` | Research Agent API URL |
| `CONTEXT_CORE_PATH` | — | Path to Context Core project |
| `PR_AGENT_PATH` | — | Path to PR-Agent project |
| `MAX_ITERATIONS` | `10` | Max agent loop iterations |
| `GITHUB_TOKEN` | — | GitHub token for PR creation |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

---

## API Reference

### Task Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/tasks` | Create and start a new task |
| `GET` | `/api/tasks` | List tasks (filterable by status) |
| `GET` | `/api/tasks/{id}` | Get task details |
| `GET` | `/api/tasks/{id}/stream` | SSE stream for real-time progress |
| `DELETE` | `/api/tasks/{id}` | Cancel a running task |

### Chat

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/chat` | Smart router (conversational or task) |
| `GET` | `/api/chat/{id}/stream` | Stream conversational LLM response |

### Approvals (HITL)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/approvals/pending` | List pending approvals |
| `POST` | `/api/approvals/{id}/approve` | Approve an operation |
| `POST` | `/api/approvals/{id}/reject` | Reject an operation |
| `GET` | `/api/approvals/history` | Approval audit trail |
| `GET` | `/api/approvals/stats` | Approval statistics |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | System health check |
| `GET` | `/api/config` | Non-sensitive configuration |
| `GET` | `/api/analytics/overview` | Analytics dashboard data |
| `POST` | `/api/services/{name}/start` | Start a service |
| `POST` | `/api/services/{name}/stop` | Stop a service |

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run specific module
pytest tests/test_state_manager.py -v

# Run web tests
pytest tests/web/ -v
```

Tests use `pytest-asyncio` for async testing, real Redis integration tests (auto-skipped if unavailable), and mock agents for isolated unit tests.

---

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/ARCHITECTURE.md) | System design and data flow |
| [Phase 1 Guide](docs/PHASE_1_USAGE.md) | State management with Redis |
| [Phase 2 Guide](docs/PHASE_2_GUIDE.md) | Intelligent routing and summarization |
| [Phase 3 Guide](docs/PHASE_3_GUIDE.md) | Human-in-the-Loop safety system |
| [Phase 4 Guide](docs/PHASE_4_ARCHITECTURE.md) | Command Center web interface |
| [Agent Integration](docs/EXISTING_AGENTS.md) | How external agents are integrated |

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **LLM** | Ollama | Local inference, zero cost |
| **Orchestration** | LangGraph | Stateful graph execution with conditional edges |
| **State** | Redis | Shared blackboard with TTL and connection pooling |
| **API** | FastAPI | Async REST API with auto-generated OpenAPI docs |
| **Validation** | Pydantic v2 | Type-safe models on every boundary |
| **Frontend** | Vanilla JS + SSE | Real-time streaming, no framework overhead |
| **Templates** | Jinja2 | Server-rendered HTML with autoescape |
| **CLI** | Click + Rich | Beautiful terminal interface |
| **Testing** | pytest + pytest-asyncio | Async-first test suite |

---

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for your changes
4. Ensure all tests pass (`pytest tests/ -v`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Code Standards
- Python: PEP 8, type hints, async/await for all I/O
- Pydantic models for all data validation
- Tests for all new functionality (>80% coverage target)

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## Acknowledgements

- [LangGraph](https://langchain-ai.github.io/langgraph/) — graph-based orchestration framework
- [Ollama](https://ollama.com) — local LLM runtime
- [FastAPI](https://fastapi.tiangolo.com) — modern async Python web framework
- [Redis](https://redis.io) — in-memory data store

---

<div align="center">

**Built with local AI. No cloud. No cost. Full privacy.**

[Report Bug](https://github.com/yashasviudayan-py/the-orchestrator/issues) · [Request Feature](https://github.com/yashasviudayan-py/the-orchestrator/issues)

</div>
