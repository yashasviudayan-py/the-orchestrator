# The Orchestrator

A **100% local** autonomous project manager that orchestrates multiple AI agents to accomplish complex software development tasks using Ollama.

![Status](https://img.shields.io/badge/Phase_1-Complete-brightgreen)
![Status](https://img.shields.io/badge/Phase_2-Complete-brightgreen)
![Status](https://img.shields.io/badge/Phase_3-Complete-brightgreen)
![Status](https://img.shields.io/badge/Phase_4-Complete-brightgreen)

## Overview

The Orchestrator is a meta-agent system that coordinates three specialized agents:
- **Research Agent** (Project 1): Finds best practices and implementation patterns
- **Context Core** (Project 3): Manages memory and context with secret filtering
- **PR-Agent** (Project 2): Writes code and creates pull requests

**Privacy-first**: Every component runs locally. No cloud APIs. No data leaves your machine. $0 cost.

## Current Status

✅ **Phase 1 Complete** - The Blackboard (State Management)
✅ **Phase 2 Complete** - The Router (Intelligent Routing)
✅ **Phase 3 Complete** - The HITL Gate (Human-in-the-Loop)
✅ **Phase 4 Complete** - The Command Center (Web Interface)

## The Build Plan: 4 Phases to Autonomy

### ✅ Phase 1: The Blackboard (COMPLETE)
**Focus**: Shared state management for multi-agent coordination

**Tech Stack**: LangGraph, Redis (Local), Pydantic

**Features Implemented**:
- ✓ Redis-based state persistence with connection pooling
- ✓ Pydantic schemas for type-safe state management
- ✓ CRUD operations for tasks and messages
- ✓ Agent interface wrappers (Research, Context Core, PR-Agent)
- ✓ LangGraph orchestrator with nodes and edges
- ✓ **Secret filtering** integration (critical security)
- ✓ **Max iterations safeguard** (prevents infinite loops)
- ✓ Error handling and logging
- ✓ Complete documentation and tests

📚 [View Phase 1 Documentation](docs/PHASE_1_USAGE.md)

### ✅ Phase 2: The Router (COMPLETE)
**Focus**: Intelligent agent routing with context management

**Tech Stack**: Ollama (Local LLM), LangGraph

**Features Implemented**:
- ✓ **Context Summarizer** - prevents context window overflow
- ✓ **Enhanced Supervisor** - intelligent routing decisions
- ✓ **3 Routing Strategies**:
  - Research-First (for new features)
  - Context-First (for refactoring)
  - Adaptive (LLM-powered, recommended)
- ✓ Decision history tracking with reasoning
- ✓ Confidence scoring for decisions
- ✓ Agent-optimized context creation
- ✓ Token estimation and management
- ✓ Smart retry logic

📚 [View Phase 2 Documentation](docs/PHASE_2_GUIDE.md)

### ✅ Phase 3: The HITL Gate (COMPLETE)
**Focus**: Human-in-the-Loop safety checks before risky operations

**Tech Stack**: FastAPI, Rich, Pydantic

**Features Implemented**:
- ✓ **Risk Classification System** - 4 levels (LOW, MEDIUM, HIGH, CRITICAL)
- ✓ **Approval Manager** - Lifecycle management with async/await
- ✓ **FastAPI Server** - REST API for approval operations
- ✓ **Terminal UI** - Rich-based interactive approval interface
- ✓ **HITL Integration** - Seamless orchestrator integration
- ✓ **Timeout Handling** - Configurable timeouts by risk level
- ✓ **Approval History** - Complete audit trail with statistics
- ✓ **Auto-Approval** - Low-risk operations auto-approved
- ✓ Complete documentation and tests

📚 [View Phase 3 Documentation](docs/PHASE_3_GUIDE.md)

### ✅ Phase 4: The Command Center (COMPLETE)
**Focus**: Unified web interface for the entire system

**Tech Stack**: FastAPI, Jinja2, Vanilla JS, SSE

**Features Implemented**:
- ✓ **Dashboard** - Real-time task submission and monitoring with SSE streaming
- ✓ **Visual HITL Approvals** - Beautiful web interface for approval management
- ✓ **Task History** - Complete execution history with filtering
- ✓ **Analytics** - Comprehensive metrics (tasks, agents, approvals, routing, performance)
- ✓ **Health Monitoring** - Real-time status for all 5 services (Research, Context, PR, Ollama, Redis)
- ✓ **Jet Black Design** - Apple SF Pro inspired minimalist UI
- ✓ **Live Updates** - SSE for progress, polling for health/approvals
- ✓ Complete documentation and tests

📚 [View Phase 4 Documentation](docs/PHASE_4_COMMAND_CENTER.md)

## The Workflow: How It Works

1. **Objective**: You tell the Commander: *"I want to add a dark-mode toggle to my React app using Tailwind."*

2. **Research (Project 1)**: The Commander triggers the Research Agent to find the best Tailwind dark-mode implementation.

3. **Memory (Project 3)**: It queries your Context Core to see if you've done this before or have specific styling rules saved.

4. **Action (Project 2)**: It passes the research and context to the PR-Agent to write the code and open the Pull Request.

## Important Things to Remember

- **Avoid "Infinite Loops"**: Agents can sometimes get stuck talking to each other. You must implement a "Max Iterations" safeguard in your LangGraph.

- **Shared Context is Key**: The Commander must be able to summarize the output of one agent before passing it to the next to keep the context window clean.

- **Security**: Since the Commander will have access to your terminal and GitHub, your Secret Filtering from Project 3 must be strictly enforced here.

## Project Structure

```
the-orchestrator/
├── src/
│   ├── orchestrator/       # Main orchestrator logic
│   ├── agents/             # Agent interfaces and wrappers
│   ├── state/              # Shared state management (Redis/LangGraph)
│   ├── cli/                # CLI interface (Phase 4)
│   └── api/                # FastAPI for HITL (Phase 3)
├── config/                 # Configuration files
├── tests/                  # Test files
└── docs/                   # Documentation
```

## Prerequisites

- **Python 3.10+**
- **[Ollama](https://ollama.com)** installed and running
- **Redis** (local instance)

```bash
# Install Ollama (macOS)
brew install ollama

# Pull required models
ollama pull llama3.1:8b-instruct-q8_0  # Main LLM
ollama pull nomic-embed-text           # Embeddings

# Start Ollama server
ollama serve

# Install Redis (macOS)
brew install redis

# Start Redis server
redis-server
```

## Getting Started

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/yashasviudayan-py/the-orchestrator.git
cd the-orchestrator

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install Context Core (required for secret filtering)
pip install -e "/Users/yashasviudayan/Context Core"

# 4. Configure environment
cp .env.example .env
# Edit .env with your agent paths

# 5. Start required services
redis-server &
ollama serve &
```

### Quick Start (Phase 2)

```python
import asyncio
from dotenv import load_dotenv

from state.redis_client import get_redis_client
from agents import (
    ResearchAgentInterface,
    ContextCoreInterface,
    PRAgentInterface,
)
from orchestrator import EnhancedOrchestratorGraph, RoutingStrategy
from config import get_cached_settings

async def main():
    load_dotenv()
    settings = get_cached_settings()

    # Initialize Redis
    redis_client = get_redis_client(
        host=settings.redis_host,
        port=settings.redis_port,
    )
    await redis_client.connect()

    # Initialize Agents
    research_agent = ResearchAgentInterface(settings.research_agent_url)
    context_agent = ContextCoreInterface(settings.context_core_path)
    pr_agent = PRAgentInterface(settings.pr_agent_path)

    # Initialize Phase 2 Orchestrator
    orchestrator = EnhancedOrchestratorGraph(
        research_agent=research_agent,
        context_agent=context_agent,
        pr_agent=pr_agent,
        routing_strategy=RoutingStrategy.ADAPTIVE,  # Let LLM decide
    )

    # Run orchestration
    result = await orchestrator.run(
        objective="Add dark mode toggle to React app",
        user_context={"repo_path": "/path/to/repo"},
    )

    print(f"Status: {result.status}")
    print(f"Output:\n{result.final_output}")

    # View routing decisions
    stats = orchestrator.get_supervisor_stats()
    print(f"\nDecisions made: {stats['total_decisions']}")
    print(f"Average confidence: {stats['avg_confidence']:.2f}")

    await redis_client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
```

### Quick Start (Phase 4 - Command Center)

```bash
# Start the Command Center web interface
uvicorn src.web.server:app --host 0.0.0.0 --port 8080

# Access the dashboard at:
# http://localhost:8080
```

**Features**:
- **Dashboard** (`/`) - Submit and monitor tasks in real-time
- **Approvals** (`/approvals`) - Review and approve risky operations
- **History** (`/history`) - View all past task executions
- **Analytics** (`/analytics`) - Performance metrics and insights

**Example**: Submit a task via web UI or API:
```bash
curl -X POST http://localhost:8080/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "objective": "Find best practices for Python async/await",
    "max_iterations": 10,
    "routing_strategy": "adaptive",
    "enable_hitl": true
  }'
```

### Run Demos

```bash
# Phase 1 Demo - State Management
python examples/phase1_demo.py

# Phase 2 Demo - Intelligent Routing
python examples/phase2_demo.py
```

### Run Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

## Features

### 🔒 Security
- **Secret Filtering**: Integrates Context Core's SecretDetector (15+ pattern types)
- **Safe Operations**: Max iterations safeguard prevents infinite loops
- **Input Validation**: Pydantic schemas validate all data
- **Error Boundaries**: Comprehensive error handling

### 🧠 Intelligent Routing
- **Adaptive Strategy**: LLM analyzes objective and chooses best approach
- **Research-First**: For new features and unfamiliar tech
- **Context-First**: For refactoring and similar past work
- **Decision History**: Track all routing decisions with reasoning

### 📦 Context Management
- **Automatic Summarization**: Prevents context window overflow
- **Token Estimation**: Monitors and manages token usage
- **Agent-Optimized**: Tailors context for each agent
- **Compression**: Intelligent compression using Ollama

### 🔄 State Management
- **Redis Persistence**: Durable task state with TTL
- **Message History**: Complete audit trail
- **CRUD Operations**: Create, read, update, delete tasks
- **Statistics**: Task analytics and monitoring

### 🔌 Agent Integration
- **Research Agent**: HTTP API integration
- **Context Core**: Direct Python import
- **PR-Agent**: Subprocess execution
- **Health Checks**: Monitor agent availability

## Documentation

- **[Phase 1 Usage Guide](docs/PHASE_1_USAGE.md)** - Complete Phase 1 documentation
- **[Phase 2 Guide](docs/PHASE_2_GUIDE.md)** - Intelligent routing and context management
- **[Architecture](docs/ARCHITECTURE.md)** - System architecture and design
- **[Agent Integration](docs/EXISTING_AGENTS.md)** - How agents are integrated

## Project Structure

```
the-orchestrator/
├── src/
│   ├── orchestrator/           # Main orchestrator logic
│   │   ├── graph.py           # Phase 1 basic graph
│   │   ├── graph_v2.py        # Phase 2 enhanced graph
│   │   ├── supervisor.py      # Intelligent routing
│   │   ├── summarizer.py      # Context management
│   │   ├── nodes.py           # Node implementations
│   │   └── edges.py           # Edge routing logic
│   ├── agents/                # Agent interfaces
│   │   ├── research.py        # Research Agent wrapper
│   │   ├── context.py         # Context Core wrapper
│   │   └── pr_agent.py        # PR-Agent wrapper
│   ├── state/                 # State management
│   │   ├── redis_client.py    # Redis connection
│   │   ├── manager.py         # State CRUD
│   │   └── schemas.py         # Pydantic models
│   ├── cli/                   # CLI (Phase 4)
│   ├── api/                   # FastAPI (Phase 3)
│   ├── config.py              # Configuration
│   └── logging_config.py      # Logging setup
├── config/                    # Configuration files
├── docs/                      # Documentation
├── examples/                  # Demo scripts
├── tests/                     # Test files
└── logs/                      # Log files
```

## Routing Strategies

### Adaptive (Recommended)
Let Ollama analyze the objective and choose the best approach automatically.

**Example**:
- "Fix typo" → Direct to PR
- "Add OAuth2" → Research first
- "Update login" → Check context first

### Research-First
Always start with research - best for new features and unfamiliar technologies.

### Context-First
Check existing codebase first - best for refactoring and similar past work.

## Performance

- **100% Local**: No API calls, no latency, no costs
- **Efficient**: Context summarization keeps token usage low
- **Fast**: Connection pooling and caching
- **Scalable**: Redis for distributed state (future)

## Contributing

Contributions welcome! This project is under active development.

## Roadmap

- [x] Phase 1: State Management (Redis + LangGraph)
- [x] Phase 2: Intelligent Routing (Supervisor + Summarizer)
- [x] Phase 3: HITL Gate (FastAPI + Approval UI)
- [ ] Phase 4: Commander CLI (Click + Rich)
- [ ] Future: Distributed orchestration, parallel agents

## Support

- 📖 [Documentation](docs/)
- 💬 [Issues](https://github.com/yashasviudayan-py/the-orchestrator/issues)
- 🎯 [Demos](examples/)

## License

MIT

---

**Built with ❤️ using 100% local AI** | No cloud, no costs, full privacy
