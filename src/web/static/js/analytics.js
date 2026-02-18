/**
 * The Orchestrator Command Center - Analytics JavaScript
 *
 * Handles:
 * - Loading analytics data
 * - Rendering charts and statistics
 * - Time window selection
 */

// ═══════════════════════════════════════════════════════════════════════
// State Management
// ═══════════════════════════════════════════════════════════════════════

const state = {
    timeWindow: 7,  // days
    analyticsData: null,
    refreshInterval: null,
};

// ═══════════════════════════════════════════════════════════════════════
// DOM Elements
// ═══════════════════════════════════════════════════════════════════════

const elements = {
    timeWindowSelect: document.getElementById('time-window'),
    lastUpdated: document.getElementById('last-updated'),

    // Task stats
    totalTasks: document.getElementById('total-tasks'),
    successRate: document.getElementById('success-rate'),
    avgIterations: document.getElementById('avg-iterations'),
    tasksCompleted: document.getElementById('tasks-completed'),
    tasksFailed: document.getElementById('tasks-failed'),

    // Agent stats
    researchCalls: document.getElementById('research-calls'),
    researchSuccess: document.getElementById('research-success'),
    contextCalls: document.getElementById('context-calls'),
    contextSuccess: document.getElementById('context-success'),
    prCalls: document.getElementById('pr-calls'),
    prSuccess: document.getElementById('pr-success'),

    // Approval stats
    totalApprovals: document.getElementById('total-approvals'),
    approvalRate: document.getElementById('approval-rate'),
    avgResponseTime: document.getElementById('avg-response-time'),
    approvalsApproved: document.getElementById('approvals-approved'),
    approvalsRejected: document.getElementById('approvals-rejected'),

    // Performance stats
    avgCompletionTime: document.getElementById('avg-completion-time'),
    minCompletionTime: document.getElementById('min-completion-time'),
    maxCompletionTime: document.getElementById('max-completion-time'),

    // Charts/lists
    routingTransitions: document.getElementById('routing-transitions'),
    riskBreakdown: document.getElementById('risk-breakdown'),
};

// ═══════════════════════════════════════════════════════════════════════
// API Client
// ═══════════════════════════════════════════════════════════════════════

const api = {
    /**
     * Get analytics overview
     */
    async getOverview(days = 7) {
        const response = await fetch(`/api/analytics/overview?days=${days}`);
        if (!response.ok) throw new Error('Failed to fetch analytics');
        return await response.json();
    },
};

// ═══════════════════════════════════════════════════════════════════════
// Data Loading
// ═══════════════════════════════════════════════════════════════════════

/**
 * Load analytics data
 */
async function loadAnalytics() {
    try {
        const data = await api.getOverview(state.timeWindow);
        state.analyticsData = data;

        renderAnalytics(data);
        updateTimestamp();

    } catch (error) {
        console.error('Failed to load analytics:', error);
        showError('Failed to load analytics data');
    }
}

/**
 * Update last updated timestamp
 */
function updateTimestamp() {
    if (elements.lastUpdated) {
        const now = new Date().toLocaleTimeString();
        elements.lastUpdated.textContent = `Last updated: ${now}`;
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Rendering
// ═══════════════════════════════════════════════════════════════════════

/**
 * Render all analytics
 */
function renderAnalytics(data) {
    renderTaskStats(data.tasks);
    renderAgentStats(data.agents);
    renderApprovalStats(data.approvals);
    renderPerformanceStats(data.performance);
    renderRoutingStats(data.routing);
}

/**
 * Render task statistics
 */
function renderTaskStats(stats) {
    if (!stats) return;

    setText(elements.totalTasks, stats.total_tasks);
    setText(elements.successRate, `${stats.success_rate}%`);
    setText(elements.avgIterations, stats.average_iterations);
    setText(elements.tasksCompleted, stats.completed);
    setText(elements.tasksFailed, stats.failed);
}

/**
 * Render agent statistics
 */
function renderAgentStats(stats) {
    if (!stats) return;

    // Research agent
    if (stats.research) {
        setText(elements.researchCalls, stats.research.total_calls);
        setText(elements.researchSuccess, `${stats.research.success_rate}%`);
    }

    // Context agent
    if (stats.context) {
        setText(elements.contextCalls, stats.context.total_calls);
        setText(elements.contextSuccess, `${stats.context.success_rate}%`);
    }

    // PR agent
    if (stats.pr) {
        setText(elements.prCalls, stats.pr.total_calls);
        setText(elements.prSuccess, `${stats.pr.success_rate}%`);
    }
}

/**
 * Render approval statistics
 */
function renderApprovalStats(stats) {
    if (!stats) return;

    setText(elements.totalApprovals, stats.total_requests);
    setText(elements.approvalRate, `${stats.approval_rate}%`);
    setText(elements.avgResponseTime, formatDuration(stats.average_response_time));
    setText(elements.approvalsApproved, stats.approved);
    setText(elements.approvalsRejected, stats.rejected);

    // Render risk breakdown
    if (elements.riskBreakdown && stats.risk_breakdown) {
        elements.riskBreakdown.innerHTML = Object.entries(stats.risk_breakdown)
            .map(([risk, count]) => `
                <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                    <span class="risk-badge ${risk}">${risk.toUpperCase()}</span>
                    <span style="color: var(--text-secondary); font-weight: 600;">${count}</span>
                </div>
            `)
            .join('');
    }
}

/**
 * Render performance statistics
 */
function renderPerformanceStats(stats) {
    if (!stats) return;

    setText(elements.avgCompletionTime, formatDuration(stats.average_completion_time));
    setText(elements.minCompletionTime, formatDuration(stats.min_completion_time));
    setText(elements.maxCompletionTime, formatDuration(stats.max_completion_time));
}

/**
 * Render routing statistics
 */
function renderRoutingStats(stats) {
    if (!stats) return;

    // Render top transitions
    if (elements.routingTransitions && stats.top_transitions) {
        const transitions = Object.entries(stats.top_transitions);

        if (transitions.length === 0) {
            elements.routingTransitions.innerHTML = '<p class="text-dim">No routing data yet.</p>';
            return;
        }

        elements.routingTransitions.innerHTML = transitions
            .map(([transition, count]) => `
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; background: var(--bg-secondary); border-radius: 6px; margin-bottom: 8px;">
                    <span style="color: var(--text-secondary); font-family: monospace; font-size: 13px;">
                        ${transition}
                    </span>
                    <span style="color: var(--success); font-weight: 600; font-size: 14px;">
                        ${count}
                    </span>
                </div>
            `)
            .join('');
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Utilities
// ═══════════════════════════════════════════════════════════════════════

/**
 * Set text content safely
 */
function setText(element, value) {
    if (element) {
        element.textContent = value !== undefined && value !== null ? value : '-';
    }
}

/**
 * Format duration in seconds to human readable
 */
function formatDuration(seconds) {
    if (!seconds || seconds === 0) return '0s';

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    const parts = [];
    if (hours > 0) parts.push(`${hours}h`);
    if (minutes > 0) parts.push(`${minutes}m`);
    if (secs > 0 || parts.length === 0) parts.push(`${secs}s`);

    return parts.join(' ');
}

/**
 * Show error message
 */
function showError(message) {
    console.error(message);
    // Could implement a toast notification here
}

// ═══════════════════════════════════════════════════════════════════════
// Event Handlers
// ═══════════════════════════════════════════════════════════════════════

/**
 * Handle time window change
 */
function onTimeWindowChange(event) {
    state.timeWindow = parseInt(event.target.value);
    loadAnalytics();
}

/**
 * Handle refresh button click
 */
function onRefreshClick() {
    loadAnalytics();
}

// ═══════════════════════════════════════════════════════════════════════
// Initialization
// ═══════════════════════════════════════════════════════════════════════

/**
 * Initialize analytics page
 */
async function init() {
    console.log('Initializing Analytics page...');

    // Setup event listeners
    if (elements.timeWindowSelect) {
        elements.timeWindowSelect.addEventListener('change', onTimeWindowChange);
    }

    // Load initial data
    await loadAnalytics();

    // Auto-refresh every 60 seconds
    state.refreshInterval = setInterval(loadAnalytics, 60000);

    console.log('Analytics page ready ✓');
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (state.refreshInterval) {
        clearInterval(state.refreshInterval);
    }
});

// Start when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
