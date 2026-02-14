# Phase 1: The Blackboard - Implementation Plan

## Overview
Create a shared state system using LangGraph and Redis where all three agents can read/write data.

## Objectives
1. Set up local Redis instance
2. Design state schema for agent communication
3. Implement LangGraph state graph
4. Create state management utilities
5. Test state persistence and retrieval

## Prerequisites
- Redis installed and running locally
- Python 3.10+ environment set up
- Dependencies installed from requirements.txt

## Implementation Steps

### Step 1: Redis Setup
**Files to create**:
- `src/state/redis_client.py` - Redis connection manager
- `src/state/config.py` - Redis configuration

**Tasks**:
- [ ] Install Redis locally (brew install redis on macOS)
- [ ] Create Redis client wrapper with connection pooling
- [ ] Implement health check and reconnection logic
- [ ] Add Redis configuration loader

### Step 2: State Schema Design
**Files to create**:
- `src/state/schemas.py` - Pydantic models for state

**State Structure**:
```python
class AgentMessage(BaseModel):
    agent_name: str
    timestamp: datetime
    message_type: str
    content: dict
    metadata: dict

class TaskState(BaseModel):
    task_id: str
    objective: str
    status: TaskStatus
    current_agent: Optional[str]
    iteration: int
    messages: List[AgentMessage]
    context: dict
    errors: List[str]
```

**Tasks**:
- [ ] Define core state models
- [ ] Create validation rules
- [ ] Implement serialization/deserialization
- [ ] Add type hints throughout

### Step 3: LangGraph State Graph
**Files to create**:
- `src/orchestrator/graph.py` - Main LangGraph definition
- `src/orchestrator/nodes.py` - Node implementations
- `src/orchestrator/edges.py` - Edge logic

**Graph Structure**:
```
START → PARSE_OBJECTIVE → ROUTE_TO_AGENT → AGENT_EXECUTION → CHECK_COMPLETE → END
                                ↓                                    ↑
                                └────────── (loop) ─────────────────┘
```

**Tasks**:
- [ ] Define LangGraph StateGraph
- [ ] Implement node functions
- [ ] Add conditional edge logic
- [ ] Configure checkpointing

### Step 4: State Management Utilities
**Files to create**:
- `src/state/manager.py` - State management class
- `src/state/operations.py` - CRUD operations

**Operations**:
```python
class StateManager:
    async def create_task(self, objective: str) -> str
    async def get_task(self, task_id: str) -> TaskState
    async def update_task(self, task_id: str, updates: dict) -> bool
    async def add_message(self, task_id: str, message: AgentMessage) -> bool
    async def get_messages(self, task_id: str) -> List[AgentMessage]
    async def delete_task(self, task_id: str) -> bool
```

**Tasks**:
- [ ] Implement StateManager class
- [ ] Add async Redis operations
- [ ] Implement message queue operations
- [ ] Add error handling and retries

### Step 5: Agent Communication Protocol
**Files to create**:
- `src/agents/base.py` - Base agent interface
- `src/agents/protocol.py` - Communication protocol

**Protocol**:
```python
class AgentInterface(ABC):
    @abstractmethod
    async def process(self, state: TaskState) -> AgentResponse:
        """Process task and return response"""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if agent is available"""
        pass
```

**Tasks**:
- [ ] Define agent communication protocol
- [ ] Create base agent interface
- [ ] Implement message formatting
- [ ] Add response validation

### Step 6: Testing
**Files to create**:
- `tests/test_redis_client.py`
- `tests/test_state_manager.py`
- `tests/test_graph.py`

**Test Cases**:
- [ ] Redis connection and reconnection
- [ ] State creation and retrieval
- [ ] Message queue operations
- [ ] Graph execution flow
- [ ] Checkpoint save/restore
- [ ] Error handling

### Step 7: Documentation
**Files to create/update**:
- `docs/STATE_MANAGEMENT.md` - State management guide
- `docs/API.md` - API documentation

**Tasks**:
- [ ] Document state schema
- [ ] Document API endpoints
- [ ] Create usage examples
- [ ] Add troubleshooting guide

## Success Criteria
- [ ] Redis successfully stores and retrieves state
- [ ] LangGraph executes basic flow without errors
- [ ] State persists across graph executions
- [ ] All tests pass
- [ ] Documentation is complete

## Timeline Estimate
- Redis Setup: 1 hour
- State Schema: 2 hours
- LangGraph Implementation: 4 hours
- State Management Utilities: 3 hours
- Agent Protocol: 2 hours
- Testing: 3 hours
- Documentation: 2 hours

**Total**: ~17 hours

## Dependencies
```
langgraph>=0.2.0
langchain>=0.3.0
redis>=5.0.0
pydantic>=2.9.0
```

## Risks & Mitigations

### Risk: Redis Connection Issues
**Mitigation**: Implement connection pooling and automatic reconnection

### Risk: State Schema Changes
**Mitigation**: Version the schema and implement migration logic

### Risk: Memory Overflow
**Mitigation**: Implement TTL and cleanup for old tasks

## Next Steps After Phase 1
Once Phase 1 is complete, we'll move to Phase 2: The Router, where we'll implement the supervisor node that decides which agent to call next.
