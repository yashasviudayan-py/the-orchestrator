# Claude Instructions for The Orchestrator

## Project Overview
This is a multi-agent orchestration system that coordinates three AI agents (Research Agent, Context Core, PR-Agent) to accomplish complex software development tasks autonomously.

## Build Phases
The project is built in 4 phases:
1. **Phase 1 (The Blackboard)**: Shared state with LangGraph + Redis
2. **Phase 2 (The Router)**: Supervisor node for agent routing
3. **Phase 3 (The HITL Gate)**: Human-in-the-loop safety checks
4. **Phase 4 (The Commander CLI)**: Unified terminal interface

## Critical Requirements

### Safety First
- **NEVER** skip the HITL (Human-in-the-Loop) gate for risky operations
- Always implement the "Max Iterations" safeguard (default: 10) in LangGraph
- Secret filtering from Context Core MUST be enforced for all outputs
- No destructive operations without explicit user approval

### Code Standards
- Use **async/await** for all I/O operations
- Use **Pydantic** for all data validation
- Use **type hints** throughout
- Follow **PEP 8** style guide
- Keep functions small and focused

### Testing Requirements
- Write tests for all new functionality
- Use pytest with asyncio support
- Maintain >80% code coverage
- Test both success and failure paths

### Dependencies
- **LLM**: Ollama (100% local, no API keys required)
- **State Management**: Redis (local)
- **Framework**: LangGraph
- **API**: FastAPI (Phase 3)
- **CLI**: Click + Rich (Phase 4)

### LLM Configuration
This project uses **Ollama exclusively** for all LLM operations:
- **Routing decisions**: Ollama determines which agent to call next
- **Agent operations**: All three existing agents use Ollama
- **No cloud APIs**: Everything runs locally, $0 cost
- **Privacy-first**: No data leaves your machine

## Project Structure
```
src/
├── orchestrator/    # Main orchestrator logic (LangGraph)
├── agents/          # Agent interfaces and wrappers
├── state/           # Shared state management (Redis)
├── cli/             # CLI interface (Phase 4)
└── api/             # FastAPI for HITL (Phase 3)
```

## Key Design Patterns

### Agent Communication
Agents communicate through the shared state (Redis) using structured messages:
```python
class AgentMessage(BaseModel):
    agent_name: str
    timestamp: datetime
    message_type: str
    content: dict
    metadata: dict
```

### State Schema
All state operations use the `TaskState` model:
```python
class TaskState(TypedDict):
    task_id: str
    objective: str
    status: TaskStatus
    current_agent: Optional[str]
    iteration: int
    messages: List[AgentMessage]
    context: dict
    errors: List[str]
```

### Error Handling
- Implement retry logic with exponential backoff for Ollama connection failures
- Log all errors with context
- Never fail silently
- Handle Ollama server downtime gracefully

## External Agent Integration
This project integrates with three external agent projects:
1. **Research Agent** (Project 1): Finds best practices
2. **Context Core** (Project 3): Manages memory and secrets
3. **PR-Agent** (Project 2): Writes code and creates PRs

Paths to these projects are configured in `.env` file.

## Environment Setup
1. **Start required services**:
   ```bash
   ollama serve        # Start Ollama server
   redis-server        # Start Redis server
   ```
2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Update agent paths in .env if needed
   ```
3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_state_manager.py
```

## Common Tasks

### Adding a New Agent Node
1. Define node function in `src/orchestrator/nodes.py`
2. Add node to graph in `src/orchestrator/graph.py`
3. Update state schema if needed
4. Add tests in `tests/test_nodes.py`

### Adding a New State Field
1. Update `TaskState` in `src/state/schemas.py`
2. Update Redis serialization logic
3. Add migration if needed
4. Update documentation

### Adding a New HITL Check (Phase 3)
1. Define check in `src/api/hitl.py`
2. Add to `require_approval_for` in config
3. Implement approval UI
4. Add tests

## Important Notes
- Context window management is critical - summarize before passing between agents
- Always version control the state schema
- Monitor Redis memory usage (implement TTL)
- Log all agent interactions for debugging

## When in Doubt
- Ask the user for clarification rather than making assumptions
- Prefer simple solutions over complex ones
- Follow the existing patterns in the codebase
- Check the documentation in `docs/` directory
