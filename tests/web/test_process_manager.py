"""
Tests for ProcessManager and service-control API endpoints.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.web.process_manager import (
    ProcessManager,
    ServiceNotControllableError,
    get_process_manager,
)


# ═══════════════════════════════════════════════════════════════════════
# ProcessManager unit tests
# ═══════════════════════════════════════════════════════════════════════


class TestIsControllable:
    def test_ollama_is_controllable(self):
        pm = ProcessManager()
        assert pm.is_controllable("ollama") is True

    def test_redis_is_controllable(self):
        pm = ProcessManager()
        assert pm.is_controllable("redis") is True

    def test_research_is_not_controllable(self):
        pm = ProcessManager()
        assert pm.is_controllable("research") is False

    def test_context_is_not_controllable(self):
        pm = ProcessManager()
        assert pm.is_controllable("context") is False

    def test_pr_is_not_controllable(self):
        pm = ProcessManager()
        assert pm.is_controllable("pr") is False

    def test_unknown_service_is_not_controllable(self):
        pm = ProcessManager()
        assert pm.is_controllable("unicorn") is False


class TestStartService:
    @pytest.mark.asyncio
    async def test_raises_for_non_controllable_service(self):
        pm = ProcessManager()
        with pytest.raises(ServiceNotControllableError):
            await pm.start_service("research")

    @pytest.mark.asyncio
    async def test_returns_false_when_binary_missing(self):
        pm = ProcessManager()
        with patch("shutil.which", return_value=None):
            success, msg = await pm.start_service("redis")
        assert success is False
        assert "not found" in msg

    @pytest.mark.asyncio
    async def test_starts_long_running_daemon(self):
        """ollama is a long-running daemon — should not be awaited."""
        pm = ProcessManager()
        mock_proc = MagicMock()
        mock_proc.pid = 12345

        with patch("shutil.which", return_value="/usr/bin/ollama"), \
             patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
            success, msg = await pm.start_service("ollama")

        assert success is True
        assert "12345" in msg
        assert "ollama" in pm._handles

    @pytest.mark.asyncio
    async def test_starts_short_lived_command(self):
        """redis uses brew services — awaits the process."""
        pm = ProcessManager()
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("shutil.which", return_value="/usr/bin/brew"), \
             patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
            success, msg = await pm.start_service("redis")

        assert success is True
        assert "redis" in msg.lower()

    @pytest.mark.asyncio
    async def test_start_returns_false_on_nonzero_exit(self):
        pm = ProcessManager()
        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"some error"))

        with patch("shutil.which", return_value="/usr/bin/brew"), \
             patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
            success, msg = await pm.start_service("redis")

        assert success is False
        assert "some error" in msg


class TestStopService:
    @pytest.mark.asyncio
    async def test_raises_for_non_controllable_service(self):
        pm = ProcessManager()
        with pytest.raises(ServiceNotControllableError):
            await pm.stop_service("pr")

    @pytest.mark.asyncio
    async def test_terminates_stored_handle(self):
        """If we have a stored handle (daemon), terminate it directly."""
        pm = ProcessManager()
        mock_handle = MagicMock()  # use MagicMock so terminate() is sync
        mock_handle.wait = AsyncMock(return_value=0)
        pm._handles["ollama"] = mock_handle

        success, msg = await pm.stop_service("ollama")

        mock_handle.terminate.assert_called_once()
        assert success is True
        assert "ollama" not in pm._handles

    @pytest.mark.asyncio
    async def test_stop_via_command(self):
        pm = ProcessManager()
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("shutil.which", return_value="/usr/bin/brew"), \
             patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
            success, msg = await pm.stop_service("redis")

        assert success is True

    @pytest.mark.asyncio
    async def test_stop_treats_pkill_code1_as_not_running(self):
        """pkill returns 1 if no matching process — treat as success."""
        pm = ProcessManager()
        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"no process found"))

        with patch("shutil.which", return_value="/usr/bin/pkill"), \
             patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
            success, msg = await pm.stop_service("ollama")

        assert success is True
        assert "not running" in msg.lower()


# ═══════════════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════════════


def test_singleton_returns_same_instance():
    # Reset global state
    import src.web.process_manager as pm_module
    pm_module._process_manager = None

    pm1 = get_process_manager()
    pm2 = get_process_manager()
    assert pm1 is pm2


# ═══════════════════════════════════════════════════════════════════════
# API endpoint tests
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def client():
    """Create a TestClient for the FastAPI app."""
    from src.web.server import app
    return TestClient(app, raise_server_exceptions=False)


class TestServiceAPIEndpoints:
    def test_start_unknown_service_returns_404(self, client):
        response = client.post("/api/services/unicorn/start")
        assert response.status_code == 404

    def test_stop_unknown_service_returns_404(self, client):
        response = client.post("/api/services/unicorn/stop")
        assert response.status_code == 404

    def test_start_non_controllable_service_returns_400(self, client):
        response = client.post("/api/services/research/start")
        assert response.status_code == 400
        assert "cannot be started" in response.json()["detail"].lower()

    def test_stop_non_controllable_service_returns_400(self, client):
        response = client.post("/api/services/pr/stop")
        assert response.status_code == 400

    def test_start_controllable_service_returns_200(self, client):
        with patch(
            "src.web.process_manager.ProcessManager.start_service",
            new=AsyncMock(return_value=(True, "ollama started")),
        ):
            response = client.post("/api/services/ollama/start")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["service"] == "ollama"

    def test_stop_controllable_service_returns_200(self, client):
        with patch(
            "src.web.process_manager.ProcessManager.stop_service",
            new=AsyncMock(return_value=(True, "redis stopped")),
        ):
            response = client.post("/api/services/redis/stop")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["service"] == "redis"
