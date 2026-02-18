# Phase 4: The Command Center

**Status**: ✅ Complete
**Version**: 1.0.0
**Last Updated**: February 18, 2026

## Overview

The Command Center is a unified web-based interface for The Orchestrator, providing real-time monitoring, task management, human-in-the-loop approvals, analytics, and system health monitoring.

## Features

### ✅ Core Features

1. **Dashboard** (`/`)
   - Real-time task submission and monitoring
   - Live agent status indicators (5 agents: Research, Context, PR, Ollama, Redis)
   - SSE-based progress streaming
   - Event timeline visualization
   - Task progress tracking with iteration count

2. **HITL Approvals** (`/approvals`)
   - Visual approval interface for risky operations
   - Risk level classification (LOW, MEDIUM, HIGH, CRITICAL)
   - Countdown timers for pending approvals
   - Approval history tracking
   - Optional notes for approval/rejection decisions
   - Auto-refresh every 5 seconds

3. **Task History** (`/history`)
   - Complete task execution history
   - Status filtering and search
   - Task detail view with messages and routing
   - Performance metrics per task

4. **Analytics** (`/analytics`)
   - Task statistics (success rate, avg iterations, completion times)
   - Agent usage patterns and success rates
   - Approval statistics and risk breakdown
   - Routing decision analysis
   - Performance metrics (avg/min/max completion times)
   - Configurable time windows (1, 7, 14, 30 days)

5. **Health Monitoring**
   - Real-time health checks for all services
   - Automatic status detection (HEALTHY, DEGRADED, DOWN, UNKNOWN)
   - Service-specific diagnostics
   - Integration with dashboard agent indicators

## Architecture

### Backend (FastAPI)

```
src/web/
├── server.py              # Unified FastAPI server (port 8080)
├── models.py              # Pydantic models for API
├── task_manager.py        # Background task orchestration
├── health_monitor.py      # Agent health checking
├── analytics.py           # Analytics data aggregation
├── static/                # Frontend assets
│   ├── css/style.css     # Jet black design system
│   └── js/
│       ├── dashboard.js  # Dashboard frontend
│       ├── approvals.js  # Approvals interface
│       └── analytics.js  # Analytics visualization
└── templates/             # Jinja2 HTML templates
    ├── dashboard.html
    ├── approvals.html
    ├── history.html
    └── analytics.html
```

### Key Components

#### 1. Server (`server.py`)

Unified FastAPI application with:
- **Task Management API**: Create, monitor, stream tasks
- **Approval API**: Pending/approve/reject/history/stats
- **Analytics API**: Overview, tasks, agents, approvals, routing, performance
- **Health API**: System and agent health checks
- **HTML Pages**: Dashboard, approvals, history, analytics
- **Static Files**: CSS, JavaScript, images

Port: `8080`
Host: `0.0.0.0` (accessible on network)

#### 2. Task Manager (`task_manager.py`)

Manages background orchestration tasks:
- Async task execution using LangGraph
- SSE event streaming for real-time updates
- Task state persistence
- Event types: TASK_START, AGENT_START, AGENT_PROGRESS, AGENT_COMPLETE, COMPLETE, ERROR

#### 3. Health Monitor (`health_monitor.py`)

Monitors all system components:
- **Research Agent**: HTTP health check to port 8000
- **Context Core**: Path validation and import check
- **PR-Agent**: Path validation and structure check
- **Ollama**: HTTP check + model availability verification
- **Redis**: Connection test with ping

#### 4. Analytics Service (`analytics.py`)

Aggregates metrics from tasks and approvals:
- Task completion rates and iteration counts
- Agent call patterns and success rates
- Approval response times and risk distribution
- Routing transitions and strategy usage
- Performance benchmarks

### Frontend

#### Design System

**Theme**: Jet Black (Apple-inspired)
- Background: `#000000` (pure black)
- Text: `#ffffff` (white)
- Font: Apple SF Pro Display / SF Pro Text
- Success: `#00ff00` (bright green)
- Error: `#ff3333` (bright red)
- Warning: `#ff8800` (orange)

#### Real-time Updates

- **SSE (Server-Sent Events)**: Task progress streaming
- **Polling**: Health checks (30s), approvals (5s), analytics (60s)
- **EventSource API**: Browser-native SSE client

#### User Experience

- Minimalist, clean interface
- Instant visual feedback
- Live countdown timers for approvals
- Auto-refresh for pending items
- Responsive grid layouts
- Browser notifications (opt-in)

## API Reference

### Task Management

```
POST   /api/tasks                    # Create new task
GET    /api/tasks                    # List tasks (with filters)
GET    /api/tasks/{id}               # Get task details
GET    /api/tasks/{id}/stream        # SSE progress stream
```

### Approvals

```
GET    /api/approvals/pending        # Get pending approvals
POST   /api/approvals/{id}/approve   # Approve request
POST   /api/approvals/{id}/reject    # Reject request
GET    /api/approvals/history        # Get approval history
GET    /api/approvals/stats          # Get approval statistics
```

### Analytics

```
GET    /api/analytics/overview       # Complete analytics overview
GET    /api/analytics/tasks          # Task statistics
GET    /api/analytics/agents         # Agent usage stats
GET    /api/analytics/approvals      # Approval statistics
GET    /api/analytics/routing        # Routing decisions
GET    /api/analytics/performance    # Performance metrics
```

### Health

```
GET    /api/health                   # System health status
```

### HTML Pages

```
GET    /                             # Dashboard
GET    /approvals                    # Approvals interface
GET    /history                      # Task history
GET    /analytics                    # Analytics page
```

## Getting Started

### Prerequisites

1. **Python 3.10+** with dependencies:
   ```bash
   pip install fastapi uvicorn jinja2 aiohttp redis
   ```

2. **Environment Configuration** (`.env`):
   ```env
   RESEARCH_AGENT_PATH=/path/to/research-agent
   CONTEXT_CORE_PATH=/path/to/context-core
   PR_AGENT_PATH=/path/to/pr-agent
   RESEARCH_AGENT_URL=http://localhost:8000
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=llama3.1:8b-instruct-q8_0
   REDIS_HOST=localhost
   REDIS_PORT=6379
   REDIS_DB=0
   ```

3. **External Services**:
   ```bash
   # Start Ollama
   ollama serve

   # Start Redis
   redis-server

   # (Optional) Start Research Agent
   cd /path/to/research-agent && python -m uvicorn main:app --port 8000
   ```

### Running the Command Center

```bash
# Development mode (with auto-reload)
uvicorn src.web.server:app --host 0.0.0.0 --port 8080 --reload

# Production mode
uvicorn src.web.server:app --host 0.0.0.0 --port 8080
```

Access at: **http://localhost:8080**

### Testing

```bash
# Run all Phase 4 tests
pytest tests/web/ -v

# Run with coverage
pytest tests/web/ --cov=src.web --cov-report=html

# Run specific test file
pytest tests/web/test_health_monitor.py -v
```

## Usage Examples

### 1. Submit a Task

```python
import requests

response = requests.post('http://localhost:8080/api/tasks', json={
    'objective': 'Find best practices for Python logging',
    'max_iterations': 10,
    'routing_strategy': 'adaptive',
    'enable_hitl': True,
})

task = response.json()
print(f"Task ID: {task['task_id']}")
print(f"Stream URL: {task['stream_url']}")
```

### 2. Monitor Task Progress (SSE)

```javascript
const eventSource = new EventSource('/api/tasks/task-123/stream');

eventSource.addEventListener('agent_start', (e) => {
    const data = JSON.parse(e.data);
    console.log(`Agent started: ${data.agent}`);
});

eventSource.addEventListener('complete', (e) => {
    const data = JSON.parse(e.data);
    console.log('Task completed!', data);
    eventSource.close();
});
```

### 3. Check System Health

```bash
curl http://localhost:8080/api/health | jq
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2026-02-18T01:00:00.123456",
  "agents": {
    "research": "healthy",
    "context": "healthy",
    "pr": "healthy",
    "ollama": "healthy",
    "redis": "healthy"
  },
  "details": {
    "version": "1.0.0"
  }
}
```

### 4. Get Analytics

```bash
curl "http://localhost:8080/api/analytics/overview?days=7" | jq
```

## Integration with Phase 3 (HITL)

The Command Center seamlessly integrates the HITL approval system from Phase 3:

1. **Risk Classification**: Automatically classifies operations by risk level
2. **Visual Approvals**: Beautiful web interface for approving/rejecting
3. **Timeout Handling**: Countdown timers with auto-expiration
4. **Audit Trail**: Complete history of all approval decisions
5. **Statistics**: Approval rates, response times, risk distribution

## Performance

- **SSE Streaming**: Low-latency real-time updates (< 100ms)
- **Health Checks**: Concurrent async checks (< 5s for all agents)
- **Analytics**: In-memory aggregation (< 1s for 1000 tasks)
- **Static Assets**: Served directly by FastAPI (optimized)

## Security Considerations

1. **Local-First**: Runs entirely on localhost by default
2. **No Authentication**: Designed for single-user local development (add auth for production)
3. **CORS**: Not enabled (add if needed for external frontends)
4. **Input Validation**: All inputs validated with Pydantic
5. **Secrets Filtering**: Context Core filters sensitive data

## Troubleshooting

### Server Won't Start

```bash
# Check if port 8080 is already in use
lsof -ti:8080 | xargs kill -9

# Check for missing dependencies
pip install -r requirements.txt
```

### Agents Showing as "DOWN"

1. **Ollama**: `ollama serve` not running
2. **Redis**: `redis-server` not running
3. **Research Agent**: Server not started or wrong URL
4. **Context Core**: Path incorrect in .env
5. **PR-Agent**: Path incorrect in .env

### No Task Progress Updates

- Check browser console for SSE connection errors
- Verify task_manager is starting orchestration correctly
- Check server logs for exceptions

### Analytics Showing Zero

- No tasks have been run yet (expected)
- Check that tasks are being persisted correctly
- Verify time window includes executed tasks

## Future Enhancements

### Planned

- [ ] WebSocket notifications for approvals (real-time push)
- [ ] Settings UI for configuration management
- [ ] Chart visualizations (Chart.js or similar)
- [ ] Task templates and presets
- [ ] Export analytics to CSV/JSON
- [ ] Dark/light theme toggle
- [ ] Multi-user authentication
- [ ] Role-based access control

### Under Consideration

- [ ] Distributed orchestration (multiple workers)
- [ ] Task scheduling and cron jobs
- [ ] Slack/Discord notifications
- [ ] Grafana/Prometheus integration
- [ ] Docker deployment
- [ ] Kubernetes manifests

## Architecture Decisions

### Why FastAPI?

- Async/await native support
- Automatic API documentation (Swagger UI at `/docs`)
- Pydantic integration for type safety
- High performance
- SSE support with StreamingResponse

### Why SSE over WebSockets?

- Simpler protocol (one-way server→client)
- Auto-reconnection built into EventSource
- No need for complex WebSocket state management
- Perfect for progress streaming use case

### Why Jinja2 Templates?

- Server-side rendering for initial page load
- SEO-friendly (though not needed for local tool)
- Progressive enhancement
- Simple integration with FastAPI

### Why Jet Black Design?

- User requested Apple-inspired aesthetic
- High contrast for readability
- Modern, professional appearance
- Reduced eye strain in dark environments

## Testing

### Test Coverage

```
src/web/health_monitor.py     100%
src/web/analytics.py           95%
src/web/server.py              85%
src/web/models.py              100%
Overall:                       92%
```

### Test Categories

1. **Unit Tests**: Health monitoring, analytics service
2. **Integration Tests**: API endpoints with mocked dependencies
3. **Frontend Tests**: (Manual for now - could add Playwright)

## Related Documentation

- [Phase 1: The Blackboard](./PHASE_1_BLACKBOARD.md) - Shared state
- [Phase 2: The Router](./PHASE_2_ROUTER.md) - Intelligent routing
- [Phase 3: The HITL Gate](./PHASE_3_HITL.md) - Approval system
- [Architecture Overview](./PHASE_4_ARCHITECTURE.md) - Detailed design

## Credits

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [Uvicorn](https://www.uvicorn.org/) - ASGI server
- [Jinja2](https://jinja.palletsprojects.com/) - Templating
- [Redis](https://redis.io/) - State persistence
- [Ollama](https://ollama.com/) - Local LLM
- Apple SF Pro - Typography

## License

Part of The Orchestrator project. See main README for license details.
