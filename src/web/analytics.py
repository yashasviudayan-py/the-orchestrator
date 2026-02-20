"""
Analytics and Statistics Module

Provides analytics data for:
- Task completion metrics
- Agent usage patterns
- Approval statistics
- Routing decisions
- Performance metrics
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from collections import defaultdict

from ..state.schemas import TaskStatus, AgentType
from .task_manager import get_task_manager
from ..api.approval_manager import get_approval_manager
from ..api.approval import ApprovalStatus, RiskLevel

logger = logging.getLogger(__name__)


def _get(task, key, default=None):
    """Get a field from either a dict or an object, parsing datetime strings."""
    if isinstance(task, dict):
        val = task.get(key, default)
        if val and key in ('created_at', 'updated_at', 'completed_at') and isinstance(val, str):
            try:
                dt = datetime.fromisoformat(val)
                # Ensure timezone-aware so comparisons with timezone.utc cutoff work
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (ValueError, TypeError):
                return default
        return val
    val = getattr(task, key, default)
    # Also normalise datetime attributes on objects
    if val is not None and key in ('created_at', 'updated_at', 'completed_at') and isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc)
    return val


def _status_str(task) -> str:
    """Get task status as a plain string from either a dict or an object."""
    status = _get(task, 'status')
    if status is None:
        return ''
    if isinstance(status, str):
        return status
    return status.value if hasattr(status, 'value') else str(status)


class AnalyticsService:
    """Service for collecting and computing analytics."""

    def __init__(self):
        try:
            self.task_manager = get_task_manager()
        except Exception:
            self.task_manager = None
        try:
            self.approval_manager = get_approval_manager()
        except Exception:
            self.approval_manager = None

    def get_task_statistics(self, days: int = 7) -> Dict:
        """
        Get task-level statistics.

        Args:
            days: Number of days to look back

        Returns:
            Dictionary with task statistics
        """
        if not self.task_manager:
            return {
                'total_tasks': 0, 'status_breakdown': {}, 'success_rate': 0.0,
                'average_iterations': 0.0, 'completed': 0, 'failed': 0,
                'pending': 0, 'running': 0,
            }
        all_tasks = self.task_manager.list_tasks(limit=1000)

        # Filter by time window
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent_tasks = [
            t for t in all_tasks
            if _get(t, 'created_at') and _get(t, 'created_at') > cutoff
        ]

        # Count by status
        status_counts = defaultdict(int)
        for task in recent_tasks:
            status_counts[_status_str(task)] += 1

        # Calculate success rate
        completed = status_counts.get('completed', 0)
        failed = status_counts.get('failed', 0)
        total = completed + failed
        success_rate = (completed / total * 100) if total > 0 else 0

        # Average iterations
        iterations = [
            _get(task, 'iteration', 0)
            for task in recent_tasks
            if _status_str(task) == 'completed'
        ]
        avg_iterations = sum(iterations) / len(iterations) if iterations else 0

        return {
            'total_tasks': len(recent_tasks),
            'status_breakdown': dict(status_counts),
            'success_rate': round(success_rate, 1),
            'average_iterations': round(avg_iterations, 1),
            'completed': completed,
            'failed': failed,
            'pending': status_counts.get('pending', 0),
            'running': status_counts.get('running', 0),
        }

    def get_agent_statistics(self, days: int = 7) -> Dict:
        """
        Get agent usage statistics.

        Args:
            days: Number of days to look back

        Returns:
            Dictionary with agent usage stats
        """
        if not self.task_manager:
            return {a: {'total_calls': 0, 'successful': 0, 'errors': 0, 'success_rate': 0.0}
                    for a in ['research', 'context', 'pr']}
        all_tasks = self.task_manager.list_tasks(limit=1000)

        # Filter by time window
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent_tasks = [
            t for t in all_tasks
            if _get(t, 'created_at') and _get(t, 'created_at') > cutoff
        ]

        # Count agent invocations from full task states
        # Note: TaskInfo doesn't have messages, so we need to get full states
        agent_counts = defaultdict(int)
        agent_success = defaultdict(int)
        agent_errors = defaultdict(int)

        for task_info in recent_tasks:
            # Use inline messages if present (dict tasks), otherwise fetch full state
            inline_messages = _get(task_info, 'messages')
            if inline_messages is not None:
                messages = inline_messages
            else:
                task_state = self.task_manager.get_task(_get(task_info, 'task_id'))
                if not task_state or not hasattr(task_state, 'messages'):
                    continue
                messages = task_state.messages

            for msg in messages:
                agent = msg.get('agent_name') if isinstance(msg, dict) else getattr(msg, 'agent_name', None)
                if agent:
                    agent_counts[agent] += 1

                    # Track success/errors (simplified)
                    content = msg.get('content', {}) if isinstance(msg, dict) else getattr(msg, 'content', {})
                    msg_type = content.get('type', '') if isinstance(content, dict) else ''
                    if 'error' in msg_type.lower():
                        agent_errors[agent] += 1
                    else:
                        agent_success[agent] += 1

        # Build agent stats
        agent_stats = {}
        for agent in ['research', 'context', 'pr']:
            total = agent_counts.get(agent, 0)
            success = agent_success.get(agent, 0)
            errors = agent_errors.get(agent, 0)
            success_rate = (success / total * 100) if total > 0 else 0

            agent_stats[agent] = {
                'total_calls': total,
                'successful': success,
                'errors': errors,
                'success_rate': round(success_rate, 1),
            }

        return agent_stats

    def get_approval_statistics(self, days: int = 7) -> Dict:
        """
        Get approval statistics.

        Args:
            days: Number of days to look back

        Returns:
            Dictionary with approval stats
        """
        if not self.approval_manager:
            return {
                'total_requests': 0, 'status_breakdown': {}, 'risk_breakdown': {},
                'approval_rate': 0.0, 'average_response_time': 0.0,
                'approved': 0, 'rejected': 0, 'pending': 0, 'timeout': 0,
            }
        all_history = self.approval_manager.get_history(limit=1000)

        # Filter by time window
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        def _aware(dt: datetime) -> datetime:
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

        recent_approvals = [
            a for a in all_history
            if _aware(a.created_at) > cutoff
        ]

        # Count by status
        status_counts = defaultdict(int)
        for approval in recent_approvals:
            status_counts[approval.status.value] += 1

        # Count by risk level
        risk_counts = defaultdict(int)
        for approval in recent_approvals:
            risk_counts[approval.risk_level.value] += 1

        # Calculate approval rate
        approved = status_counts.get('approved', 0)
        rejected = status_counts.get('rejected', 0)
        total = approved + rejected
        approval_rate = (approved / total * 100) if total > 0 else 0

        # Average response time (time from created to decided)
        response_times = []
        for approval in recent_approvals:
            if approval.decided_at:
                delta = (approval.decided_at - approval.created_at).total_seconds()
                response_times.append(delta)

        avg_response_time = sum(response_times) / len(response_times) if response_times else 0

        return {
            'total_requests': len(recent_approvals),
            'status_breakdown': dict(status_counts),
            'risk_breakdown': dict(risk_counts),
            'approval_rate': round(approval_rate, 1),
            'average_response_time': round(avg_response_time, 1),
            'approved': approved,
            'rejected': rejected,
            'pending': status_counts.get('pending', 0),
            'timeout': status_counts.get('timeout', 0),
        }

    def get_routing_statistics(self, days: int = 7) -> Dict:
        """
        Get routing decision statistics.

        Args:
            days: Number of days to look back

        Returns:
            Dictionary with routing stats
        """
        if not self.task_manager:
            return {'strategy_usage': {}, 'top_transitions': {}, 'total_transitions': 0}
        all_tasks = self.task_manager.list_tasks(limit=1000)

        # Filter by time window
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent_tasks = [
            t for t in all_tasks
            if _get(t, 'created_at') and _get(t, 'created_at') > cutoff
        ]

        # Count routing strategy usage
        strategy_counts = defaultdict(int)
        for task in recent_tasks:
            strategy = _get(task, 'routing_strategy')
            strategy_counts[strategy] += 1

        # Count transitions between agents
        transition_counts = defaultdict(int)
        for task_info in recent_tasks:
            # Use inline messages if present (dict tasks), otherwise fetch full state
            inline_messages = _get(task_info, 'messages')
            if inline_messages is not None:
                messages = inline_messages
            else:
                task_state = self.task_manager.get_task(_get(task_info, 'task_id'))
                if not task_state or not hasattr(task_state, 'messages'):
                    continue
                messages = task_state.messages

            agents = [
                (m.get('agent_name') if isinstance(m, dict) else getattr(m, 'agent_name', None))
                for m in messages
                if (m.get('agent_name') if isinstance(m, dict) else getattr(m, 'agent_name', None))
            ]

            # Count transitions
            for i in range(len(agents) - 1):
                transition = f"{agents[i]} → {agents[i+1]}"
                transition_counts[transition] += 1

        # Sort transitions by frequency
        top_transitions = sorted(
            transition_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        return {
            'strategy_usage': dict(strategy_counts),
            'top_transitions': dict(top_transitions),
            'total_transitions': sum(transition_counts.values()),
        }

    def get_performance_metrics(self, days: int = 7) -> Dict:
        """
        Get performance metrics.

        Args:
            days: Number of days to look back

        Returns:
            Dictionary with performance metrics
        """
        if not self.task_manager:
            return {
                'average_completion_time': 0.0, 'min_completion_time': 0.0,
                'max_completion_time': 0.0, 'total_completed': 0,
            }
        all_tasks = self.task_manager.list_tasks(limit=1000)

        # Filter by time window
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent_tasks = [
            t for t in all_tasks
            if _get(t, 'created_at') and _get(t, 'created_at') > cutoff
        ]

        # Calculate task completion times
        completion_times = []
        for task in recent_tasks:
            completed_at = _get(task, 'completed_at')
            created_at = _get(task, 'created_at')
            if _status_str(task) == 'completed' and completed_at and created_at:
                duration = (completed_at - created_at).total_seconds()
                completion_times.append(duration)

        avg_completion_time = sum(completion_times) / len(completion_times) if completion_times else 0
        min_time = min(completion_times) if completion_times else 0
        max_time = max(completion_times) if completion_times else 0

        return {
            'average_completion_time': round(avg_completion_time, 1),
            'min_completion_time': round(min_time, 1),
            'max_completion_time': round(max_time, 1),
            'total_completed': len(completion_times),
        }

    def get_overview(self, days: int = 7) -> Dict:
        """
        Get complete analytics overview.

        Args:
            days: Number of days to look back

        Returns:
            Complete analytics dictionary
        """
        return {
            'time_window_days': days,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'tasks': self.get_task_statistics(days),
            'agents': self.get_agent_statistics(days),
            'approvals': self.get_approval_statistics(days),
            'routing': self.get_routing_statistics(days),
            'performance': self.get_performance_metrics(days),
        }


# Singleton instance
_analytics_service: Optional[AnalyticsService] = None


def get_analytics_service() -> AnalyticsService:
    """Get the global AnalyticsService instance."""
    global _analytics_service
    if _analytics_service is None:
        _analytics_service = AnalyticsService()
    return _analytics_service
