# Existing Agent Integration Guide

This document describes the three existing agent projects that The Orchestrator will integrate with.

---

## Project 1: Research Agent

### Location
```
/Users/yashasviudayan/local-research-agent
```

### Type
**Dual-interface application**: CLI + Web API

### Architecture
- **Framework**: LangGraph StateGraph pipeline
- **LLM**: Ollama (Llama 3.1)
- **Search**: DuckDuckGo
- **Scraper**: Crawl4AI (async)
- **API**: FastAPI + Server-Sent Events (SSE)

### Entry Points

#### 1. CLI Mode
```bash
cd /Users/yashasviudayan/local-research-agent
python main.py "research topic"
python main.py -v --num-queries 5 --top 5 "quantum computing"
```

#### 2. Web API Mode
```bash
# Start server
cd /Users/yashasviudayan/local-research-agent
python run_web.py  # Runs on http://localhost:8000

# API Endpoints
POST   /api/research              # Start research job
GET    /api/research/{id}/stream  # SSE progress stream
GET    /api/reports               # List all reports
GET    /api/reports/{id}          # Get report content
DELETE /api/reports/{id}          # Delete report
GET    /api/health                # Ollama health check
```

#### 3. Direct Python Import
```python
# From main.py
from searcher import DeepSearcher, SearcherConfig
from scraper import DeepFetcher, FetcherConfig

async def run_research(
    topic: str,
    searcher_config: SearcherConfig,
    fetcher_config: FetcherConfig,
    progress_callback=None,
) -> dict[str, Any]:
    """
    Returns:
        {
            "topic": str,
            "urls": list[str],
            "scraped_content": dict[str, str],
            "errors": dict[str, str],
            "elapsed_ms": float
        }
    """
```

### Output Format
- **Markdown reports** saved to `reports/` directory
- **Structured state** with URLs, scraped content, and errors
- **Progress events** via callback or SSE stream

### Dependencies
```
langgraph>=1.0.0
ollama>=0.6.0
ddgs>=9.0.0
crawl4ai>=0.8.0
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
```

### Integration Strategy for Orchestrator
**Recommended**: HTTP API calls to local server
- **Pros**: Isolated process, existing infrastructure, SSE progress tracking
- **Cons**: Need to ensure server is running

**Alternative**: Direct Python import
- **Pros**: Same process, programmatic control
- **Cons**: Shared dependencies, context management

---

## Project 2: PR-Agent

### Location
```
/Users/yashasviudayan/PR-Agent/repo-maintainer
```

### Type
**Webhook-driven service** + **CLI agent**

### Architecture
- **Listener**: FastAPI webhook server
- **Agent**: Orchestrator (scan → fix → commit → PR)
- **Scanner**: Ollama for file identification
- **Git**: GitHub CLI (`gh`) for PR creation

### Entry Points

#### 1. Webhook Server
```bash
cd /Users/yashasviudayan/PR-Agent/repo-maintainer
python listener.py  # Runs on http://0.0.0.0:8000

# Webhook endpoint
POST /webhook  # Receives GitHub issue webhooks
```

#### 2. Direct Agent CLI
```bash
cd /Users/yashasviudayan/PR-Agent/repo-maintainer
python agent.py "Fix login bug" "Description of issue"
```

#### 3. Direct Python Import
```python
# From agent.py
def run_agent(title: str, body: str):
    """
    Workflow:
    1. find_relevant_file(title) → target_file
    2. git checkout -b fix-{target_file}
    3. generate_fix(target_file, title, body) → Ollama
    4. git add, commit, push
    5. gh pr create
    """
```

### Workflow
1. **Identify file**: Uses scanner.py + Ollama to find relevant file
2. **Create branch**: `git checkout -b fix-{filename}`
3. **Generate fix**: Ollama generates code fix
4. **Commit & Push**: Git operations
5. **Create PR**: `gh pr create` via GitHub CLI

### Output Format
- **Git commits** on new branch
- **GitHub Pull Request** created via `gh` CLI
- **Console output** with progress logs

### Dependencies
```
fastapi>=0.128.0
uvicorn>=0.40.0
ollama>=0.6.0
# Plus: git, gh (GitHub CLI) - system dependencies
```

### Integration Strategy for Orchestrator
**Recommended**: Direct Python function call
- **Pros**: Synchronous operation, full control
- **Cons**: Need to be in correct git repo directory

**Alternative**: Subprocess call
- **Pros**: Isolated, clear separation
- **Cons**: Need to manage working directory

---

## Project 3: Context Core

### Location
```
/Users/yashasviudayan/Context Core
```

### Type
**CLI application** + **Python library**

### Architecture
- **Vector DB**: ChromaDB (local)
- **Embeddings**: Ollama + nomic-embed-text
- **LLM Chat**: Ollama + any chat model
- **CLI**: Click framework
- **Background**: Watchdog file monitoring, clipboard, zsh history

### Entry Points

#### 1. CLI Commands
```bash
cd "/Users/yashasviudayan/Context Core"
source .venv/bin/activate

# Search
vault search "database connection" -n 20 --min-score 0.5

# Chat (RAG)
vault chat "explain the auth system"
vault chat -i  # Interactive REPL

# Ingest
vault ingest ~/Projects/my-app
vault add "Some text" -t tag1,tag2

# Background watcher
vault watch add ~/Projects
vault watch start

# Stats
vault stats
vault peek -n 10
```

#### 2. Direct Python Import
```python
from context_core.vault import Vault
from context_core.search import search_vault
from context_core.rag import RAGPipeline
from context_core.security import SecretDetector
from context_core.config import VaultConfig, DEFAULT_CONFIG

# Semantic search
vault = Vault()
results = search_vault(
    vault,
    query="authentication",
    n_results=10,
    source_type="file",
    file_extension=".py",
    min_similarity=0.5
)

# RAG chat
pipeline = RAGPipeline(vault, config=DEFAULT_CONFIG)
response = pipeline.query(
    query_text="How does auth work?",
    model="llama3.1",
    history=[]
)

# Secret detection (CRITICAL for Orchestrator)
detector = SecretDetector()
has_secrets = detector.contains_secret(text)
matched = detector.get_matched_patterns(text)
scan_result = detector.scan(text)
# Returns: {"matched_patterns": [...], "descriptions": [...]}
```

### Core Modules

| Module | Purpose | Key Functions/Classes |
|--------|---------|----------------------|
| `vault.py` | ChromaDB vector store | `Vault()` - upsert, query, delete |
| `search.py` | Semantic search | `search_vault(vault, query, ...)` |
| `rag.py` | RAG pipeline | `RAGPipeline.query()`, `.query_stream()` |
| `security.py` | **Secret detection** | `SecretDetector.contains_secret()`, `.scan()` |
| `ingest.py` | File ingestion | Document creation, chunking |
| `ollama_client.py` | Ollama API wrapper | `chat()`, `chat_stream()`, `list_models()` |
| `watcher/` | Background monitoring | File, clipboard, history watchers |

### Secret Detection Patterns (CRITICAL)
The `SecretDetector` class detects:
- API keys (generic, Google, Stripe)
- Passwords
- Bearer tokens
- AWS credentials
- Private keys (RSA, EC, SSH)
- JWT tokens
- GitHub tokens (PAT, OAuth)
- Slack tokens
- Database URLs with credentials
- Environment variables with secrets

### Output Format
- **SearchResult**: `document_id`, `content`, `similarity`, `metadata`
- **ChatResponse**: `content`, `model`, `context_ids`, `context_count`
- **Secret Scan**: `{"matched_patterns": list, "descriptions": list}`

### Dependencies
```
chromadb>=1.0.0
click>=8.1.0
rich>=13.0.0
watchdog>=4.0.0
httpx>=0.27.0
```

### Integration Strategy for Orchestrator
**Recommended**: Direct Python import
- **Pros**: Same Python ecosystem, programmatic API, secret filtering integration
- **Cons**: Need to manage virtual environment or merge dependencies

**Critical for Orchestrator**:
- **MUST use `SecretDetector`** before passing any output between agents
- Installed via: `pip install -e "/Users/yashasviudayan/Context Core"`

---

## Integration Summary for The Orchestrator

### Recommended Integration Approach

```python
# Phase 1: The Blackboard - State Schema
class OrchestratorState(TypedDict):
    task_id: str
    objective: str

    # Agent routing
    current_agent: Optional[str]
    iteration: int

    # Research Agent (Project 1)
    research_query: Optional[str]
    research_results: Optional[dict]  # From run_research()

    # Context Core (Project 3)
    context_query: Optional[str]
    context_results: Optional[list]  # SearchResult objects
    rag_response: Optional[str]

    # PR-Agent (Project 2)
    pr_title: Optional[str]
    pr_body: Optional[str]
    pr_url: Optional[str]

    # Security & Control
    secrets_detected: bool
    requires_approval: bool
    approved: Optional[bool]

    errors: list[str]
```

### Agent Interface Wrappers (Phase 1)

#### Research Agent Interface
```python
# src/agents/research.py
import httpx
from typing import Dict, Any

class ResearchAgentInterface:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url

    async def research(self, topic: str) -> Dict[str, Any]:
        """Trigger research via HTTP API"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/research",
                json={"topic": topic}
            )
            return response.json()
```

#### Context Core Interface
```python
# src/agents/context.py
import sys
sys.path.insert(0, "/Users/yashasviudayan/Context Core/src")

from context_core.vault import Vault
from context_core.search import search_vault
from context_core.rag import RAGPipeline
from context_core.security import SecretDetector

class ContextCoreInterface:
    def __init__(self):
        self.vault = Vault()
        self.pipeline = RAGPipeline(self.vault)
        self.secret_detector = SecretDetector()

    def search(self, query: str, **kwargs):
        return search_vault(self.vault, query, **kwargs)

    def chat(self, query: str, model: str = "llama3.1"):
        return self.pipeline.query(query, model)

    def check_secrets(self, text: str) -> dict:
        """CRITICAL: Use before passing data between agents"""
        return self.secret_detector.scan(text)
```

#### PR-Agent Interface
```python
# src/agents/pr_agent.py
import subprocess
import os

class PRAgentInterface:
    def __init__(self, agent_path: str):
        self.agent_path = agent_path

    def create_pr(self, title: str, body: str, repo_path: str):
        """Trigger PR creation via subprocess"""
        original_cwd = os.getcwd()
        try:
            os.chdir(repo_path)
            result = subprocess.run(
                ["python", f"{self.agent_path}/agent.py", title, body],
                capture_output=True,
                text=True
            )
            return result.stdout
        finally:
            os.chdir(original_cwd)
```

---

## Environment Variables (.env)

```bash
# Project Paths
RESEARCH_AGENT_PATH=/Users/yashasviudayan/local-research-agent
CONTEXT_CORE_PATH=/Users/yashasviudayan/Context Core
PR_AGENT_PATH=/Users/yashasviudayan/PR-Agent/repo-maintainer

# Research Agent (if using HTTP API)
RESEARCH_AGENT_URL=http://localhost:8000

# Ollama (shared by all projects)
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b-instruct-q8_0

# Context Core
CONTEXT_CORE_VENV=/Users/yashasviudayan/Context Core/.venv
CHROMA_DATA_PATH=/Users/yashasviudayan/Context Core/chroma_data

# GitHub (for PR-Agent)
GITHUB_TOKEN=your_github_token
GITHUB_USERNAME=yashasviudayan-py
```

---

## Critical Security Requirements

### 1. Secret Filtering (MANDATORY)
All agent outputs MUST pass through Context Core's `SecretDetector` before:
- Storing in shared state (Redis)
- Passing to another agent
- Logging or displaying to user

```python
# Example enforcement
def sanitize_agent_output(output: str) -> tuple[str, bool]:
    detector = SecretDetector()
    scan_result = detector.scan(output)

    if scan_result["matched_patterns"]:
        # Log warning
        logger.warning(
            f"Secrets detected: {scan_result['descriptions']}"
        )
        return output, True  # secrets_detected=True

    return output, False
```

### 2. Max Iterations Guard (MANDATORY)
Prevent infinite loops between agents:

```python
MAX_ITERATIONS = 10

if state["iteration"] >= MAX_ITERATIONS:
    logger.error("Max iterations reached")
    return END
```

### 3. Context Window Management
Summarize agent outputs before passing to next agent to prevent context overflow.

---

## Next Steps for Phase 1

1. **Install Context Core as dependency**:
   ```bash
   cd "/Users/yashasviudayan/The Orchestrator"
   pip install -e "/Users/yashasviudayan/Context Core"
   ```

2. **Create agent interface wrappers** in `src/agents/`:
   - `research.py` - ResearchAgentInterface
   - `context.py` - ContextCoreInterface
   - `pr_agent.py` - PRAgentInterface

3. **Implement secret filtering** in all state operations

4. **Test individual agent integrations** before building the orchestrator

---

## Dependencies Summary

The Orchestrator will need:
- All Research Agent dependencies (if using direct import)
- Context Core as installed package
- httpx for HTTP calls to Research Agent API
- subprocess for PR-Agent execution

See [pyproject.toml](../pyproject.toml) and [requirements.txt](../requirements.txt) for full list.
