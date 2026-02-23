# The Orchestrator - Interview Preparation Guide

---

## ELEVATOR PITCH (30 seconds)

"The Orchestrator is a multi-agent orchestration system I built that coordinates three specialized AI agents — a Research Agent, a Context Core, and a PR-Agent — to accomplish complex software development tasks autonomously. It runs 100% locally using Ollama, with zero cloud dependencies. The key differentiator is its Human-in-the-Loop safety gate that classifies operations by risk level and requires explicit approval before any destructive action. I built it in 4 phases: shared state management with Redis, intelligent routing with LangGraph, the HITL safety system, and a real-time web dashboard."

---

## PROJECT OVERVIEW

**What it is**: A local-first, multi-agent AI orchestration system for software development tasks.

**What it does**: You give it a task like "Research OAuth2 best practices and implement it in my project." The system automatically:
1. Routes to the Research Agent to find best practices
2. Passes findings through Context Core for memory/relevance
3. Sends to PR-Agent to generate code and create a PR
4. Asks for your approval before any destructive operation (git push, file delete)

**Tech Stack**:
- **LLM**: Ollama (local, free, privacy-first)
- **Orchestration**: LangGraph (stateful graph execution)
- **State**: Redis (shared blackboard pattern)
- **API**: FastAPI (async, type-safe)
- **Frontend**: Vanilla JS + SSE (real-time streaming)
- **CLI**: Click + Rich
- **Validation**: Pydantic v2 throughout

---

## THE 4 PHASES

### Phase 1: The Blackboard (Shared State)
- Redis-backed shared state using the **Blackboard architectural pattern**
- All agents read/write to a common `TaskState` object
- Async Redis client with connection pooling (max 10 connections)
- TTL-based cleanup (1 hour default) to prevent memory bloat
- Complete message audit trail — every agent interaction is logged

### Phase 2: The Router (Intelligent Supervision)
- LangGraph StateGraph with conditional edges for dynamic routing
- **EnhancedSupervisor** with 3 routing strategies:
  - `research_first` — always gather info before acting
  - `context_first` — check existing knowledge first
  - `adaptive` — LLM analyzes the objective and decides (default)
- Fast heuristic routing first (~instant), LLM fallback only for ambiguous cases
- **ContextSummarizer** to compress agent outputs and prevent token overflow
- Max iterations safeguard (default 10) prevents infinite loops

### Phase 3: The HITL Gate (Human-in-the-Loop Safety)
- Risk classification system: LOW, MEDIUM, HIGH, CRITICAL
- LOW risk auto-approves, MEDIUM+ requires human review
- Async approval flow with configurable timeout (default 300s)
- REST API for approve/reject with optional notes
- Integrates into the LangGraph as a gate node before destructive operations

### Phase 4: The Commander (Web Dashboard + CLI)
- Real-time web dashboard with SSE streaming (not WebSockets)
- ChatGPT-style interface with session history
- Smart chat router: conversational messages go direct to Ollama, task messages go through the agent pipeline
- Health monitoring for all 5 services
- Analytics: task stats, agent usage, approval rates
- CLI with `serve`, `run`, and `status` commands

---

## ARCHITECTURE DEEP DIVE

### Data Flow
```
User Input
    |
    v
Smart Router (conversational vs task)
    |
    v (if task)
LangGraph StateGraph
    |
    v
parse_objective (LLM decides first agent)
    |
    v
supervisor_entry (routing strategy applied)
    |
    +---> call_research ---> Secret Filter ---> Summarize
    +---> call_context  ---> Secret Filter ---> Summarize
    +---> call_pr       ---> HITL Gate ------> Approve/Reject
    |
    v
supervisor_route (decide next agent or finalize)
    |
    v (if iteration < max && more work needed)
    Loop back to agent
    |
    v (if done)
finalize (compile results, save to vault)
    |
    v
SSE Stream --> Browser (real-time updates)
```

### LangGraph Implementation

The graph uses `StateGraph` with a `TaskState` dict as the state schema:

**Nodes** (functions that transform state):
- `parse_objective` — analyze user input, detect conversational vs task
- `call_research` — invoke Research Agent via HTTP
- `call_context` — invoke Context Core via Python import
- `call_pr` — invoke PR-Agent via subprocess
- `supervisor_route` — decide next agent using strategy
- `finalize` — compile final output

**Edges** (conditional routing):
```python
graph.add_conditional_edges(
    "supervisor_route",
    route_after_supervisor,  # Returns "research", "context", "pr", or "finalize"
)
```

**Safety checks in edge functions**:
- `iteration >= max_iterations` -> force finalize
- `error_count >= max_retries` -> force finalize
- Agent already called + no new info -> skip redundant calls

### State Schema (TaskState)
```python
class TaskState(BaseModel):
    task_id: str
    objective: str
    status: TaskStatus          # PENDING, RUNNING, WAITING_APPROVAL, COMPLETED, FAILED
    current_agent: AgentType    # RESEARCH, CONTEXT, PR, SUPERVISOR
    iteration: int
    max_iterations: int = 10
    agents_called: list[AgentType]
    research_results: Optional[ResearchResult]
    context_results: Optional[ContextResult]
    pr_results: Optional[PRResult]
    messages: list[AgentMessage]  # Full audit trail
    secrets_detected: bool
    errors: list[str]
    final_output: Optional[str]
```

---

## THE THREE AGENTS

### 1. Research Agent
- **Integration**: HTTP API (external microservice)
- **What it does**: Finds best practices, documentation, tutorials for a given topic
- **How**: POST to `/api/research` with topic, poll for results
- **Output**: Summary, full content, URLs, key findings
- **Timeout**: 300 seconds

### 2. Context Core
- **Integration**: Direct Python import (in-process)
- **What it does**: Semantic search over project docs, RAG chat, and SECRET FILTERING
- **Modes**: Search mode (query), Chat/RAG mode, Secret detection
- **Critical feature**: `filter_secrets()` — scans 15+ patterns (API keys, JWT, AWS creds, SSH keys) and redacts with `[REDACTED]`
- **Why in-process**: Needs direct access to the vault (ChromaDB) for fast vector search

### 3. PR-Agent
- **Integration**: Subprocess (external Python script)
- **What it does**: Generates code changes, creates branches, opens PRs
- **Two modes**:
  - `generate` — preview diff without committing
  - `commit` — actually push code and create PR
- **Requires**: git CLI, GitHub CLI (gh), valid auth
- **HITL gate**: Requires approval before commit mode

---

## SECURITY MEASURES

### Secret Filtering (Critical)
- Applied between EVERY agent handoff
- Scans both `summary` and `content` fields
- 15+ patterns: API keys, tokens, passwords, private keys
- Sets `secrets_detected = True` flag on state

### HITL Risk Classification
```
LOW      → Auto-approve (agent calls, reads)
MEDIUM   → Approval recommended (file writes, git commits, PR creation)
HIGH     → Approval required (code execution, file deletion, git push)
CRITICAL → Always requires approval (force push, branch deletion)
```

### Web Security
- CORS restricted to localhost origins only
- Security headers: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy, Permissions-Policy
- All user input HTML-escaped (XSS prevention)
- Pydantic validation on all API inputs
- Chat session TTL (5 minutes) prevents unbounded memory growth

---

## REAL-TIME STREAMING (SSE)

**Why SSE over WebSockets?**
- Simpler — built on HTTP, no upgrade handshake
- Auto-reconnection built into the EventSource API
- Supports `Last-Event-ID` for resuming after disconnect
- Sufficient for our use case (server -> client only)

**Event Types**:
```
TASK_START        — Task execution begins
AGENT_START       — Agent begins work
AGENT_PROGRESS    — Intermediate update from agent
AGENT_COMPLETE    — Agent finished
APPROVAL_REQUIRED — HITL gate triggered
APPROVAL_DECIDED  — User approved/rejected
APPROVAL_TIMEOUT  — Approval timed out
ITERATION         — New iteration started
ROUTING_DECISION  — Supervisor chose next agent
COMPLETE          — Task finished
ERROR             — Something failed
KEEPALIVE         — 30-second heartbeat
```

**Implementation**:
```python
# Backend: FastAPI StreamingResponse
async def event_generator():
    queue = await task_manager.get_event_queue(task_id)
    while True:
        event = await asyncio.wait_for(queue.get(), timeout=30.0)
        yield f"id: {event.event_id}\nevent: {event.event.value}\ndata: {json.dumps(event.data)}\n\n"

# Frontend: EventSource
const es = new EventSource(`/api/tasks/${taskId}/stream`);
es.addEventListener('agent_start', e => {
    const d = JSON.parse(e.data);
    updateUI(d);
});
```

---

## SMART CHAT ROUTING

Not every message needs the full agent pipeline. The system detects conversational messages and routes them directly to Ollama:

**Conversational** (direct LLM): "hello", "thanks", "how are you", short questions
**Task** (agent pipeline): "fix the auth bug", "research OAuth2 patterns", "create a PR for dark mode"

**Detection logic**:
1. Exact match against 200+ conversational phrases
2. Starts-with matching ("hi there", "thanks a lot")
3. Heuristic: <=3 words + no task keywords = conversational
4. Task keywords: fix, add, create, implement, build, research, deploy, etc.

---

## CONTEXT SUMMARIZATION

**Problem**: Ollama has limited context window. Passing full research results (could be 10,000+ tokens) to PR-Agent wastes tokens and may exceed limits.

**Solution**: ContextSummarizer compresses agent outputs before handoff:
- Research results -> 300-word focused summary
- Context results -> relevant excerpts only
- Full task state -> high-level status summary

**When**: After each agent completes, before routing to next agent.

---

## TESTING STRATEGY

- **Framework**: pytest + pytest-asyncio
- **Coverage target**: >80%
- **Test types**:
  - Unit tests with mock agents
  - Integration tests with real Redis (skipped if unavailable)
  - API endpoint tests with FastAPI TestClient
  - Health monitor tests with mocked services
- **Key fixtures**: mock agents return predictable data, mock LLM for routing tests

---

## LIKELY INTERVIEW QUESTIONS & ANSWERS

### Q: "Why did you build this?"
**A**: "I wanted to explore multi-agent AI orchestration in a practical, production-quality way. Most agent frameworks are toy demos — I wanted something that could actually handle real software tasks safely. The HITL gate was critical to me because I believe AI should augment developers, not replace their judgment on risky operations."

### Q: "Why Ollama instead of OpenAI/Anthropic?"
**A**: "Three reasons: (1) Privacy — no data leaves my machine, which matters when the system handles source code and credentials. (2) Cost — it's completely free. (3) Independence — no API key management, no rate limits, no vendor lock-in. The architecture is LLM-agnostic via LangChain, so swapping to cloud models is a config change."

### Q: "Why LangGraph instead of LangChain agents or AutoGen?"
**A**: "LangGraph gives me explicit control over the execution flow. With LangChain agents, the LLM decides the next step at every turn — that's unpredictable and hard to debug. LangGraph lets me define the graph structure (nodes and edges) while still allowing dynamic routing via conditional edges. I get deterministic safety guarantees (max iterations, HITL gates) without sacrificing flexibility."

### Q: "How does the Human-in-the-Loop system work?"
**A**: "Every operation is classified by risk level — LOW operations auto-approve, MEDIUM and above require human review. When a risky operation is triggered, the system creates an ApprovalRequest, emits an SSE event to the dashboard, and blocks the agent with an asyncio.Event. The user sees a notification with the operation details and diff, and can approve or reject. There's a configurable timeout (default 5 minutes) so the system doesn't hang forever."

### Q: "How do you handle the context window limitation?"
**A**: "I built a ContextSummarizer that compresses agent outputs before passing them to the next agent. Research results might be 10,000+ tokens, but the next agent only needs a 300-word summary. I also use fast heuristic routing instead of always asking the LLM to decide — pattern matching handles 80% of routing decisions instantly."

### Q: "What happens if an agent fails?"
**A**: "Multiple safeguards: (1) Each agent has a retry count (max 3). (2) If retries are exhausted, the edge function routes to finalize instead of looping. (3) The max iterations guard (default 10) prevents infinite loops. (4) All errors are added to the TaskState.errors list for the final output. (5) The system never fails silently — errors are logged, emitted via SSE, and shown in the dashboard."

### Q: "How do agents communicate?"
**A**: "Through the Blackboard pattern — a shared TaskState in Redis. Each agent reads the current state, does its work, writes results back. They don't talk to each other directly. This decouples them completely. The supervisor node reads the full state to make routing decisions."

### Q: "What's the hardest technical challenge you faced?"
**A**: "Correctly routing HITL approval events to the right SSE stream. The LangGraph generates internal task IDs that differ from the TaskManager's IDs. I had to build a mapping system (_graph_to_manager_task) that the progress callback populates, so when an approval event fires, it routes to the correct browser tab's event stream. Getting this right with concurrent tasks was tricky."

### Q: "How do you ensure security?"
**A**: "Five layers: (1) Secret filtering scans all agent outputs for 15+ credential patterns and redacts them before handoff. (2) The HITL gate blocks destructive operations. (3) CORS is locked to localhost. (4) Security headers prevent XSS, clickjacking, and MIME sniffing. (5) All user input is HTML-escaped and Pydantic-validated."

### Q: "Why SSE instead of WebSockets?"
**A**: "SSE is simpler for our use case — we only need server-to-client streaming. It works over plain HTTP, has built-in reconnection via the EventSource API, and supports Last-Event-ID for resuming streams. WebSockets would add complexity (upgrade handshake, ping/pong, full-duplex we don't need) without any benefit."

### Q: "How would you scale this?"
**A**: "Three directions: (1) Parallel agent execution — the LangGraph already supports it via the PARALLEL routing strategy, just needs implementation. (2) Distributed orchestration — move from in-memory task queues to a proper message broker like RabbitMQ. (3) Multi-model support — route different tasks to different LLMs (fast model for routing, powerful model for code generation)."

### Q: "What would you do differently?"
**A**: "I'd add persistent conversation memory earlier — right now each task is independent. I'd also implement proper rate limiting on the API endpoints and add structured logging with correlation IDs for easier debugging across the agent chain."

### Q: "Walk me through the code for a typical task execution."
**A**: "User submits 'Research OAuth2 and implement it' via the dashboard. The Smart Router classifies it as a task (not conversational). TaskManager creates a TaskState, starts a background asyncio.Task. The LangGraph compiles and runs:
1. parse_objective — LLM identifies this needs research first
2. supervisor_entry — adaptive strategy confirms research agent
3. call_research — HTTP POST to Research Agent, gets back findings
4. Secret filter runs on research output
5. ContextSummarizer compresses to 300 words
6. supervisor_route — decides context is needed next
7. call_context — semantic search for relevant project docs
8. supervisor_route — decides PR-Agent is next
9. call_pr — generates code diff, triggers HITL gate (MEDIUM risk)
10. Approval event fires, user sees notification in dashboard
11. User approves, PR-Agent commits and pushes
12. finalize — compiles summary, saves to Context Core vault
13. COMPLETE event fires, dashboard shows final output."

### Q: "What design patterns did you use?"
**A**:
- **Blackboard Pattern** — shared state that all agents read/write
- **Supervisor Pattern** — central routing node decides next agent
- **Strategy Pattern** — pluggable routing strategies (research-first, context-first, adaptive)
- **Observer Pattern** — SSE callbacks for real-time UI updates
- **Interface/Abstract Base Class** — all agents implement AgentInterface
- **Singleton Pattern** — approval manager, task manager, settings (cached)
- **Gate Pattern** — HITL approval gate blocks execution until human decision

### Q: "What's the difference between Phase 1 and Phase 2 graphs?"
**A**: "Phase 1 is a basic graph with hardcoded routing — parse, call agents, finalize. Phase 2 adds the EnhancedSupervisor with intelligent routing strategies, context summarization to manage token budgets, and caching of agent summaries to avoid redundant LLM calls. The routing decision in Phase 2 considers what agents have already been called, what information is still needed, and the confidence level of the decision."

---

## KEY METRICS TO MENTION

- **4 phases** built end-to-end
- **3 external agents** integrated (HTTP, Python import, subprocess)
- **5 service health checks** (Ollama, Redis, Research, Context, PR)
- **12 SSE event types** for real-time streaming
- **15+ secret patterns** detected and filtered
- **4 risk levels** with automatic classification
- **3 routing strategies** (research-first, context-first, adaptive)
- **200+ conversational patterns** for smart chat routing
- **0 cloud dependencies** — runs entirely local
- **$0 cost** — no API keys needed
- **6 web pages** (Dashboard, Approvals, History, Analytics, Health, Settings)

---

## TERMINOLOGY CHEAT SHEET

| Term | Meaning |
|------|---------|
| **Blackboard** | Shared state pattern — all agents read/write to common TaskState |
| **Supervisor** | Central routing node that decides which agent to call next |
| **HITL** | Human-in-the-Loop — requires human approval for risky operations |
| **StateGraph** | LangGraph's core abstraction — nodes + conditional edges |
| **Conditional Edge** | An edge whose destination is determined by a function at runtime |
| **SSE** | Server-Sent Events — one-way server-to-client streaming over HTTP |
| **Adaptive Routing** | LLM analyzes the objective and decides which agent to call |
| **Context Summarization** | Compressing agent outputs to fit within LLM token limits |
| **Risk Classification** | Automatic categorization of operations (LOW/MEDIUM/HIGH/CRITICAL) |
| **Secret Filtering** | Scanning text for credential patterns and redacting before handoff |
| **Agent Interface** | Abstract base class all agents implement (execute + health_check) |
| **Event Queue** | Per-task asyncio.Queue that buffers SSE events for streaming |
| **Progress Callback** | Function called on each LangGraph node update to emit SSE events |

---

## QUICK REFERENCE: FILE LOCATIONS

| Component | File |
|-----------|------|
| Main web server | `src/web/server.py` |
| LangGraph (Phase 2) | `src/orchestrator/graph_v2.py` |
| Node implementations | `src/orchestrator/nodes.py` |
| Routing logic | `src/orchestrator/edges.py` |
| Supervisor | `src/orchestrator/supervisor.py` |
| Summarizer | `src/orchestrator/summarizer.py` |
| HITL integration | `src/orchestrator/hitl_integration.py` |
| State schemas | `src/state/schemas.py` |
| Redis client | `src/state/redis_client.py` |
| Approval system | `src/api/approval_manager.py` |
| Task manager | `src/web/task_manager.py` |
| Health monitor | `src/web/health_monitor.py` |
| Config | `src/config.py` |
| CLI | `src/cli/main.py` |
| Dashboard JS | `src/web/static/js/dashboard.js` |
| Styles | `src/web/static/css/style.css` |
