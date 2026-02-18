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
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict

from ..state.schemas import TaskStatus, AgentType
from .task_manager import get_task_manager
from ..api.approval_manager import get_approval_manager
from ..api.approval import ApprovalStatus, RiskLevel

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service for collecting and computing analytics."""

    def __init__(self):
        self.task_manager = get_task_manager()
        self.approval_manager = get_approval_manager()

    def get_task_statistics(self, days: int = 7) -> Dict:
        """
        Get task-level statistics.

        Args:
            days: Number of days to look back

        Returns:
            Dictionary with task statistics
        """
        all_tasks = self.task_manager.list_tasks(limit=1000)

        # Filter by time window
        cutoff = datetime.now() - timedelta(days=days)
        recent_tasks = [
            t for t in all_tasks
            if t.created_at and t.created_at > cutoff
        ]

        # Count by status
        status_counts = defaultdict(int)
        for task in recent_tasks:
            status = task.status.value if hasattr(task.status, 'value') else str(task.status)
            status_counts[status] += 1

        # Calculate success rate
        completed = status_counts.get('completed', 0)
        failed = status_counts.get('failed', 0)
        total = completed + failed
        success_rate = (completed / total * 100) if total > 0 else 0

        # Average iterations
        iterations = [
            task.iteration
            for task in recent_tasks
            if (task.status.value if hasattr(task.status, 'value') else str(task.status)) == 'completed'
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
        all_tasks = self.task_manager.list_tasks(limit=1000)

        # Filter by time window
        cutoff = datetime.now() - timedelta(days=days)
        recent_tasks = [
            t for t in all_tasks
            if t.created_at and t.created_at > cutoff
        ]

        # Count agent invocations from full task states
        # Note: TaskInfo doesn't have messages, so we need to get full states
        agent_counts = defaultdict(int)
        agent_success = defaultdict(int)
        agent_errors = defaultdict(int)

        for task_info in recent_tasks:
            # Get full task state to access messages
            task_state = self.task_manager.get_task(task_info.task_id)
            if not task_state or not hasattr(task_state, 'messages'):
                continue

            for msg in task_state.messages:
                agent = getattr(msg, 'agent_name', None)
                if agent:
                    agent_counts[agent] += 1

                    # Track success/errors (simplified)
                    content = getattr(msg, 'content', {})
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
        all_history = self.approval_manager.get_history(limit=1000)

        # Filter by time window
        cutoff = datetime.now() - timedelta(days=days)
        recent_approvals = [
            a for a in all_history
            if a.created_at > cutoff
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
        all_tasks = self.task_manager.list_tasks(limit=1000)

        # Filter by time window
        cutoff = datetime.now() - timedelta(days=days)
        recent_tasks = [
            t for t in all_tasks
            if t.created_at and t.created_at > cutoff
        ]

        # Count routing strategy usage
        strategy_counts = defaultdict(int)
        for task in recent_tasks:
            strategy = task.routing_strategy
            strategy_counts[strategy] += 1

        # Count transitions between agents
        transition_counts = defaultdict(int)
        for task_info in recent_tasks:
            # Get full task state to access messages
            task_state = self.task_manager.get_task(task_info.task_id)
            if not task_state or not hasattr(task_state, 'messages'):
                continue

            agents = [
                getattr(m, 'agent_name', None)
                for m in task_state.messages
                if getattr(m, 'agent_name', None)
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
        all_tasks = self.task_manager.list_tasks(limit=1000)

        # Filter by time window
        cutoff = datetime.now() - timedelta(days=days)
        recent_tasks = [
            t for t in all_tasks
            if t.created_at and t.created_at > cutoff
        ]

        # Calculate task completion times
        completion_times = []
        for task in recent_tasks:
            status_val = task.status.value if hasattr(task.status, 'value') else str(task.status)
            if status_val == 'completed' and task.completed_at:
                duration = (task.completed_at - task.created_at).total_seconds()
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
            'generated_at': datetime.now().isoformat(),
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
