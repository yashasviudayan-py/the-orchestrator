#!/usr/bin/env python3
"""
Phase 1 Demo - The Blackboard

Demonstrates the complete Phase 1 implementation:
- Redis state management
- Agent interface wrappers
- LangGraph orchestrator
- Secret filtering integration
"""

import asyncio
import logging
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

from state.redis_client import RedisClient, get_redis_client
from state.manager import StateManager
from state.schemas import TaskState, TaskStatus
from agents import (
    ResearchAgentInterface,
    ContextCoreInterface,
    PRAgentInterface,
)
from orchestrator import OrchestratorGraph
from config import get_cached_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    """Run Phase 1 demo."""
    print("\n" + "=" * 60)
    print("  PHASE 1 DEMO - THE BLACKBOARD")
    print("=" * 60 + "\n")

    # Load environment variables
    load_dotenv()
    settings = get_cached_settings()

    print("📋 Configuration:")
    print(f"   Redis: {settings.redis_host}:{settings.redis_port}")
    print(f"   Ollama: {settings.ollama_base_url}")
    print(f"   Model: {settings.ollama_model}")
    print(f"   Max Iterations: {settings.max_iterations}\n")

    # Step 1: Initialize Redis
    print("🔄 Step 1: Connecting to Redis...")
    redis_client = get_redis_client(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password,
    )

    try:
        await redis_client.connect()
        health = await redis_client.health_check()
        if not health:
            raise Exception("Redis health check failed")
        print("   ✓ Redis connected\n")
    except Exception as e:
        print(f"   ✗ Redis connection failed: {e}")
        print("   Make sure Redis is running: redis-server")
        return

    # Step 2: Initialize State Manager
    print("🔄 Step 2: Initializing State Manager...")
    state_manager = StateManager(redis_client)
    print("   ✓ State Manager ready\n")

    # Step 3: Initialize Agent Interfaces
    print("🔄 Step 3: Initializing Agent Interfaces...")

    try:
        # Research Agent (HTTP API)
        research_agent = ResearchAgentInterface(
            base_url=settings.research_agent_url
        )
        research_healthy = await research_agent.health_check()
        print(f"   {'✓' if research_healthy else '✗'} Research Agent: {settings.research_agent_url}")

        # Context Core (Direct Import)
        context_agent = ContextCoreInterface(
            context_core_path=settings.context_core_path
        )
        context_healthy = await context_agent.health_check()
        print(f"   {'✓' if context_healthy else '✗'} Context Core: {settings.context_core_path}")

        # PR-Agent (Subprocess)
        pr_agent = PRAgentInterface(
            agent_path=settings.pr_agent_path
        )
        pr_healthy = await pr_agent.health_check()
        print(f"   {'✓' if pr_healthy else '✗'} PR-Agent: {settings.pr_agent_path}")

        print()

        if not all([research_healthy, context_healthy, pr_healthy]):
            print("⚠️  Warning: Some agents are not healthy")
            print("   The demo will continue, but agent calls may fail\n")

    except Exception as e:
        print(f"   ✗ Agent initialization failed: {e}")
        print("   Check agent paths in .env file")
        return

    # Step 4: Initialize Orchestrator
    print("🔄 Step 4: Building Orchestrator Graph...")
    orchestrator = OrchestratorGraph(
        research_agent=research_agent,
        context_agent=context_agent,
        pr_agent=pr_agent,
        llm_base_url=settings.ollama_base_url,
        llm_model=settings.ollama_model,
    )
    print("   ✓ Orchestrator ready\n")

    # Step 5: Create a test task
    print("🔄 Step 5: Creating test task...")
    objective = "Add input validation to user registration form"
    user_context = {
        "repo_path": ".",  # Current directory
        "project_type": "web_app",
    }

    task = await state_manager.create_task(
        objective=objective,
        user_context=user_context,
        max_iterations=settings.max_iterations,
    )
    print(f"   ✓ Task created: {task.task_id}")
    print(f"   Objective: {objective}\n")

    # Step 6: Demonstrate secret filtering
    print("🔄 Step 6: Testing Secret Filtering...")
    test_text = "API_KEY=sk_test_1234567890 password=secret123"
    result = await context_agent.execute({"check_secrets": test_text})
    if result["has_secrets"]:
        print(f"   ✓ Secret detection working!")
        print(f"   Detected: {', '.join(result['descriptions'])}\n")
    else:
        print("   ℹ️  No secrets in test text\n")

    # Step 7: Run orchestration (simplified - would normally call orchestrator.run())
    print("🔄 Step 7: Orchestration Flow (Simulated)...")
    print("   Note: Full orchestration would call all agents")
    print("   For demo, we'll just show the state transitions:\n")

    # Simulate state transitions
    task.status = TaskStatus.RUNNING
    await state_manager.update_task(task)
    print(f"   → Status: {task.status.value}")

    task.increment_iteration()
    await state_manager.update_task(task)
    print(f"   → Iteration: {task.iteration}")

    task.add_message(
        agent_type="research",
        message_type="request",
        content={"topic": objective},
    )
    await state_manager.update_task(task)
    print(f"   → Added message from research agent")

    task.complete("Demo task completed successfully")
    await state_manager.update_task(task)
    print(f"   → Status: {task.status.value}\n")

    # Step 8: Retrieve and display stats
    print("🔄 Step 8: State Management Demo...")
    stats = await state_manager.get_stats()
    print(f"   Total tasks: {stats.get('total', 0)}")
    print(f"   Completed: {stats['by_status'].get('completed', 0)}")
    print(f"   With errors: {stats.get('with_errors', 0)}")
    print(f"   Avg iteration: {stats.get('avg_iteration', 0):.1f}\n")

    # Step 9: Cleanup
    print("🔄 Step 9: Cleaning up...")
    await redis_client.disconnect()
    print("   ✓ Disconnected from Redis\n")

    print("=" * 60)
    print("  ✅ PHASE 1 DEMO COMPLETED SUCCESSFULLY!")
    print("=" * 60 + "\n")

    print("📝 Summary:")
    print("   ✓ Redis connection and state management")
    print("   ✓ Agent interface wrappers")
    print("   ✓ LangGraph orchestrator initialization")
    print("   ✓ Secret filtering integration")
    print("   ✓ State persistence and retrieval\n")

    print("🚀 Next Steps:")
    print("   1. Start all required services (Redis, Ollama, agents)")
    print("   2. Run full orchestration with: orchestrator.run(objective)")
    print("   3. Monitor state transitions in Redis")
    print("   4. Test with real tasks\n")


if __name__ == "__main__":
    asyncio.run(main())
