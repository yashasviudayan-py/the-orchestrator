
# Phase 1 Usage Guide

Complete guide for using Phase 1 (The Blackboard) implementation.

## Overview

Phase 1 provides:
- **Redis-based state management** for task persistence
- **Agent interface wrappers** for Research, Context Core, and PR-Agent
- **LangGraph orchestrator** with routing logic
- **Secret filtering** integration from Context Core
- **Comprehensive error handling** and logging

## Prerequisites

### 1. Start Required Services

```bash
# Redis
redis-server

# Ollama
ollama serve

# Research Agent API (optional, if using HTTP mode)
cd /Users/yashasviudayan/local-research-agent
python run_web.py
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your paths and settings
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt

# Install Context Core as editable package
pip install -e "/Users/yashasviudayan/Context Core"
```

## Quick Start

### Basic Usage

```python
import asyncio
from dotenv import load_dotenv

from state.redis_client import get_redis_client
from state.manager import StateManager
from agents import (
    ResearchAgentInterface,
    ContextCoreInterface,
    PRAgentInterface,
)
from orchestrator import OrchestratorGraph
from config import get_cached_settings

async def main():
    # Load configuration
    load_dotenv()
    settings = get_cached_settings()

    # Initialize Redis
    redis_client = get_redis_client(
        host=settings.redis_host,
        port=settings.redis_port,
    )
    await redis_client.connect()

    # Initialize State Manager
    state_manager = StateManager(redis_client)

    # Initialize Agents
    research_agent = ResearchAgentInterface(
        base_url=settings.research_agent_url
    )
    context_agent = ContextCoreInterface(
        context_core_path=settings.context_core_path
    )
    pr_agent = PRAgentInterface(
        agent_path=settings.pr_agent_path
    )

    # Initialize Orchestrator
    orchestrator = OrchestratorGraph(
        research_agent=research_agent,
        context_agent=context_agent,
        pr_agent=pr_agent,
        llm_base_url=settings.ollama_base_url,
        llm_model=settings.ollama_model,
    )

    # Run a task
    result = await orchestrator.run(
        objective="Add dark mode toggle to React app",
        user_context={"repo_path": "/path/to/repo"},
        max_iterations=10,
    )

    print(f"Task completed: {result.status}")
    print(f"Final output:\n{result.final_output}")

    # Cleanup
    await redis_client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
```

## Component Usage

### 1. State Management

```python
from state.manager import StateManager
from state.redis_client import get_redis_client

# Connect to Redis
redis_client = get_redis_client()
await redis_client.connect()

# Create state manager
state_manager = StateManager(redis_client)

# Create a task
task = await state_manager.create_task(
    objective="Add user authentication",
    user_context={"repo_path": "."},
    max_iterations=10,
)

# Update task
task.status = TaskStatus.RUNNING
await state_manager.update_task(task)

# Get task
task = await state_manager.get_task(task_id)

# List tasks
tasks = await state_manager.list_tasks(status=TaskStatus.RUNNING)

# Get statistics
stats = await state_manager.get_stats()
```

### 2. Agent Interfaces

#### Research Agent

```python
from agents import ResearchAgentInterface

research_agent = ResearchAgentInterface(
    base_url="http://localhost:8000"
)

# Check health
is_healthy = await research_agent.health_check()

# Execute research
result = await research_agent.execute({
    "topic": "JWT authentication best practices"
})

print(result["summary"])
print(result["key_findings"])
```

#### Context Core

```python
from agents import ContextCoreInterface

context_agent = ContextCoreInterface(
    context_core_path="/Users/yashasviudayan/Context Core"
)

# Semantic search
result = await context_agent.execute({
    "query": "authentication implementation",
    "n_results": 10,
    "min_similarity": 0.5,
})

print(f"Found {len(result['relevant_docs'])} relevant docs")
print(f"Has prior work: {result['has_prior_work']}")

# RAG chat
result = await context_agent.execute({
    "chat_query": "How did we implement auth before?",
    "model": "llama3.1:8b-instruct-q8_0",
})

print(result["summary"])

# Secret detection (CRITICAL)
result = await context_agent.execute({
    "check_secrets": "API_KEY=sk_test_123456"
})

if result["has_secrets"]:
    print(f"⚠️  Secrets detected: {result['descriptions']}")
```

#### PR-Agent

```python
from agents import PRAgentInterface

pr_agent = PRAgentInterface(
    agent_path="/Users/yashasviudayan/PR-Agent/repo-maintainer"
)

# Create PR
result = await pr_agent.execute({
    "title": "Add JWT authentication",
    "body": "Implements secure JWT-based authentication",
    "repo_path": "/path/to/repo",
})

if result["success"]:
    print(f"✓ PR created: {result['pr_url']}")
else:
    print(f"✗ PR failed: {result['error']}")
```

### 3. Orchestrator Graph

```python
from orchestrator import OrchestratorGraph

orchestrator = OrchestratorGraph(
    research_agent=research_agent,
    context_agent=context_agent,
    pr_agent=pr_agent,
    llm_base_url="http://localhost:11434",
    llm_model="llama3.1:8b-instruct-q8_0",
)

# Run complete workflow
result = await orchestrator.run(
    objective="Add email verification to signup",
    user_context={"repo_path": "/path/to/repo"},
)

# Stream progress (for UI integration)
async for state in orchestrator.stream(
    objective="Implement password reset",
):
    print(f"Iteration {state.iteration}: {state.current_agent}")

# Visualize graph
mermaid = orchestrator.get_graph_visualization()
print(mermaid)
```

## Error Handling

### Retry Logic

```python
try:
    result = await research_agent.execute(task_input)
except AgentTimeoutError as e:
    # Handle timeout
    logger.error(f"Agent timed out: {e}")
except AgentConnectionError as e:
    # Handle connection failure
    logger.error(f"Cannot connect to agent: {e}")
except AgentError as e:
    # Handle general agent error
    logger.error(f"Agent failed: {e}")
```

### Max Iterations Safeguard

```python
# Automatically enforced by orchestrator
result = await orchestrator.run(
    objective="Complex task",
    max_iterations=10,  # Will stop after 10 iterations
)

if result.iteration >= result.max_iterations:
    print("⚠️  Max iterations reached - task incomplete")
```

## Security

### Secret Filtering

**CRITICAL**: All agent outputs MUST pass through secret filtering:

```python
# Filter before passing between agents
text = agent_output["content"]
filtered, had_secrets = context_agent.filter_secrets(text)

if had_secrets:
    logger.warning("Secrets detected and filtered")
    # Use filtered text instead of original
```

### Secret Detection Patterns

Context Core detects:
- API keys (AWS, Google, Stripe, etc.)
- Passwords and bearer tokens
- Private keys (RSA, EC, SSH)
- JWT tokens
- GitHub/Slack tokens
- Database URLs with credentials
- Environment variables with secrets

## Monitoring

### Logging

```python
from logging_config import setup_logging

# Configure logging
setup_logging(
    level="INFO",
    log_file=Path("logs/orchestrator.log"),
    detailed=True,  # Include filename and line number
)
```

### State Inspection

```python
# Get task details
task = await state_manager.get_task(task_id)

print(f"Status: {task.status}")
print(f"Current agent: {task.current_agent}")
print(f"Iteration: {task.iteration}/{task.max_iterations}")
print(f"Errors: {len(task.errors)}")

# Get messages
messages = await state_manager.get_messages(task_id, limit=10)
for msg in messages:
    print(f"[{msg.agent_name}] {msg.message_type}: {msg.content}")
```

## Troubleshooting

### Redis Connection Issues

```bash
# Check if Redis is running
redis-cli ping
# Should return: PONG

# Check Redis logs
tail -f /usr/local/var/log/redis.log  # macOS
```

### Ollama Connection Issues

```bash
# Check if Ollama is running
curl http://localhost:11434/api/version

# Check models
ollama list

# Pull missing models
ollama pull llama3.1:8b-instruct-q8_0
ollama pull nomic-embed-text
```

### Agent Connection Issues

```bash
# Research Agent
curl http://localhost:8000/api/health

# Context Core
cd "/Users/yashasviudayan/Context Core"
source .venv/bin/activate
python -c "from context_core.vault import Vault; v = Vault(); print('OK')"

# PR-Agent
ls -la "/Users/yashasviudayan/PR-Agent/repo-maintainer/agent.py"
```

## Performance Tips

1. **Connection Pooling**: Redis client uses connection pooling by default (max 10 connections)

2. **TTL Management**: Tasks expire after 1 hour by default. Extend if needed:
   ```python
   await state_manager.extend_ttl(task_id, seconds=7200)  # 2 hours
   ```

3. **Cleanup**: Regularly clean up completed tasks:
   ```python
   deleted = await state_manager.cleanup_completed(older_than_seconds=86400)
   print(f"Cleaned up {deleted} old tasks")
   ```

4. **Agent Caching**: Context Core uses ChromaDB caching for semantic search

## Next Steps

Phase 1 is complete! Ready for:
- **Phase 2**: Add supervisor routing logic with Ollama
- **Phase 3**: Implement HITL gate with FastAPI
- **Phase 4**: Build Commander CLI with Click + Rich

## Support

For issues or questions:
1. Check logs: `logs/orchestrator.log`
2. Run demo: `python examples/phase1_demo.py`
3. Review tests: `pytest tests/`
