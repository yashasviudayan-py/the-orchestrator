"""
Tests for Health Monitoring System
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from src.web.health_monitor import HealthMonitor, get_health_monitor
from src.web.models import AgentStatus


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = MagicMock()
    settings.research_agent_url = "http://localhost:8000"
    settings.context_core_path = "/fake/context/path"
    settings.pr_agent_path = "/fake/pr/path"
    settings.ollama_base_url = "http://localhost:11434"
    settings.ollama_model = "llama3.1:8b-instruct-q8_0"
    settings.redis_host = "localhost"
    settings.redis_port = 6379
    settings.redis_db = 0
    return settings


@pytest.fixture
def health_monitor(mock_settings):
    """Create health monitor instance."""
    with patch('src.web.health_monitor.get_settings', return_value=mock_settings):
        monitor = HealthMonitor()
        return monitor


class TestHealthMonitor:
    """Test HealthMonitor class."""

    @pytest.mark.asyncio
    async def test_check_research_agent_healthy(self, health_monitor):
        """Test Research Agent health check - healthy status."""
        mock_response = AsyncMock()
        mock_response.status = 200

        with patch('aiohttp.ClientSession') as mock_session:
            mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response

            status = await health_monitor.check_research_agent()

            assert status == AgentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_check_research_agent_down(self, health_monitor):
        """Test Research Agent health check - connection error."""
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session.return_value.__aenter__.return_value.get.side_effect = Exception("Connection refused")

            status = await health_monitor.check_research_agent()

            assert status == AgentStatus.DOWN

    @pytest.mark.asyncio
    async def test_check_context_core_healthy(self, health_monitor):
        """Test Context Core health check - healthy status."""
        with patch('pathlib.Path.exists', return_value=True):
            with patch('src.web.health_monitor.Path.is_dir', return_value=True):
                # Mock successful import
                with patch('sys.path'):
                    with patch('builtins.__import__', return_value=MagicMock()):
                        status = await health_monitor.check_context_core()

                        assert status == AgentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_check_context_core_path_missing(self, health_monitor):
        """Test Context Core health check - path doesn't exist."""
        with patch('pathlib.Path.exists', return_value=False):
            status = await health_monitor.check_context_core()

            assert status == AgentStatus.DOWN

    @pytest.mark.asyncio
    async def test_check_pr_agent_healthy(self, health_monitor):
        """Test PR-Agent health check - healthy status."""
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = True
        mock_path.__truediv__.return_value.exists.return_value = True  # For file checks

        with patch('pathlib.Path', return_value=mock_path):
            status = await health_monitor.check_pr_agent()

            assert status == AgentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_check_ollama_healthy(self, health_monitor):
        """Test Ollama health check - healthy with model available."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "models": [
                {"name": "llama3.1:8b-instruct-q8_0"},
            ]
        })

        with patch('aiohttp.ClientSession') as mock_session:
            mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response

            status = await health_monitor.check_ollama()

            assert status == AgentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_check_ollama_degraded(self, health_monitor):
        """Test Ollama health check - server up but model missing."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "models": [
                {"name": "different-model"},
            ]
        })

        with patch('aiohttp.ClientSession') as mock_session:
            mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response

            status = await health_monitor.check_ollama()

            assert status == AgentStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_check_redis_healthy(self, health_monitor):
        """Test Redis health check - healthy status."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.close = AsyncMock()

        with patch('redis.asyncio.from_url', return_value=mock_client):
            status = await health_monitor.check_redis()

            assert status == AgentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_check_redis_down(self, health_monitor):
        """Test Redis health check - connection error."""
        with patch('redis.asyncio.from_url', side_effect=Exception("Connection refused")):
            status = await health_monitor.check_redis()

            assert status == AgentStatus.DOWN

    @pytest.mark.asyncio
    async def test_check_all(self, health_monitor):
        """Test checking all agents at once."""
        # Mock all individual checks
        health_monitor.check_research_agent = AsyncMock(return_value=AgentStatus.HEALTHY)
        health_monitor.check_context_core = AsyncMock(return_value=AgentStatus.HEALTHY)
        health_monitor.check_pr_agent = AsyncMock(return_value=AgentStatus.HEALTHY)
        health_monitor.check_ollama = AsyncMock(return_value=AgentStatus.HEALTHY)
        health_monitor.check_redis = AsyncMock(return_value=AgentStatus.HEALTHY)

        results = await health_monitor.check_all()

        assert results["research"] == AgentStatus.HEALTHY
        assert results["context"] == AgentStatus.HEALTHY
        assert results["pr"] == AgentStatus.HEALTHY
        assert results["ollama"] == AgentStatus.HEALTHY
        assert results["redis"] == AgentStatus.HEALTHY

    def test_get_overall_status_healthy(self, health_monitor):
        """Test overall status - all healthy."""
        health = {
            "research": AgentStatus.HEALTHY,
            "context": AgentStatus.HEALTHY,
            "pr": AgentStatus.HEALTHY,
            "ollama": AgentStatus.HEALTHY,
            "redis": AgentStatus.HEALTHY,
        }

        status = health_monitor.get_overall_status(health)

        assert status == "healthy"

    def test_get_overall_status_degraded(self, health_monitor):
        """Test overall status - one agent degraded."""
        health = {
            "research": AgentStatus.DEGRADED,
            "context": AgentStatus.HEALTHY,
            "pr": AgentStatus.HEALTHY,
            "ollama": AgentStatus.HEALTHY,
            "redis": AgentStatus.HEALTHY,
        }

        status = health_monitor.get_overall_status(health)

        assert status == "degraded"

    def test_get_overall_status_down_critical(self, health_monitor):
        """Test overall status - critical service down."""
        health = {
            "research": AgentStatus.HEALTHY,
            "context": AgentStatus.HEALTHY,
            "pr": AgentStatus.HEALTHY,
            "ollama": AgentStatus.DOWN,  # Critical service
            "redis": AgentStatus.HEALTHY,
        }

        status = health_monitor.get_overall_status(health)

        assert status == "down"

    def test_get_health_monitor_singleton(self):
        """Test singleton pattern for get_health_monitor."""
        monitor1 = get_health_monitor()
        monitor2 = get_health_monitor()

        assert monitor1 is monitor2
