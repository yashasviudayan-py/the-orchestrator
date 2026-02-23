/**
 * The Orchestrator Command Center - Approvals JavaScript
 *
 * Handles:
 * - Loading pending approvals
 * - Approve/reject actions
 * - Real-time WebSocket updates
 * - Approval history
 */

// ═══════════════════════════════════════════════════════════════════════
// State Management
// ═══════════════════════════════════════════════════════════════════════

const state = {
    pendingApprovals: [],
    approvalHistory: [],
    refreshInterval: null,
    ws: null,
};

// ═══════════════════════════════════════════════════════════════════════
// DOM Elements
// ═══════════════════════════════════════════════════════════════════════

const elements = {
    pendingCount: document.getElementById('pending-count'),
    pendingList: document.getElementById('pending-list'),
    historyList: document.getElementById('history-list'),
    emptyPending: document.getElementById('empty-pending'),
    emptyHistory: document.getElementById('empty-history'),
};

// ═══════════════════════════════════════════════════════════════════════
// API Client
// ═══════════════════════════════════════════════════════════════════════

const api = {
    /**
     * Get pending approvals
     */
    async getPendingApprovals() {
        const response = await fetch('/api/approvals/pending');
        if (!response.ok) throw new Error('Failed to fetch pending approvals');
        return await response.json();
    },

    /**
     * Approve a request
     */
    async approve(requestId, note = '') {
        const response = await fetch(`/api/approvals/${requestId}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ note }),
        });
        if (!response.ok) throw new Error('Failed to approve request');
        return await response.json();
    },

    /**
     * Reject a request
     */
    async reject(requestId, note = '') {
        const response = await fetch(`/api/approvals/${requestId}/reject`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ note }),
        });
        if (!response.ok) throw new Error('Failed to reject request');
        return await response.json();
    },

    /**
     * Get approval history
     */
    async getHistory(limit = 20) {
        const response = await fetch(`/api/approvals/history?limit=${limit}`);
        if (!response.ok) throw new Error('Failed to fetch history');
        return await response.json();
    },

    /**
     * Get approval statistics
     */
    async getStats() {
        const response = await fetch('/api/approvals/stats');
        if (!response.ok) throw new Error('Failed to fetch stats');
        return await response.json();
    },
};

// ═══════════════════════════════════════════════════════════════════════
// UI Rendering
// ═══════════════════════════════════════════════════════════════════════

/**
 * Render pending approvals
 */
function renderPendingApprovals(approvals) {
    state.pendingApprovals = approvals;

    // Update count
    elements.pendingCount.textContent = approvals.length;

    if (approvals.length === 0) {
        elements.emptyPending.classList.remove('hidden');
        elements.pendingList.innerHTML = '';
        return;
    }

    elements.emptyPending.classList.add('hidden');

    // Render approval cards
    elements.pendingList.innerHTML = approvals.map(approval => {
        const riskClass = approval.risk_level.toLowerCase();
        const createdTime = new Date(approval.created_at).toLocaleTimeString();
        const timeElapsed = getTimeElapsed(approval.created_at);
        const timeRemaining = getTimeRemaining(approval.created_at, approval.timeout_seconds);

        return `
            <div class="approval-card ${riskClass}-risk" data-request-id="${approval.request_id}">
                <div class="approval-header">
                    <div class="approval-operation">
                        ${getOperationIcon(approval.operation_type)} ${formatOperationType(approval.operation_type)}
                    </div>
                    <span class="risk-badge ${riskClass}">
                        ${approval.risk_level.toUpperCase()}
                    </span>
                </div>

                <div class="approval-description">
                    ${approval.description}
                </div>

                ${renderApprovalDetails(approval)}

                <div class="approval-meta" style="display: flex; gap: 16px; margin-top: 12px; font-size: 13px; color: var(--text-dim);">
                    <div>
                        <span>Task:</span> <span style="color: var(--text-secondary);">${approval.task_id || 'N/A'}</span>
                    </div>
                    <div>
                        <span>Agent:</span> <span style="color: var(--text-secondary);">${approval.agent_name || 'N/A'}</span>
                    </div>
                    <div>
                        <span>Requested:</span> <span style="color: var(--text-secondary);">${createdTime}</span>
                    </div>
                </div>

                <div class="approval-timer" style="margin-top: 12px; font-size: 13px;">
                    <span style="color: var(--text-dim);">⏱️ Timeout:</span>
                    <span class="time-remaining" style="color: var(--warning); font-weight: 600;">
                        ${timeRemaining}
                    </span>
                </div>

                <div class="approval-note" style="margin-top: 12px;">
                    <textarea
                        id="note-${approval.request_id}"
                        placeholder="Optional note (reason for approval/rejection)"
                        style="width: 100%; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 6px; padding: 8px; color: var(--text-primary); font-family: inherit; font-size: 13px; resize: vertical; min-height: 60px;"
                    ></textarea>
                </div>

                <div class="approval-actions">
                    <button onclick="approveRequest('${approval.request_id}')" class="btn btn-success">
                        ✓ Approve
                    </button>
                    <button onclick="rejectRequest('${approval.request_id}')" class="btn btn-danger">
                        ✗ Reject
                    </button>
                </div>
            </div>
        `;
    }).join('');

    // Start timer updates
    updateTimers();
}

/**
 * Render approval details
 */
function renderApprovalDetails(approval) {
    if (!approval.details || Object.keys(approval.details).length === 0) {
        return '';
    }

    let html = '';

    // Render diff block if present
    if (approval.details.diff) {
        const diffLines = approval.details.diff.split('\n').map(line => {
            const escaped = line.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            if (line.startsWith('+++') || line.startsWith('---')) {
                return `<span style="color: var(--text-dim);">${escaped}</span>`;
            } else if (line.startsWith('+')) {
                return `<span style="color: #4ade80;">${escaped}</span>`;
            } else if (line.startsWith('-')) {
                return `<span style="color: #f87171;">${escaped}</span>`;
            } else if (line.startsWith('@@')) {
                return `<span style="color: #60a5fa;">${escaped}</span>`;
            }
            return escaped;
        }).join('\n');

        html += `
            <div class="approval-diff-section">
                <strong>Code Changes:</strong>
                <pre class="diff-block">${diffLines}</pre>
            </div>
        `;
    }

    // Render other details (skip diff key)
    const otherDetails = Object.entries(approval.details)
        .filter(([key]) => key !== 'diff')
        .map(([key, value]) => `<div>• ${key}: ${formatDetailValue(value)}</div>`)
        .join('');

    if (otherDetails) {
        html += `
            <div class="approval-details">
                <strong>Details:</strong>
                ${otherDetails}
            </div>
        `;
    }

    return html;
}

/**
 * Render approval history
 */
function renderHistory(history) {
    state.approvalHistory = history;

    if (history.length === 0) {
        elements.emptyHistory.classList.remove('hidden');
        elements.historyList.innerHTML = '';
        return;
    }

    elements.emptyHistory.classList.add('hidden');

    elements.historyList.innerHTML = history.map((item, index) => {
        const statusIcon = item.status === 'approved' ? '✓' : item.status === 'rejected' ? '✗' : '⏱';
        const statusClass = item.status === 'approved' ? 'success' : item.status === 'rejected' ? 'error' : 'warning';
        const decidedTime = item.decided_at ? new Date(item.decided_at).toLocaleString() : 'N/A';
        const hasDetails = item.details && Object.keys(item.details).length > 0;

        return `
            <div class="card mb-2 history-item ${hasDetails ? 'clickable' : ''}" style="padding: 12px; ${hasDetails ? 'cursor: pointer;' : ''}" ${hasDetails ? `onclick="toggleHistoryDetails(${index})"` : ''}>
                <div style="display: flex; justify-content: space-between; align-items: start;">
                    <div style="flex: 1;">
                        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                            <span class="text-${statusClass}" style="font-size: 18px;">${statusIcon}</span>
                            <strong>${formatOperationType(item.operation_type)}</strong>
                            <span class="risk-badge ${item.risk_level}">${item.risk_level.toUpperCase()}</span>
                            ${hasDetails ? '<span style="color: var(--text-dim); font-size: 11px; margin-left: 4px;">▶ click to expand</span>' : ''}
                        </div>
                        <div style="color: var(--text-secondary); font-size: 13px; margin-bottom: 4px;">
                            ${item.description}
                        </div>
                        ${item.decision_note ? `
                            <div style="color: var(--text-dim); font-size: 12px; font-style: italic;">
                                Note: ${item.decision_note}
                            </div>
                        ` : ''}
                    </div>
                    <div style="text-align: right; color: var(--text-dim); font-size: 12px;">
                        ${decidedTime}
                    </div>
                </div>
                <div id="history-details-${index}" class="history-details hidden">
                    ${hasDetails ? renderHistoryDetails(item.details) : ''}
                </div>
            </div>
        `;
    }).join('');
}

/**
 * Toggle history item details
 */
window.toggleHistoryDetails = function(index) {
    const details = document.getElementById(`history-details-${index}`);
    if (!details) return;
    details.classList.toggle('hidden');

    // Update the expand hint
    const item = details.closest('.history-item');
    const hint = item ? item.querySelector('span[style*="11px"]') : null;
    if (hint) {
        hint.textContent = details.classList.contains('hidden') ? '▶ click to expand' : '▼ click to collapse';
    }
};

/**
 * Render history item details (including diff)
 */
function renderHistoryDetails(details) {
    let html = '';

    if (details.diff) {
        const diffLines = details.diff.split('\n').map(line => {
            const escaped = line.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            if (line.startsWith('+++') || line.startsWith('---')) {
                return `<span style="color: var(--text-dim);">${escaped}</span>`;
            } else if (line.startsWith('+')) {
                return `<span style="color: #4ade80;">${escaped}</span>`;
            } else if (line.startsWith('-')) {
                return `<span style="color: #f87171;">${escaped}</span>`;
            } else if (line.startsWith('@@')) {
                return `<span style="color: #60a5fa;">${escaped}</span>`;
            }
            return escaped;
        }).join('\n');

        html += `
            <div class="approval-diff-section" style="margin-top: 12px;">
                <strong>Code Changes:</strong>
                <pre class="diff-block">${diffLines}</pre>
            </div>
        `;
    }

    const otherDetails = Object.entries(details)
        .filter(([key]) => key !== 'diff')
        .map(([key, value]) => `<div>• ${key}: ${formatDetailValue(value)}</div>`)
        .join('');

    if (otherDetails) {
        html += `
            <div class="approval-details" style="margin-top: 8px;">
                <strong>Details:</strong>
                ${otherDetails}
            </div>
        `;
    }

    return html;
}

// ═══════════════════════════════════════════════════════════════════════
// Actions
// ═══════════════════════════════════════════════════════════════════════

/**
 * Approve a request
 */
window.approveRequest = async function(requestId) {
    const noteEl = document.getElementById(`note-${requestId}`);
    const note = noteEl ? noteEl.value.trim() : '';

    const card = document.querySelector(`[data-request-id="${requestId}"]`);
    if (card) {
        card.style.opacity = '0.5';
        card.style.pointerEvents = 'none';
    }

    try {
        await api.approve(requestId, note);
        console.log('Approved:', requestId);

        // Show success feedback
        showNotification('✓ Approved', 'Request has been approved');

        // Refresh immediately
        await loadPendingApprovals();
        await loadHistory();

    } catch (error) {
        console.error('Failed to approve:', error);
        alert(`Failed to approve: ${error.message}`);

        if (card) {
            card.style.opacity = '1';
            card.style.pointerEvents = 'auto';
        }
    }
};

/**
 * Reject a request
 */
window.rejectRequest = async function(requestId) {
    const noteEl = document.getElementById(`note-${requestId}`);
    const note = noteEl ? noteEl.value.trim() : '';

    if (!note) {
        const confirmed = confirm('No rejection reason provided. Continue anyway?');
        if (!confirmed) return;
    }

    const card = document.querySelector(`[data-request-id="${requestId}"]`);
    if (card) {
        card.style.opacity = '0.5';
        card.style.pointerEvents = 'none';
    }

    try {
        await api.reject(requestId, note);
        console.log('Rejected:', requestId);

        // Show feedback
        showNotification('✗ Rejected', 'Request has been rejected');

        // Refresh immediately
        await loadPendingApprovals();
        await loadHistory();

    } catch (error) {
        console.error('Failed to reject:', error);
        alert(`Failed to reject: ${error.message}`);

        if (card) {
            card.style.opacity = '1';
            card.style.pointerEvents = 'auto';
        }
    }
};

// ═══════════════════════════════════════════════════════════════════════
// Data Loading
// ═══════════════════════════════════════════════════════════════════════

/**
 * Load pending approvals
 */
async function loadPendingApprovals() {
    try {
        const approvals = await api.getPendingApprovals();
        renderPendingApprovals(approvals);
    } catch (error) {
        console.error('Failed to load pending approvals:', error);
    }
}

/**
 * Load approval history
 */
async function loadHistory() {
    try {
        const history = await api.getHistory(20);
        renderHistory(history);
    } catch (error) {
        console.error('Failed to load history:', error);
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Utilities
// ═══════════════════════════════════════════════════════════════════════

/**
 * Get operation type icon
 */
function getOperationIcon(operationType) {
    const icons = {
        'git_push': '📤',
        'git_force_push': '⚠️',
        'code_execution': '⚡',
        'file_write': '📝',
        'file_delete': '🗑️',
        'pr_create': '🔀',
        'api_call': '🌐',
        'agent_call': '🤖',
    };
    return icons[operationType] || '📋';
}

/**
 * Format operation type for display
 */
function formatOperationType(operationType) {
    return operationType
        .split('_')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
}

/**
 * Format detail value
 */
function formatDetailValue(value) {
    if (typeof value === 'object') {
        return JSON.stringify(value);
    }
    return String(value);
}

/**
 * Get time elapsed since creation
 */
function getTimeElapsed(createdAt) {
    const elapsed = Date.now() - new Date(createdAt).getTime();
    const seconds = Math.floor(elapsed / 1000);
    const minutes = Math.floor(seconds / 60);

    if (minutes > 0) {
        return `${minutes}m ${seconds % 60}s ago`;
    }
    return `${seconds}s ago`;
}

/**
 * Get time remaining until timeout
 */
function getTimeRemaining(createdAt, timeoutSeconds) {
    const elapsed = (Date.now() - new Date(createdAt).getTime()) / 1000;
    const remaining = Math.max(0, timeoutSeconds - elapsed);

    const minutes = Math.floor(remaining / 60);
    const seconds = Math.floor(remaining % 60);

    if (remaining <= 0) {
        return 'EXPIRED';
    }

    return `${minutes}:${seconds.toString().padStart(2, '0')} remaining`;
}

/**
 * Update all timers
 */
function updateTimers() {
    const timerElements = document.querySelectorAll('.time-remaining');

    timerElements.forEach((el, index) => {
        if (state.pendingApprovals[index]) {
            const approval = state.pendingApprovals[index];
            const timeRemaining = getTimeRemaining(approval.created_at, approval.timeout_seconds);
            el.textContent = timeRemaining;

            // Color code based on urgency
            const elapsed = (Date.now() - new Date(approval.created_at).getTime()) / 1000;
            const remaining = approval.timeout_seconds - elapsed;

            if (remaining <= 0) {
                el.style.color = 'var(--error)';
            } else if (remaining < 60) {
                el.style.color = 'var(--error)';
            } else if (remaining < 180) {
                el.style.color = 'var(--warning)';
            } else {
                el.style.color = 'var(--text-secondary)';
            }
        }
    });
}

/**
 * Show notification
 */
function showNotification(title, message) {
    console.log(`[Notification] ${title}: ${message}`);

    if ('Notification' in window && Notification.permission === 'granted') {
        new Notification(title, {
            body: message,
            icon: '/static/img/logo.svg',
        });
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Initialization
// ═══════════════════════════════════════════════════════════════════════

/**
 * Initialize approvals page
 */
async function init() {
    console.log('Initializing Approvals page...');

    // Request notification permission
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }

    // Load initial data
    await Promise.all([
        loadPendingApprovals(),
        loadHistory(),
    ]);

    // Auto-refresh every 5 seconds
    state.refreshInterval = setInterval(async () => {
        await loadPendingApprovals();
    }, 5000);

    // Update timers every second
    setInterval(updateTimers, 1000);

    console.log('Approvals page ready ✓');
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
