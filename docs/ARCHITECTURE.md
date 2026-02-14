# Architecture Documentation

## System Overview

The Orchestrator is a multi-agent system built on LangGraph that coordinates three specialized AI agents to accomplish complex software development tasks autonomously.

## Core Components

### 1. The Blackboard (Phase 1)
The shared state system that enables communication between agents.

**Technology**: LangGraph State + Redis

**Purpose**:
- Centralized data storage for agent communication
- Message passing between agents
- Context preservation across agent invocations
- Task status tracking

**Key Features**:
- Thread-safe read/write operations
- TTL-based cleanup
- Structured state schema
- Checkpoint support for rollback

### 2. The Router (Phase 2)
The supervisor node that orchestrates agent execution.

**Technology**: LangGraph Supervisor Pattern + Claude/Ollama

**Purpose**:
- Analyze user objectives
- Determine optimal agent sequence
- Route tasks to appropriate agents
- Synthesize agent outputs

**Decision Logic**:
```
User Input → Parse Intent → Route to Agent(s) → Collect Results → Synthesize → Output
```

**Routing Strategy**:
1. **Research-First**: For new features or unfamiliar patterns
2. **Context-First**: For tasks matching previous work
3. **Direct-to-PR**: For simple, well-defined changes
4. **Multi-Agent**: For complex tasks requiring all agents

### 3. The HITL Gate (Phase 3)
Human-in-the-loop safety layer for risky operations.

**Technology**: FastAPI + Inquirer.py

**Purpose**:
- Intercept potentially destructive operations
- Present actions for user approval
- Log all approvals/rejections
- Timeout handling for stuck workflows

**Protected Operations**:
- Code execution
- Git push/force-push
- File deletion
- External API calls
- Database modifications

### 4. The Commander CLI (Phase 4)
Unified terminal interface for the entire system.

**Technology**: Click + Rich

**Purpose**:
- Single entry point for all operations
- Beautiful terminal UI
- Progress tracking
- Interactive configuration

**Commands**:
```bash
orchestrator start <objective>     # Start a new task
orchestrator status                # View current task status
orchestrator config                # Configure agents and settings
orchestrator logs                  # View execution logs
orchestrator agents                # Manage agent connections
```

## Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                         User (CLI)                          │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    Commander/Router                         │
│                  (LangGraph Supervisor)                     │
└──────┬──────────────┬────────────────┬─────────────────────┘
       │              │                │
       ▼              ▼                ▼
┌──────────┐   ┌──────────┐    ┌──────────┐
│Research  │   │Context   │    │PR-Agent  │
│Agent     │   │Core      │    │          │
└────┬─────┘   └────┬─────┘    └────┬─────┘
     │              │               │
     └──────────────┼───────────────┘
                    │
                    ▼
        ┌────────────────────┐
        │   Shared State     │
        │  (Redis/LangGraph) │
        └────────────────────┘
```

## Agent Integration

### Research Agent Interface
```python
class ResearchAgentInterface:
    def query(self, topic: str, context: dict) -> ResearchResult:
        """Query the research agent for best practices"""
        pass
```

### Context Core Interface
```python
class ContextCoreInterface:
    def retrieve_context(self, query: str) -> ContextResult:
        """Retrieve relevant context and memory"""
        pass

    def store_context(self, data: dict) -> bool:
        """Store new context for future use"""
        pass
```

### PR-Agent Interface
```python
class PRAgentInterface:
    def create_pr(self, spec: PRSpec, research: ResearchResult, context: ContextResult) -> PR:
        """Create a pull request with code changes"""
        pass
```

## State Schema

```python
class OrchestratorState(TypedDict):
    objective: str
    current_agent: str
    iteration: int
    max_iterations: int
    research_results: Optional[ResearchResult]
    context_results: Optional[ContextResult]
    pr_results: Optional[PRResult]
    errors: List[str]
    requires_approval: bool
    approved: Optional[bool]
    final_output: Optional[str]
```

## Safety Mechanisms

### 1. Max Iteration Guard
Prevents infinite loops between agents.

```python
if state["iteration"] >= state["max_iterations"]:
    return "END"
```

### 2. Context Window Management
Commander summarizes agent outputs before passing to next agent.

### 3. Secret Filtering
All outputs pass through Context Core's secret filter before proceeding.

### 4. Approval Checkpoints
HITL gate intercepts risky operations for user approval.

## Error Handling

### Graceful Degradation
- If Claude API fails → fallback to Ollama
- If Redis fails → use in-memory state (warning logged)
- If agent fails → log error, continue with partial results

### Retry Logic
- 3 retries with exponential backoff for network errors
- Manual retry option for approval timeout
- Checkpoint restoration for catastrophic failures

## Scalability Considerations

### Current (Local)
- Single machine execution
- Local Redis instance
- Sequential agent execution

### Future (Distributed)
- Redis Cluster for distributed state
- Parallel agent execution
- Queue-based task distribution
- Multi-machine orchestration

## Security

### API Key Management
- Environment variables for sensitive data
- No hardcoded credentials
- Secret filtering from Context Core

### GitHub Access
- Scoped tokens (repo access only)
- No force-push to protected branches
- PR creation only (no direct commits)

### Code Execution
- HITL approval required
- Sandboxed execution environment (future)
- Input validation and sanitization

## Monitoring & Logging

### Log Levels
- DEBUG: All agent communications
- INFO: Task progress and routing decisions
- WARNING: Fallbacks and retries
- ERROR: Failures and exceptions

### Metrics (Future)
- Task completion time
- Agent utilization
- Success/failure rates
- Approval response times

## Testing Strategy

### Unit Tests
- Individual agent interfaces
- State management operations
- Routing logic

### Integration Tests
- Multi-agent workflows
- HITL approval flows
- Error recovery scenarios

### End-to-End Tests
- Complete user objectives
- Real agent integration
- CLI interface testing
