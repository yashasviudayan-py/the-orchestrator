# Phase 4: The Command Center - Architecture

## Overview

The Command Center is a comprehensive web-based dashboard that provides a unified interface for managing The Orchestrator and all three AI agents. It combines real-time task monitoring, visual approval workflow, agent health tracking, and analytics into a single, intuitive interface.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     Browser (Frontend)                          │
│  ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌─────────────────┐  │
│  │Dashboard │ │ Approvals │ │ History  │ │ Analytics/Agents│  │
│  └──────────┘ └───────────┘ └──────────┘ └─────────────────┘  │
│       ↕ SSE         ↕ WS         ↕ REST         ↕ REST         │
└─────────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────────┐
│              Unified FastAPI Server (Port 8080)                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Routes:                                                  │  │
│  │  • / → Dashboard page                                     │  │
│  │  • /approvals → Approvals page                           │  │
│  │  • /api/tasks → Task management (start, status, list)    │  │
│  │  • /api/tasks/{id}/stream → SSE progress updates         │  │
│  │  • /api/approvals → HITL approval operations             │  │
│  │  • /api/approvals/ws → WebSocket notifications           │  │
│  │  • /api/agents → Agent health and status                 │  │
│  │  • /api/stats → Analytics and metrics                    │  │
│  │  • /api/config → Configuration management                │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
            ↕           ↕           ↕           ↕
┌──────────────┐ ┌─────────────┐ ┌───────┐ ┌──────────────┐
│ Orchestrator │ │  Approval   │ │ Redis │ │ External     │
│   Graph      │ │  Manager    │ │ State │ │ Agents (3)   │
│  (Phase 2)   │ │  (Phase 3)  │ │(Phase1)│ │ Health Checks│
└──────────────┘ └─────────────┘ └───────┘ └──────────────┘
```

## Technology Stack

### Backend
- **FastAPI**: Unified web server
- **Server-Sent Events (SSE)**: Real-time task progress streaming
- **WebSocket**: Instant approval notifications
- **Pydantic**: Request/response validation
- **asyncio**: Concurrent task execution

### Frontend
- **Vanilla JavaScript**: No framework overhead
- **Modern CSS**: Grid, Flexbox, animations
- **EventSource API**: SSE client
- **WebSocket API**: Real-time notifications
- **Chart.js**: Analytics visualization (optional)

### Integration
- **EnhancedOrchestratorGraph** (Phase 2)
- **ApprovalManager** (Phase 3)
- **Redis** (Phase 1)
- **Research Agent API**
- **Context Core**
- **PR-Agent**

## Core Components

### 1. Unified Server (`src/web/server.py`)

Main FastAPI application that combines:
- Task orchestration endpoints
- HITL approval endpoints (from Phase 3)
- Agent monitoring
- Analytics and statistics
- Configuration management

**Key Features:**
- Background task execution using asyncio
- SSE streaming for progress updates
- WebSocket broadcasting for approvals
- Connection pooling for Redis
- Health checks for external agents

### 2. Task Management System

**Data Models:**
```python
class TaskRequest(BaseModel):
    objective: str
    user_context: dict = {}
    max_iterations: int = 10
    routing_strategy: RoutingStrategy = RoutingStrategy.ADAPTIVE
    enable_hitl: bool = True

class TaskInfo(BaseModel):
    task_id: str
    objective: str
    status: TaskStatus
    current_agent: Optional[str]
    iteration: int
    max_iterations: int
    created_at: datetime
    updated_at: datetime

class TaskProgressEvent(BaseModel):
    event_type: str  # "agent_start", "agent_complete", "iteration", "complete", "error"
    data: dict
```

**API Endpoints:**
- `POST /api/tasks` - Start new orchestration task
- `GET /api/tasks` - List all tasks
- `GET /api/tasks/{id}` - Get task details
- `GET /api/tasks/{id}/stream` - SSE progress stream
- `DELETE /api/tasks/{id}` - Cancel task

**SSE Events:**
```javascript
// Client receives real-time updates
event: agent_start
data: {"agent": "research", "iteration": 1}

event: agent_progress
data: {"message": "Found 15 URLs", "progress": 30}

event: agent_complete
data: {"agent": "research", "duration_ms": 12500}

event: approval_required
data: {"request_id": "abc-123", "operation": "pr_create"}

event: iteration
data: {"iteration": 2, "max": 10}

event: complete
data: {"status": "completed", "output": "..."}

event: error
data: {"message": "Agent timeout"}
```

### 3. Visual HITL Approval System

**Enhanced Approval Manager Integration:**
- Real-time approval notifications via WebSocket
- Visual approval cards with risk indicators
- Countdown timers for pending approvals
- Approval history with filtering

**WebSocket Protocol:**
```javascript
// Server broadcasts to all connected clients
{
  "type": "approval_required",
  "request": {
    "request_id": "abc-123",
    "operation_type": "git_push",
    "risk_level": "high",
    "description": "Push to main branch",
    "details": {...},
    "timeout_seconds": 300,
    "created_at": "2026-02-18T10:30:00Z"
  }
}

// Client sends decision
{
  "type": "approve",
  "request_id": "abc-123",
  "note": "Looks good"
}

// Server confirms
{
  "type": "approval_decided",
  "request_id": "abc-123",
  "approved": true
}
```

### 4. Agent Health Monitoring

**Monitored Agents:**
1. Research Agent (HTTP API)
2. Context Core (Python import)
3. PR-Agent (Subprocess)
4. Ollama (LLM)
5. Redis (State)

**Health Check System:**
```python
class AgentHealth(BaseModel):
    name: str
    status: str  # "healthy", "degraded", "down"
    last_check: datetime
    response_time_ms: Optional[int]
    error: Optional[str]
    details: dict

# Periodic health checks every 30 seconds
async def check_agent_health():
    # Check Research Agent API
    # Check Context Core
    # Check PR-Agent
    # Check Ollama
    # Check Redis
```

**API:**
- `GET /api/agents` - List all agents with health
- `GET /api/agents/{name}` - Get specific agent details
- `POST /api/agents/{name}/check` - Force health check

### 5. Analytics and Statistics

**Metrics Tracked:**
- Task execution statistics (success rate, avg duration)
- Agent usage patterns (call frequency, duration)
- Approval statistics (approval rate by operation type)
- Routing decisions (which strategy, which agent chosen)
- Error patterns and frequencies

**API:**
- `GET /api/stats/tasks` - Task statistics
- `GET /api/stats/approvals` - Approval statistics
- `GET /api/stats/agents` - Agent usage statistics
- `GET /api/stats/routing` - Routing decision analytics

## Frontend Pages

### 1. Dashboard (`/`)

**Layout:**
```
┌─────────────────────────────────────────────────┐
│  🎛️ The Orchestrator - Command Center          │
├─────────────────────────────────────────────────┤
│  [Dashboard] [Approvals] [History] [Analytics]  │
├─────────────────────────────────────────────────┤
│                                                 │
│  Agent Status:                                  │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ │
│  │ Res  │ │ Ctx  │ │  PR  │ │ Olm  │ │ Rds  │ │
│  │  ✓   │ │  ✓   │ │  ✓   │ │  ✓   │ │  ✓   │ │
│  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ │
│                                                 │
│  Start New Task:                                │
│  ┌────────────────────────────────────────────┐ │
│  │ What would you like to accomplish?        │ │
│  │                                            │ │
│  │ [Submit Task]                              │ │
│  └────────────────────────────────────────────┘ │
│                                                 │
│  Active Task: #task-123                         │
│  ┌────────────────────────────────────────────┐ │
│  │ 🔵 Running - Iteration 2/10                │ │
│  │ Current: Research Agent                    │ │
│  │ ▓▓▓▓▓░░░░░ 50%                            │ │
│  │                                            │ │
│  │ Progress:                                  │ │
│  │  ✓ Research (12.5s)                       │ │
│  │  → Context (in progress...)               │ │
│  │  ⏸ PR-Agent (pending approval)            │ │
│  └────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

**Features:**
- Real-time agent status indicators
- Live task progress with SSE
- Quick task launcher
- Active task visualization
- Recent tasks list

### 2. Approvals (`/approvals`)

**Layout:**
```
┌─────────────────────────────────────────────────┐
│  Pending Approvals (2)                          │
├─────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────┐ │
│  │ ⚠️ GIT_PUSH - HIGH RISK 🔴                 │ │
│  │                                            │ │
│  │ Push changes to main branch                │ │
│  │                                            │ │
│  │ Details:                                   │ │
│  │  • Branch: main                            │ │
│  │  • Commits: 3                              │ │
│  │  • Files: 12                               │ │
│  │                                            │ │
│  │ Timeout: ⏱️ 4:32 remaining                 │ │
│  │                                            │ │
│  │ Note: [________________]                   │ │
│  │                                            │ │
│  │ [✓ Approve]  [✗ Reject]                   │ │
│  └────────────────────────────────────────────┘ │
│                                                 │
│  History (Last 10)                              │
│  ┌────────────────────────────────────────────┐ │
│  │ ✓ FILE_WRITE - Approved (2 min ago)       │ │
│  │ ✗ GIT_FORCE_PUSH - Rejected (5 min ago)   │ │
│  │ ⏱ CODE_EXECUTION - Timeout (10 min ago)   │ │
│  └────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

**Features:**
- Live pending approvals with WebSocket
- Visual risk indicators (color-coded)
- Countdown timers
- One-click approve/reject
- Optional notes
- Filterable history

### 3. History (`/history`)

**Layout:**
```
┌─────────────────────────────────────────────────┐
│  Task History                                   │
│  Filters: [All] [Completed] [Failed] [Last 7d] │
├─────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────┐ │
│  │ ✓ Add OAuth2 authentication                │ │
│  │   #task-123 • Completed • 2:34 duration    │ │
│  │   Research → Context → PR → Done           │ │
│  │   3 iterations • 2 approvals               │ │
│  │   [View Details] [View Output]             │ │
│  └────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────┐ │
│  │ ✗ Fix login bug                            │ │
│  │   #task-122 • Failed • 0:45 duration       │ │
│  │   Research → Error                         │ │
│  │   [View Details] [View Error]              │ │
│  └────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

**Features:**
- Comprehensive task history
- Filtering and search
- Detailed execution timeline
- Output and error viewing
- Re-run capability

### 4. Analytics (`/analytics`)

**Layout:**
```
┌─────────────────────────────────────────────────┐
│  Analytics Dashboard                            │
├─────────────────────────────────────────────────┤
│  Overview:                                      │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐  │
│  │ Tasks  │ │Success │ │Avg Time│ │Approval│  │
│  │  47    │ │ 89.4%  │ │ 2:34   │ │ 94.2% │  │
│  └────────┘ └────────┘ └────────┘ └────────┘  │
│                                                 │
│  Agent Usage (Last 30 Days):                    │
│  [Bar Chart]                                    │
│  Research: ████████████ 45                      │
│  Context:  ███████ 32                           │
│  PR-Agent: ████████ 38                          │
│                                                 │
│  Approval Rate by Operation:                    │
│  [Pie Chart]                                    │
│  GIT_PUSH: 95% approved                         │
│  CODE_EXEC: 85% approved                        │
│  FILE_DEL: 60% approved                         │
└─────────────────────────────────────────────────┘
```

**Features:**
- Summary statistics
- Charts and visualizations
- Trend analysis
- Agent performance metrics

## Data Flow

### Task Execution Flow

```
1. User submits task via Dashboard
   ↓
2. Server creates TaskRequest
   ↓
3. Server starts orchestration in background
   ↓
4. Orchestrator emits progress events
   ↓
5. Server broadcasts via SSE to client
   ↓
6. Client updates UI in real-time
   ↓
7. If approval needed:
   a. Server broadcasts via WebSocket
   b. Client shows approval card
   c. User approves/rejects
   d. Server processes decision
   e. Orchestrator continues
   ↓
8. Task completes
   ↓
9. Server sends "complete" event
   ↓
10. Client shows final output
```

### Approval Notification Flow

```
1. Orchestrator requests approval
   ↓
2. ApprovalManager creates request
   ↓
3. Server detects new pending approval
   ↓
4. Server broadcasts via WebSocket to all clients
   ↓
5. All connected clients show approval card
   ↓
6. User on any client approves/rejects
   ↓
7. Server processes decision
   ↓
8. ApprovalManager resolves request
   ↓
9. Server broadcasts decision to all clients
   ↓
10. All clients update UI
    ↓
11. Orchestrator continues
```

## Security Considerations

1. **CORS Configuration**: Restrict allowed origins in production
2. **Rate Limiting**: Prevent abuse of API endpoints
3. **Input Validation**: Sanitize all user inputs
4. **Secret Filtering**: Context Core integration for sensitive data
5. **WebSocket Authentication**: Optional token-based auth
6. **HTTPS**: Use TLS in production

## Performance Optimizations

1. **Connection Pooling**: Redis, HTTP clients
2. **Caching**: Agent health checks, statistics
3. **Lazy Loading**: Load history/analytics on demand
4. **Pagination**: Large lists (history, approvals)
5. **Debouncing**: UI updates, health checks
6. **Background Tasks**: Non-blocking operations

## Deployment

### Development
```bash
# Start unified server
python -m src.web.server

# Access at http://localhost:8080
```

### Production
```bash
# Using Gunicorn + Uvicorn workers
gunicorn src.web.server:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8080
```

### Docker
```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "src.web.server:app", "--host", "0.0.0.0", "--port", "8080"]
```

## Future Enhancements

- **Multi-user Support**: User authentication and permissions
- **Task Templates**: Pre-defined common tasks
- **Scheduled Tasks**: Cron-like task scheduling
- **Collaboration**: Multiple users on same task
- **Mobile App**: Native mobile interface
- **Dark Mode**: Theme support
- **Export/Import**: Task configurations
- **API Keys**: Programmatic access
- **Webhooks**: External integrations

## Related Documentation

- [Phase 1 Guide](PHASE_1_USAGE.md) - State Management
- [Phase 2 Guide](PHASE_2_GUIDE.md) - Intelligent Routing
- [Phase 3 Guide](PHASE_3_GUIDE.md) - HITL Approval System
- [Phase 4 User Guide](PHASE_4_GUIDE.md) - Command Center Usage (TBD)
