/**
 * The Orchestrator Command Center - Dashboard JavaScript
 *
 * Handles:
 * - Task submission
 * - SSE streaming for real-time progress
 * - Agent status monitoring
 * - UI updates
 */

// ═══════════════════════════════════════════════════════════════════════
// State Management
// ═══════════════════════════════════════════════════════════════════════

const state = {
    currentTaskId: null,
    eventSource: null,
    agents: {},
};

// ═══════════════════════════════════════════════════════════════════════
// DOM Elements
// ═══════════════════════════════════════════════════════════════════════

const elements = {
    taskInput: document.getElementById('task-input'),
    submitBtn: document.getElementById('submit-btn'),
    taskProgress: document.getElementById('task-progress'),
    taskStatus: document.getElementById('task-status'),
    progressBar: document.getElementById('progress-bar'),
    currentAgent: document.getElementById('current-agent'),
    iteration: document.getElementById('iteration'),
    eventsTimeline: document.getElementById('events-timeline'),
    agentGrid: document.getElementById('agent-grid'),
};

// ═══════════════════════════════════════════════════════════════════════
// API Client
// ═══════════════════════════════════════════════════════════════════════

const api = {
    /**
     * Start a new orchestration task
     */
    async startTask(objective) {
        const response = await fetch('/api/tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                objective,
                max_iterations: 10,
                routing_strategy: 'adaptive',
                enable_hitl: true,
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to start task');
        }

        return await response.json();
    },

    /**
     * Get task details
     */
    async getTask(taskId) {
        const response = await fetch(`/api/tasks/${taskId}`);

        if (!response.ok) {
            throw new Error('Failed to get task');
        }

        return await response.json();
    },

    /**
     * Check agent health
     */
    async checkHealth() {
        const response = await fetch('/api/health');
        return await response.json();
    },
};

// ═══════════════════════════════════════════════════════════════════════
// SSE Event Handling
// ═══════════════════════════════════════════════════════════════════════

/**
 * Connect to SSE stream for task progress
 */
function connectToTaskStream(taskId, streamUrl) {
    // Close existing connection
    if (state.eventSource) {
        state.eventSource.close();
    }

    const eventSource = new EventSource(streamUrl);
    state.eventSource = eventSource;
    state.currentTaskId = taskId;

    // Task start
    eventSource.addEventListener('task_start', (e) => {
        const data = JSON.parse(e.data);
        console.log('Task started:', data);
        addEvent('Task started', 'system');
    });

    // Agent start
    eventSource.addEventListener('agent_start', (e) => {
        const data = JSON.parse(e.data);
        console.log('Agent starting:', data);

        updateCurrentAgent(data.agent);
        updateIteration(data.iteration);
        addEvent(`Starting ${data.agent} agent`, data.agent);
    });

    // Agent progress
    eventSource.addEventListener('agent_progress', (e) => {
        const data = JSON.parse(e.data);
        console.log('Agent progress:', data);

        if (data.progress) {
            updateProgress(data.progress);
        }

        addEvent(data.message || 'Progress update', state.currentAgent);
    });

    // Agent complete
    eventSource.addEventListener('agent_complete', (e) => {
        const data = JSON.parse(e.data);
        console.log('Agent completed:', data);

        addEvent(`${data.agent} agent completed (${data.duration_ms}ms)`, data.agent, 'success');
    });

    // Approval required
    eventSource.addEventListener('approval_required', (e) => {
        const data = JSON.parse(e.data);
        console.log('Approval required:', data);

        addEvent('⚠️ Approval required - check Approvals page', 'system', 'warning');

        // Could show toast notification here
        showNotification('Approval Required', 'An operation needs your approval');
    });

    // Approval decided
    eventSource.addEventListener('approval_decided', (e) => {
        const data = JSON.parse(e.data);
        console.log('Approval decided:', data);

        const status = data.approved ? 'approved' : 'rejected';
        addEvent(`Approval ${status}`, 'system', status === 'approved' ? 'success' : 'error');
    });

    // Iteration
    eventSource.addEventListener('iteration', (e) => {
        const data = JSON.parse(e.data);
        console.log('Iteration:', data);

        updateIteration(data.iteration, data.max);
        addEvent(`Iteration ${data.iteration}/${data.max}`, 'system');
    });

    // Routing decision
    eventSource.addEventListener('routing_decision', (e) => {
        const data = JSON.parse(e.data);
        console.log('Routing decision:', data);

        addEvent(`Routing to: ${data.next_agent}`, 'supervisor');
    });

    // Complete
    eventSource.addEventListener('complete', (e) => {
        const data = JSON.parse(e.data);
        console.log('Task completed:', data);

        updateTaskStatus('completed');
        updateProgress(100);
        addEvent('✓ Task completed successfully', 'system', 'success');

        // Show final output if available
        if (data.final_output) {
            showFinalOutput(data.final_output);
        }

        eventSource.close();
    });

    // Error
    eventSource.addEventListener('error', (e) => {
        if (e.data) {
            const data = JSON.parse(e.data);
            console.error('Task error:', data);

            updateTaskStatus('failed');
            addEvent(`✗ Error: ${data.error}`, 'system', 'error');
        }

        eventSource.close();
    });

    // Keepalive
    eventSource.addEventListener('keepalive', () => {
        console.log('Keepalive ping');
    });

    // Connection errors
    eventSource.onerror = (error) => {
        console.error('SSE connection error:', error);

        // Retry logic could go here
        if (eventSource.readyState === EventSource.CLOSED) {
            addEvent('Connection closed', 'system', 'error');
        }
    };
}

// ═══════════════════════════════════════════════════════════════════════
// UI Updates
// ═══════════════════════════════════════════════════════════════════════

/**
 * Update task status display
 */
function updateTaskStatus(status) {
    const statusEl = elements.taskStatus;
    statusEl.textContent = status.charAt(0).toUpperCase() + status.slice(1);
    statusEl.className = `task-status ${status}`;
}

/**
 * Update progress bar
 */
function updateProgress(percent) {
    elements.progressBar.style.width = `${percent}%`;
}

/**
 * Update current agent display
 */
function updateCurrentAgent(agent) {
    elements.currentAgent.textContent = agent || 'None';
}

/**
 * Update iteration display
 */
function updateIteration(current, max = 10) {
    elements.iteration.textContent = `${current} / ${max}`;
}

/**
 * Add event to timeline
 */
function addEvent(message, agent = 'system', type = 'info') {
    const time = new Date().toLocaleTimeString();

    const eventEl = document.createElement('div');
    eventEl.className = 'event-item';

    eventEl.innerHTML = `
        <div class="event-time">${time}</div>
        <div class="event-content">
            <span class="event-agent">[${agent}]</span>
            <span class="text-${type === 'success' ? 'success' : type === 'error' ? 'error' : 'secondary'}">${message}</span>
        </div>
    `;

    elements.eventsTimeline.appendChild(eventEl);

    // Auto-scroll to bottom
    eventEl.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

/**
 * Show final output
 */
function showFinalOutput(output) {
    const outputEl = document.createElement('div');
    outputEl.className = 'card mt-3';
    outputEl.innerHTML = `
        <div class="card-title">Final Output</div>
        <div class="card-content" style="white-space: pre-wrap; color: var(--text-primary);">${output}</div>
    `;

    elements.taskProgress.appendChild(outputEl);
}

/**
 * Show notification (basic implementation)
 */
function showNotification(title, message) {
    // Could use browser Notification API or toast library
    console.log(`[Notification] ${title}: ${message}`);

    // Basic browser notification if permission granted
    if ('Notification' in window && Notification.permission === 'granted') {
        new Notification(title, {
            body: message,
            icon: '/static/icon.png',
        });
    }
}

/**
 * Update agent status indicators
 */
function updateAgentStatuses(agents) {
    const agentNames = ['research', 'context', 'pr', 'ollama', 'redis'];

    agentNames.forEach(name => {
        const indicator = document.querySelector(`[data-agent="${name}"] .agent-indicator`);
        if (indicator && agents[name]) {
            indicator.className = `agent-indicator ${agents[name]}`;
        }
    });
}

// ═══════════════════════════════════════════════════════════════════════
// Event Listeners
// ═══════════════════════════════════════════════════════════════════════

/**
 * Handle task submission
 */
elements.submitBtn.addEventListener('click', async () => {
    const objective = elements.taskInput.value.trim();

    if (!objective) {
        alert('Please enter a task objective');
        return;
    }

    try {
        // Disable input
        elements.submitBtn.disabled = true;
        elements.submitBtn.innerHTML = '<span class="spinner"></span> Starting...';

        // Start task
        const response = await api.startTask(objective);

        console.log('Task created:', response);

        // Show progress section
        elements.taskProgress.classList.remove('hidden');

        // Clear previous events
        elements.eventsTimeline.innerHTML = '';

        // Reset UI
        updateTaskStatus('running');
        updateProgress(0);
        updateCurrentAgent(null);
        updateIteration(0);

        // Connect to stream
        connectToTaskStream(response.task_id, response.stream_url);

    } catch (error) {
        console.error('Failed to start task:', error);
        alert(`Failed to start task: ${error.message}`);

        elements.submitBtn.disabled = false;
        elements.submitBtn.textContent = 'Start Task';
    }
});

/**
 * Allow Enter to submit (with Shift+Enter for newline)
 */
elements.taskInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        elements.submitBtn.click();
    }
});

// ═══════════════════════════════════════════════════════════════════════
// Initialization
// ═══════════════════════════════════════════════════════════════════════

/**
 * Initialize dashboard
 */
async function init() {
    console.log('Initializing Command Center...');

    // Request notification permission
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }

    // Load agent health
    try {
        const health = await api.checkHealth();
        updateAgentStatuses(health.agents);
        console.log('Agent health:', health);
    } catch (error) {
        console.error('Failed to check health:', error);
    }

    // Periodic health check every 30 seconds
    setInterval(async () => {
        try {
            const health = await api.checkHealth();
            updateAgentStatuses(health.agents);
        } catch (error) {
            console.error('Health check failed:', error);
        }
    }, 30000);

    console.log('Command Center ready ✓');
}

// Start when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
