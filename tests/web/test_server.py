"""
Tests for FastAPI Server Endpoints
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from src.web.server import app
from src.web.models import AgentStatus
from src.state.schemas import TaskStatus


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_health_monitor():
    """Mock health monitor."""
    monitor = MagicMock()
    monitor.check_all = AsyncMock(return_value={
        "research": AgentStatus.HEALTHY,
        "context": AgentStatus.HEALTHY,
        "pr": AgentStatus.HEALTHY,
        "ollama": AgentStatus.HEALTHY,
        "redis": AgentStatus.HEALTHY,
    })
    monitor.get_overall_status = MagicMock(return_value="healthy")
    monitor.settings = MagicMock()
    return monitor


@pytest.fixture
def mock_task_manager():
    """Mock task manager."""
    manager = MagicMock()
    return manager


@pytest.fixture
def mock_analytics_service():
    """Mock analytics service."""
    service = MagicMock()
    service.get_overview.return_value = {
        'time_window_days': 7,
        'tasks': {},
        'agents': {},
        'approvals': {},
        'routing': {},
        'performance': {},
    }
    return service


class TestHealthEndpoint:
    """Test /api/health endpoint."""

    def test_health_check_healthy(self, client, mock_health_monitor):
        """Test health check - all systems healthy."""
        with patch('src.web.server.get_health_monitor', return_value=mock_health_monitor):
            response = client.get("/api/health")

            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'healthy'
            assert data['agents']['research'] == 'healthy'
            assert data['agents']['ollama'] == 'healthy'

    def test_health_check_degraded(self, client, mock_health_monitor):
        """Test health check - degraded status."""
        mock_health_monitor.check_all = AsyncMock(return_value={
            "research": AgentStatus.DEGRADED,
            "context": AgentStatus.HEALTHY,
            "pr": AgentStatus.HEALTHY,
            "ollama": AgentStatus.HEALTHY,
            "redis": AgentStatus.HEALTHY,
        })
        mock_health_monitor.get_overall_status = MagicMock(return_value="degraded")

        with patch('src.web.server.get_health_monitor', return_value=mock_health_monitor):
            response = client.get("/api/health")

            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'degraded'


class TestAnalyticsEndpoints:
    """Test /api/analytics/* endpoints."""

    def test_get_analytics_overview(self, client, mock_analytics_service):
        """Test analytics overview endpoint."""
        with patch('src.web.server.get_analytics_service', return_value=mock_analytics_service):
            response = client.get("/api/analytics/overview")

            assert response.status_code == 200
            data = response.json()
            assert 'time_window_days' in data
            assert 'tasks' in data
            assert 'agents' in data

    def test_get_analytics_overview_custom_days(self, client, mock_analytics_service):
        """Test analytics overview with custom time window."""
        with patch('src.web.server.get_analytics_service', return_value=mock_analytics_service):
            response = client.get("/api/analytics/overview?days=14")

            assert response.status_code == 200
            mock_analytics_service.get_overview.assert_called_once_with(days=14)

    def test_get_task_analytics(self, client, mock_analytics_service):
        """Test task analytics endpoint."""
        mock_analytics_service.get_task_statistics.return_value = {
            'total_tasks': 10,
            'success_rate': 80.0,
        }

        with patch('src.web.server.get_analytics_service', return_value=mock_analytics_service):
            response = client.get("/api/analytics/tasks")

            assert response.status_code == 200
            data = response.json()
            assert data['total_tasks'] == 10
            assert data['success_rate'] == 80.0

    def test_get_agent_analytics(self, client, mock_analytics_service):
        """Test agent analytics endpoint."""
        mock_analytics_service.get_agent_statistics.return_value = {
            'research': {'total_calls': 5},
        }

        with patch('src.web.server.get_analytics_service', return_value=mock_analytics_service):
            response = client.get("/api/analytics/agents")

            assert response.status_code == 200
            data = response.json()
            assert 'research' in data


class TestTaskEndpoints:
    """Test /api/tasks/* endpoints."""

    def test_create_task(self, client, mock_task_manager):
        """Test task creation endpoint."""
        mock_state = MagicMock()
        mock_state.task_id = "test-task-123"
        mock_state.created_at = "2026-02-18T00:00:00"
        mock_task_manager.start_task = AsyncMock(return_value=mock_state)

        with patch('src.web.server.get_task_manager', return_value=mock_task_manager):
            response = client.post(
                "/api/tasks",
                json={
                    "objective": "Test task",
                    "max_iterations": 5,
                    "routing_strategy": "adaptive",
                    "enable_hitl": True,
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert data['task_id'] == "test-task-123"
            assert 'stream_url' in data

    def test_create_task_empty_objective(self, client):
        """Test task creation with empty objective."""
        response = client.post(
            "/api/tasks",
            json={
                "objective": "   ",
            }
        )

        assert response.status_code == 400

    def test_list_tasks(self, client, mock_task_manager):
        """Test listing tasks."""
        mock_task_manager.list_tasks.return_value = [
            {
                'task_id': 'task-1',
                'objective': 'Test 1',
                'status': 'completed',
            },
            {
                'task_id': 'task-2',
                'objective': 'Test 2',
                'status': 'running',
            },
        ]

        with patch('src.web.server.get_task_manager', return_value=mock_task_manager):
            response = client.get("/api/tasks")

            assert response.status_code == 200
            data = response.json()
            assert data['total'] == 2
            assert len(data['tasks']) == 2


class TestHTMLPages:
    """Test HTML page endpoints."""

    def test_dashboard_page(self, client):
        """Test dashboard page renders."""
        response = client.get("/")
        assert response.status_code == 200
        assert b"Command Center" in response.content

    def test_approvals_page(self, client):
        """Test approvals page renders."""
        response = client.get("/approvals")
        assert response.status_code == 200
        assert b"Approvals" in response.content

    def test_history_page(self, client):
        """Test history page renders."""
        response = client.get("/history")
        assert response.status_code == 200
        assert b"History" in response.content

    def test_analytics_page(self, client):
        """Test analytics page renders."""
        response = client.get("/analytics")
        assert response.status_code == 200
        assert b"Analytics" in response.content


class TestStaticFiles:
    """Test static file serving."""

    def test_css_accessible(self, client):
        """Test CSS files are accessible."""
        response = client.get("/static/css/style.css")
        assert response.status_code == 200

    def test_js_accessible(self, client):
        """Test JavaScript files are accessible."""
        response = client.get("/static/js/dashboard.js")
        assert response.status_code == 200
