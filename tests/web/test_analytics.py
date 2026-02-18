"""
Tests for Analytics Service
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from src.web.analytics import AnalyticsService, get_analytics_service


@pytest.fixture
def mock_task_manager():
    """Mock task manager."""
    manager = MagicMock()
    return manager


@pytest.fixture
def mock_approval_manager():
    """Mock approval manager."""
    manager = MagicMock()
    return manager


@pytest.fixture
def analytics_service(mock_task_manager, mock_approval_manager):
    """Create analytics service instance."""
    with patch('src.web.analytics.get_task_manager', return_value=mock_task_manager):
        with patch('src.web.analytics.get_approval_manager', return_value=mock_approval_manager):
            service = AnalyticsService()
            return service


class TestAnalyticsService:
    """Test AnalyticsService class."""

    def test_get_task_statistics_no_tasks(self, analytics_service, mock_task_manager):
        """Test task statistics with no tasks."""
        mock_task_manager.list_tasks.return_value = []

        stats = analytics_service.get_task_statistics(days=7)

        assert stats['total_tasks'] == 0
        assert stats['success_rate'] == 0
        assert stats['average_iterations'] == 0
        assert stats['completed'] == 0
        assert stats['failed'] == 0

    def test_get_task_statistics_with_tasks(self, analytics_service, mock_task_manager):
        """Test task statistics with sample tasks."""
        now = datetime.now()
        mock_tasks = [
            {
                'created_at': now.isoformat(),
                'status': 'completed',
                'iteration': 3,
            },
            {
                'created_at': now.isoformat(),
                'status': 'completed',
                'iteration': 5,
            },
            {
                'created_at': now.isoformat(),
                'status': 'failed',
                'iteration': 2,
            },
            {
                'created_at': now.isoformat(),
                'status': 'pending',
                'iteration': 0,
            },
        ]
        mock_task_manager.list_tasks.return_value = mock_tasks

        stats = analytics_service.get_task_statistics(days=7)

        assert stats['total_tasks'] == 4
        assert stats['completed'] == 2
        assert stats['failed'] == 1
        assert stats['pending'] == 1
        assert stats['success_rate'] == 66.7  # 2 completed out of 3 (completed + failed)
        assert stats['average_iterations'] == 4.0  # (3 + 5) / 2

    def test_get_agent_statistics_no_data(self, analytics_service, mock_task_manager):
        """Test agent statistics with no data."""
        mock_task_manager.list_tasks.return_value = []

        stats = analytics_service.get_agent_statistics(days=7)

        assert stats['research']['total_calls'] == 0
        assert stats['context']['total_calls'] == 0
        assert stats['pr']['total_calls'] == 0

    def test_get_agent_statistics_with_messages(self, analytics_service, mock_task_manager):
        """Test agent statistics with agent messages."""
        now = datetime.now()
        mock_tasks = [
            {
                'created_at': now.isoformat(),
                'messages': [
                    {'agent_name': 'research', 'content': {'type': 'result'}},
                    {'agent_name': 'research', 'content': {'type': 'result'}},
                    {'agent_name': 'context', 'content': {'type': 'result'}},
                    {'agent_name': 'pr', 'content': {'type': 'error'}},
                ],
            },
        ]
        mock_task_manager.list_tasks.return_value = mock_tasks

        stats = analytics_service.get_agent_statistics(days=7)

        assert stats['research']['total_calls'] == 2
        assert stats['research']['successful'] == 2
        assert stats['research']['errors'] == 0
        assert stats['research']['success_rate'] == 100.0

        assert stats['pr']['total_calls'] == 1
        assert stats['pr']['errors'] == 1
        assert stats['pr']['success_rate'] == 0.0

    def test_get_approval_statistics_no_approvals(self, analytics_service, mock_approval_manager):
        """Test approval statistics with no approvals."""
        mock_approval_manager.get_history.return_value = []

        stats = analytics_service.get_approval_statistics(days=7)

        assert stats['total_requests'] == 0
        assert stats['approval_rate'] == 0
        assert stats['average_response_time'] == 0

    def test_get_approval_statistics_with_approvals(self, analytics_service, mock_approval_manager):
        """Test approval statistics with sample approvals."""
        now = datetime.now()
        mock_approvals = [
            MagicMock(
                created_at=now,
                decided_at=now + timedelta(seconds=30),
                status=MagicMock(value='approved'),
                risk_level=MagicMock(value='medium'),
            ),
            MagicMock(
                created_at=now,
                decided_at=now + timedelta(seconds=60),
                status=MagicMock(value='approved'),
                risk_level=MagicMock(value='high'),
            ),
            MagicMock(
                created_at=now,
                decided_at=now + timedelta(seconds=45),
                status=MagicMock(value='rejected'),
                risk_level=MagicMock(value='critical'),
            ),
        ]
        mock_approval_manager.get_history.return_value = mock_approvals

        stats = analytics_service.get_approval_statistics(days=7)

        assert stats['total_requests'] == 3
        assert stats['approved'] == 2
        assert stats['rejected'] == 1
        assert stats['approval_rate'] == 66.7  # 2 out of 3
        assert stats['average_response_time'] == 45.0  # (30 + 60 + 45) / 3

    def test_get_routing_statistics_no_data(self, analytics_service, mock_task_manager):
        """Test routing statistics with no data."""
        mock_task_manager.list_tasks.return_value = []

        stats = analytics_service.get_routing_statistics(days=7)

        assert stats['total_transitions'] == 0
        assert len(stats['top_transitions']) == 0

    def test_get_routing_statistics_with_transitions(self, analytics_service, mock_task_manager):
        """Test routing statistics with agent transitions."""
        now = datetime.now()
        mock_tasks = [
            {
                'created_at': now.isoformat(),
                'routing_strategy': 'adaptive',
                'messages': [
                    {'agent_name': 'research'},
                    {'agent_name': 'context'},
                    {'agent_name': 'pr'},
                ],
            },
            {
                'created_at': now.isoformat(),
                'routing_strategy': 'adaptive',
                'messages': [
                    {'agent_name': 'research'},
                    {'agent_name': 'context'},
                ],
            },
        ]
        mock_task_manager.list_tasks.return_value = mock_tasks

        stats = analytics_service.get_routing_statistics(days=7)

        assert stats['total_transitions'] == 3  # research→context (x2), context→pr (x1)
        assert 'research → context' in stats['top_transitions']
        assert stats['top_transitions']['research → context'] == 2

    def test_get_performance_metrics_no_data(self, analytics_service, mock_task_manager):
        """Test performance metrics with no completed tasks."""
        mock_task_manager.list_tasks.return_value = []

        stats = analytics_service.get_performance_metrics(days=7)

        assert stats['average_completion_time'] == 0
        assert stats['total_completed'] == 0

    def test_get_performance_metrics_with_data(self, analytics_service, mock_task_manager):
        """Test performance metrics with completed tasks."""
        now = datetime.now()
        mock_tasks = [
            {
                'created_at': (now - timedelta(minutes=5)).isoformat(),
                'completed_at': now.isoformat(),
                'status': 'completed',
            },
            {
                'created_at': (now - timedelta(minutes=10)).isoformat(),
                'completed_at': now.isoformat(),
                'status': 'completed',
            },
        ]
        mock_task_manager.list_tasks.return_value = mock_tasks

        stats = analytics_service.get_performance_metrics(days=7)

        assert stats['total_completed'] == 2
        assert stats['average_completion_time'] > 0
        assert stats['min_completion_time'] > 0
        assert stats['max_completion_time'] > 0

    def test_get_overview(self, analytics_service, mock_task_manager, mock_approval_manager):
        """Test getting complete overview."""
        mock_task_manager.list_tasks.return_value = []
        mock_approval_manager.get_history.return_value = []

        overview = analytics_service.get_overview(days=7)

        assert 'time_window_days' in overview
        assert overview['time_window_days'] == 7
        assert 'tasks' in overview
        assert 'agents' in overview
        assert 'approvals' in overview
        assert 'routing' in overview
        assert 'performance' in overview
        assert 'generated_at' in overview

    def test_get_analytics_service_singleton(self):
        """Test singleton pattern for get_analytics_service."""
        service1 = get_analytics_service()
        service2 = get_analytics_service()

        assert service1 is service2
