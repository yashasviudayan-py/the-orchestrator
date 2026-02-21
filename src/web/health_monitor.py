"""
Agent Health Monitoring

Provides health checks for all integrated services:
- Research Agent (HTTP API)
- Context Core (Python module)
- PR-Agent (File system)
- Ollama (LLM server)
- Redis (State store)
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import aiohttp
import redis.asyncio as aioredis

from ..config import get_settings
from .models import AgentStatus

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Monitors health of all system components."""

    def __init__(self):
        self.settings = get_settings()
        self._health_cache: Dict[str, tuple[AgentStatus, datetime]] = {}
        self._cache_ttl = 30  # Cache health status for 30 seconds

    async def check_all(self) -> Dict[str, AgentStatus]:
        """
        Check health of all agents and services.

        Returns:
            Dictionary mapping service name to health status
        """
        # Run all health checks concurrently
        results = await asyncio.gather(
            self.check_research_agent(),
            self.check_context_core(),
            self.check_pr_agent(),
            self.check_ollama(),
            self.check_redis(),
            return_exceptions=True,
        )

        health = {
            "research": results[0] if not isinstance(results[0], Exception) else AgentStatus.DOWN,
            "context": results[1] if not isinstance(results[1], Exception) else AgentStatus.DOWN,
            "pr": results[2] if not isinstance(results[2], Exception) else AgentStatus.DOWN,
            "ollama": results[3] if not isinstance(results[3], Exception) else AgentStatus.DOWN,
            "redis": results[4] if not isinstance(results[4], Exception) else AgentStatus.DOWN,
        }

        logger.debug(f"Health check results: {health}")
        return health

    async def check_research_agent(self) -> AgentStatus:
        """Check if Research Agent API is accessible."""
        try:
            url = f"{self.settings.research_agent_url}/api/health"
            timeout = aiohttp.ClientTimeout(total=3)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        logger.debug("Research Agent: HEALTHY")
                        return AgentStatus.HEALTHY
                    else:
                        logger.warning(f"Research Agent returned status {response.status}")
                        return AgentStatus.DEGRADED

        except aiohttp.ClientConnectionError:
            logger.warning("Research Agent: Cannot connect (server may be down)")
            return AgentStatus.DOWN
        except asyncio.TimeoutError:
            logger.warning("Research Agent: Timeout (server not responding)")
            return AgentStatus.DEGRADED
        except Exception as e:
            logger.error(f"Research Agent health check failed: {e}")
            return AgentStatus.DOWN

    async def check_context_core(self) -> AgentStatus:
        """Check if Context Core is importable and accessible."""
        try:
            # Check if path exists
            path = Path(self.settings.context_core_path)
            if not path.exists():
                logger.warning(f"Context Core path does not exist: {path}")
                return AgentStatus.DOWN

            # Try importing Context Core
            # Note: This is a lightweight check - just verify we can import it
            import sys
            sys.path.insert(0, str(path))

            try:
                import context_core
                logger.debug("Context Core: HEALTHY (importable)")
                return AgentStatus.HEALTHY
            except ImportError as ie:
                logger.warning(f"Context Core: Cannot import - {ie}")
                return AgentStatus.DEGRADED
            finally:
                # Clean up sys.path
                if str(path) in sys.path:
                    sys.path.remove(str(path))

        except Exception as e:
            logger.error(f"Context Core health check failed: {e}")
            return AgentStatus.DOWN

    async def check_pr_agent(self) -> AgentStatus:
        """Check if PR-Agent path is accessible and dependencies are available."""
        try:
            path = Path(self.settings.pr_agent_path)

            if not path.exists():
                logger.warning(f"PR-Agent path does not exist: {path}")
                return AgentStatus.DOWN

            # Check if it's a valid directory with expected structure
            if not path.is_dir():
                logger.warning(f"PR-Agent path is not a directory: {path}")
                return AgentStatus.DOWN

            # Look for key files that indicate a valid PR-Agent installation
            expected_files = ["__init__.py", "main.py", "agent.py"]
            found_files = any((path / f).exists() for f in expected_files)

            if not found_files:
                logger.warning("PR-Agent: Path exists but missing expected files")
                return AgentStatus.DEGRADED

            # Verify git CLI is available
            try:
                git_proc = await asyncio.create_subprocess_exec(
                    "git", "--version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await git_proc.communicate()
                if git_proc.returncode != 0:
                    logger.warning("PR-Agent: git CLI not available")
                    return AgentStatus.DEGRADED
            except FileNotFoundError:
                logger.warning("PR-Agent: git CLI not installed")
                return AgentStatus.DEGRADED

            # Verify gh CLI is available
            try:
                gh_proc = await asyncio.create_subprocess_exec(
                    "gh", "auth", "status",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await gh_proc.communicate()
                if gh_proc.returncode != 0:
                    logger.warning("PR-Agent: GitHub CLI not authenticated")
                    return AgentStatus.DEGRADED
            except FileNotFoundError:
                logger.warning("PR-Agent: GitHub CLI (gh) not installed")
                return AgentStatus.DEGRADED

            logger.debug("PR-Agent: HEALTHY (path, git, and gh all accessible)")
            return AgentStatus.HEALTHY

        except Exception as e:
            logger.error(f"PR-Agent health check failed: {e}")
            return AgentStatus.DOWN

    async def check_ollama(self) -> AgentStatus:
        """Check if Ollama server is running and responsive."""
        try:
            url = f"{self.settings.ollama_base_url}/api/tags"
            timeout = aiohttp.ClientTimeout(total=5)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()

                        # Check if our configured model is available
                        models = data.get("models", [])
                        model_names = [m.get("name", "") for m in models]

                        if self.settings.ollama_model in model_names:
                            logger.debug(f"Ollama: HEALTHY (model {self.settings.ollama_model} available)")
                            return AgentStatus.HEALTHY
                        else:
                            logger.warning(f"Ollama: Model {self.settings.ollama_model} not found")
                            return AgentStatus.DEGRADED
                    else:
                        logger.warning(f"Ollama returned status {response.status}")
                        return AgentStatus.DEGRADED

        except aiohttp.ClientConnectionError:
            logger.warning("Ollama: Cannot connect (server may be down)")
            return AgentStatus.DOWN
        except asyncio.TimeoutError:
            logger.warning("Ollama: Timeout (server not responding)")
            return AgentStatus.DEGRADED
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return AgentStatus.DOWN

    async def check_redis(self) -> AgentStatus:
        """Check if Redis is accessible."""
        try:
            client = aioredis.from_url(
                f"redis://{self.settings.redis_host}:{self.settings.redis_port}/{self.settings.redis_db}",
                decode_responses=True,
            )

            # Try a simple ping
            response = await asyncio.wait_for(client.ping(), timeout=3.0)
            await client.close()

            if response:
                logger.debug("Redis: HEALTHY")
                return AgentStatus.HEALTHY
            else:
                logger.warning("Redis: Unexpected ping response")
                return AgentStatus.DEGRADED

        except asyncio.TimeoutError:
            logger.warning("Redis: Timeout (server not responding)")
            return AgentStatus.DEGRADED
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return AgentStatus.DOWN

    def get_overall_status(self, health: Dict[str, AgentStatus]) -> str:
        """
        Determine overall system health.

        Args:
            health: Dictionary of individual service health statuses

        Returns:
            Overall status: "healthy", "degraded", or "down"
        """
        statuses = list(health.values())

        # If any critical service is down, system is down
        critical_services = ["ollama", "redis"]
        for service in critical_services:
            if health.get(service) == AgentStatus.DOWN:
                return "down"

        # If any service is down or degraded, system is degraded
        if any(s == AgentStatus.DOWN for s in statuses):
            return "degraded"
        if any(s == AgentStatus.DEGRADED for s in statuses):
            return "degraded"

        # All services healthy
        return "healthy"


# Singleton instance
_health_monitor: Optional[HealthMonitor] = None


def get_health_monitor() -> HealthMonitor:
    """Get the global HealthMonitor instance."""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = HealthMonitor()
    return _health_monitor
