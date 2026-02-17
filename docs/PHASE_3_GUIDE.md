# Phase 3: The HITL Gate - Human-in-the-Loop Safety Checks

## Overview

Phase 3 introduces **Human-in-the-Loop (HITL)** approval gates that require explicit user approval before executing risky operations. This ensures safety and control over critical actions like code execution, git operations, and PR creation.

## Components

### 1. Risk Classification System

Operations are classified into 4 risk levels:

```python
class RiskLevel(Enum):
    LOW = "low"          # No approval needed (read operations)
    MEDIUM = "medium"     # Approval recommended (non-destructive writes)
    HIGH = "high"         # Approval required (destructive operations)
    CRITICAL = "critical" # Always requires approval (irreversible actions)
```

### 2. Operation Types

Supported operation types with automatic risk classification:

| Operation Type | Risk Level | Requires Approval? |
|---|---|---|
| `AGENT_CALL` (Research/Context) | LOW | No |
| `FILE_WRITE` | MEDIUM | Yes |
| `GIT_COMMIT` | MEDIUM | Yes |
| `PR_CREATE` | MEDIUM | Yes |
| `API_CALL` | MEDIUM | Yes |
| `CODE_EXECUTION` | HIGH | Yes |
| `FILE_DELETE` | HIGH | Yes |
| `GIT_PUSH` | HIGH | Yes |
| `NETWORK_REQUEST` | HIGH | Yes |
| `GIT_FORCE_PUSH` | CRITICAL | Yes |
| `GIT_BRANCH_DELETE` | CRITICAL | Yes |

### 3. Approval Manager

Manages the lifecycle of approval requests:

- Creates approval requests with automatic risk classification
- Blocks execution until approval/rejection/timeout
- Tracks pending and historical approvals
- Provides statistics and audit trail

### 4. FastAPI Server

REST API for managing approvals:

- `POST /approvals` - Create approval request (blocks until decided)
- `GET /approvals/pending` - List pending requests
- `GET /approvals/{id}` - Get specific request
- `POST /approvals/{id}/approve` - Approve request
- `POST /approvals/{id}/reject` - Reject request
- `GET /approvals/history` - View history
- `GET /approvals/stats` - Get statistics
- `DELETE /approvals/history` - Clear old history

### 5. Terminal UI

Interactive CLI for reviewing approvals:

```bash
# List pending approvals
python -m src.api.terminal_ui list

# Review all pending approvals interactively
python -m src.api.terminal_ui review

# Show approval history
python -m src.api.terminal_ui history

# Show statistics
python -m src.api.terminal_ui stats

# Run interactive monitoring mode
python -m src.api.terminal_ui interactive
```

## Usage

### Basic Approval Flow

```python
import asyncio
from src.api.approval_manager import get_approval_manager
from src.api.approval import OperationType

async def main():
    manager = get_approval_manager()

    # Request approval (blocks until decided or timeout)
    response = await manager.request_approval(
        operation_type=OperationType.GIT_PUSH,
        description="Push changes to main branch",
        details={"branch": "main", "commits": 3},
        task_id="task-123",
        agent_name="pr",
        timeout=300,  # 5 minutes
    )

    if response.approved:
        print(f"✓ Approved: {response.note}")
        # Proceed with operation
    else:
        print(f"✗ Rejected: {response.note}")
        # Cancel operation

asyncio.run(main())
```

### Integrating with Orchestrator

#### Option 1: Use HITL-Enhanced Graph

```python
from src.orchestrator import EnhancedOrchestratorGraph, create_hitl_enabled_graph
from src.agents import ResearchAgentInterface, ContextCoreInterface, PRAgentInterface

# Create agents
research = ResearchAgentInterface("http://localhost:8000")
context = ContextCoreInterface("/path/to/context-core")
pr_agent = PRAgentInterface("/path/to/pr-agent")

# Create HITL-enabled graph
orchestrator = create_hitl_enabled_graph(
    base_graph_class=EnhancedOrchestratorGraph,
    enable_hitl=True,  # Enable HITL approval gates
    research_agent=research,
    context_agent=context,
    pr_agent=pr_agent,
)

# Run with HITL protection
result = await orchestrator.run(
    objective="Add authentication to React app",
    user_context={"repo_path": "/path/to/repo"},
)
```

#### Option 2: Manual Integration

```python
from src.orchestrator.hitl_integration import HITLGate
from src.api.approval import OperationType

# Create HITL gate
hitl_gate = HITLGate(enabled=True)

# Check approval before risky operation
approved = await hitl_gate.check_approval(
    operation_type=OperationType.PR_CREATE,
    description="Create PR with authentication feature",
    task_state=task_state,
    details={"files_changed": 5},
)

if approved:
    # Execute PR agent
    await pr_agent.execute(...)
```

### Starting the Approval Server

```bash
# Start FastAPI approval server
cd /Users/yashasviudayan/The\ Orchestrator
python -m src.api.server

# Server runs on http://localhost:8001
# API docs at http://localhost:8001/docs
```

### Using the Terminal UI

#### Interactive Mode (Recommended)

```bash
# Run interactive monitoring mode
python -m src.api.terminal_ui interactive

# This will:
# 1. Monitor for pending approval requests
# 2. Prompt you to review when requests arrive
# 3. Display rich formatted request details
# 4. Allow approve/reject with optional notes
```

#### Manual Commands

```bash
# List pending requests in a table
python -m src.api.terminal_ui list

# Review all pending requests
python -m src.api.terminal_ui review

# Show last 20 approval decisions
python -m src.api.terminal_ui history 20

# Show approval statistics
python -m src.api.terminal_ui stats
```

## Configuration

### Default Timeouts

Configure timeouts by risk level in `HITLConfig`:

```python
from src.orchestrator.hitl_integration import HITLConfig

# Default timeouts (seconds)
HITLConfig.TIMEOUT_BY_RISK = {
    RiskLevel.LOW: 60,        # 1 minute
    RiskLevel.MEDIUM: 300,     # 5 minutes
    RiskLevel.HIGH: 600,       # 10 minutes
    RiskLevel.CRITICAL: 900,   # 15 minutes
}
```

### Custom Risk Classification

Override risk levels for specific operation types:

```python
from src.api.approval import RiskClassifier, OperationType, RiskLevel

# Make API calls HIGH risk instead of MEDIUM
RiskClassifier.RISK_LEVELS[OperationType.API_CALL] = RiskLevel.HIGH
```

### Disable HITL for Development

```python
# Create orchestrator with HITL disabled
orchestrator = create_hitl_enabled_graph(
    base_graph_class=EnhancedOrchestratorGraph,
    enable_hitl=False,  # Disable for dev/testing
    ...
)

# Or create HITL gate disabled
hitl_gate = HITLGate(enabled=False)
```

## Approval Statistics

Get comprehensive statistics about approvals:

```python
from src.api.approval_manager import get_approval_manager

manager = get_approval_manager()
stats = manager.get_stats()

print(f"Pending: {stats['pending']}")
print(f"Total: {stats['total_history']}")
print(f"Approval Rate: {stats['approval_rate']:.1%}")
print(f"By Status: {stats['by_status']}")
print(f"By Risk: {stats['by_risk_level']}")
```

Output:
```
Pending: 2
Total: 47
Approval Rate: 89.4%
By Status: {'approved': 42, 'rejected': 5, 'timeout': 0}
By Risk: {'low': 0, 'medium': 30, 'high': 15, 'critical': 2}
```

## Approval History

View and manage approval history:

```python
from src.api.approval import ApprovalStatus

# Get last 10 approvals
history = manager.get_history(limit=10)

# Get only approved requests
approved = manager.get_history(status=ApprovalStatus.APPROVED)

# Get specific request
request = manager.get_request("request-id-123")

# Clear old history (older than 24 hours)
cleared = manager.clear_history(older_than_hours=24)
```

## REST API Examples

### Create Approval Request

```bash
curl -X POST http://localhost:8001/approvals \
  -H "Content-Type: application/json" \
  -d '{
    "operation_type": "git_push",
    "description": "Push to main branch",
    "details": {"branch": "main"},
    "task_id": "task-123",
    "agent_name": "pr",
    "timeout": 300
  }'
```

### List Pending Requests

```bash
curl http://localhost:8001/approvals/pending
```

### Approve Request

```bash
curl -X POST http://localhost:8001/approvals/abc-123/approve \
  -H "Content-Type: application/json" \
  -d '{"note": "Looks good to me"}'
```

### Reject Request

```bash
curl -X POST http://localhost:8001/approvals/abc-123/reject \
  -H "Content-Type: application/json" \
  -d '{"note": "Too risky, please review code first"}'
```

### Get History

```bash
# Last 10 requests
curl http://localhost:8001/approvals/history?limit=10

# Only approved requests
curl http://localhost:8001/approvals/history?status=approved
```

## Security Best Practices

1. **Always Enable HITL for Production**
   ```python
   orchestrator = create_hitl_enabled_graph(
       enable_hitl=True,  # Always True for production
       ...
   )
   ```

2. **Use Appropriate Timeouts**
   - SHORT (60s): Quick operations you're monitoring
   - MEDIUM (5m): Standard operations
   - LONG (15m): Critical operations requiring review

3. **Review History Regularly**
   - Check approval patterns
   - Identify frequently rejected operations
   - Adjust risk levels as needed

4. **Clear Old History**
   ```python
   # Clear approvals older than 30 days
   manager.clear_history(older_than_hours=30*24)
   ```

5. **Add Detailed Notes**
   - Always include approval/rejection reason
   - Helps with auditing and debugging
   - Future reference for similar operations

## Workflow Integration

### Full Orchestrator Workflow with HITL

```python
import asyncio
from src.orchestrator import create_hitl_enabled_graph, EnhancedOrchestratorGraph
from src.agents import ResearchAgentInterface, ContextCoreInterface, PRAgentInterface
from src.state.redis_client import get_redis_client
from src.config import get_cached_settings

async def main():
    settings = get_cached_settings()

    # Initialize Redis
    redis = get_redis_client(
        host=settings.redis_host,
        port=settings.redis_port,
    )
    await redis.connect()

    # Initialize agents
    research = ResearchAgentInterface(settings.research_agent_url)
    context = ContextCoreInterface(settings.context_core_path)
    pr_agent = PRAgentInterface(settings.pr_agent_path)

    # Create HITL-enabled orchestrator
    orchestrator = create_hitl_enabled_graph(
        base_graph_class=EnhancedOrchestratorGraph,
        enable_hitl=True,  # HITL protection enabled
        research_agent=research,
        context_agent=context,
        pr_agent=pr_agent,
    )

    # Run orchestration (will request approval before PR creation)
    result = await orchestrator.run(
        objective="Add OAuth2 authentication to the API",
        user_context={"repo_path": "/path/to/repo"},
    )

    print(f"Status: {result.status}")
    print(f"Output: {result.final_output}")

    await redis.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
```

## Troubleshooting

### Approval Request Times Out

**Problem**: Approval requests timeout before being reviewed

**Solutions**:
1. Increase timeout: `timeout=900` (15 minutes)
2. Run terminal UI in interactive mode for auto-notification
3. Use FastAPI endpoint to programmatically approve during testing

### No Pending Requests Showing

**Problem**: Terminal UI shows no pending requests

**Solutions**:
1. Check if approval server is running: `curl http://localhost:8001/health`
2. Verify HITL is enabled: `orchestrator.hitl_enabled`
3. Check if operation is classified as LOW risk (auto-approved)

### Low Risk Operations Requiring Approval

**Problem**: Read operations are asking for approval

**Solutions**:
1. Check risk classification: `RiskClassifier.classify(operation_type)`
2. Verify operation type is correct
3. Update risk mapping if needed

## Next Steps

- **Phase 4**: Commander CLI - Unified terminal interface for the entire system
- **Advanced HITL**: Batch approvals, approval policies, role-based approvals

## Related Documentation

- [Phase 1 Guide](PHASE_1_USAGE.md) - State Management
- [Phase 2 Guide](PHASE_2_GUIDE.md) - Intelligent Routing
- [Architecture](ARCHITECTURE.md) - System Architecture
- [Agent Integration](EXISTING_AGENTS.md) - External Agent Integration
