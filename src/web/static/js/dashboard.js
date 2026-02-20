/**
 * The Orchestrator Command Center - Dashboard JavaScript
 *
 * Handles:
 * - Task submission
 * - SSE streaming for real-time progress
 * - Chat-style agent activity feed
 * - UI updates
 */

// ═══════════════════════════════════════════════════════════════════════
// Agent Configuration
// ═══════════════════════════════════════════════════════════════════════

const AGENT_CONFIG = {
    research:   { icon: '🔬', label: 'Research Agent' },
    context:    { icon: '🧠', label: 'Context Core' },
    pr:         { icon: '⚙️',  label: 'PR-Agent' },
    supervisor: { icon: '🎯', label: 'Supervisor' },
    system:     { icon: '🖥️', label: 'System' },
};

// ═══════════════════════════════════════════════════════════════════════
// State Management
// ═══════════════════════════════════════════════════════════════════════

const state = {
    currentTaskId: null,
    eventSource: null,
    taskCount: 0,  // number of tasks started this session
};

// ═══════════════════════════════════════════════════════════════════════
// DOM Elements
// ═══════════════════════════════════════════════════════════════════════

const elements = {
    taskInput: document.getElementById('task-input'),
    submitBtn: document.getElementById('submit-btn'),
    stopBtn: document.getElementById('stop-btn'),
    taskStatusBar: document.getElementById('task-status-bar'),
    taskStatus: document.getElementById('task-status'),
    progressBar: document.getElementById('progress-bar'),
    currentAgent: document.getElementById('current-agent'),
    iteration: document.getElementById('iteration'),
    chatMessages: document.getElementById('chat-messages'),
    typingIndicator: document.getElementById('typing-indicator'),
};

// ═══════════════════════════════════════════════════════════════════════
// API Client
// ═══════════════════════════════════════════════════════════════════════

const api = {
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

    async cancelTask(taskId) {
        const response = await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });

        if (!response.ok) {
            throw new Error('Failed to cancel task');
        }

        return await response.json();
    },
};

// ═══════════════════════════════════════════════════════════════════════
// Chat UI
// ═══════════════════════════════════════════════════════════════════════

/**
 * Remove the "empty" placeholder if present
 */
function clearEmptyPlaceholder() {
    const empty = elements.chatMessages.querySelector('.chat-empty');
    if (empty) empty.remove();
}

/**
 * Add a task separator when a new task starts
 */
function addTaskSeparator(taskNumber) {
    clearEmptyPlaceholder();
    const sep = document.createElement('div');
    sep.className = 'chat-separator';
    sep.textContent = `— Task #${taskNumber} —`;
    elements.chatMessages.appendChild(sep);
    sep.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

/**
 * Add a chat bubble message
 */
function addChatMessage(message, agent = 'system', type = 'info') {
    clearEmptyPlaceholder();

    const cfg = AGENT_CONFIG[agent] || { icon: '●', label: agent };
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    const bubble = document.createElement('div');
    bubble.className = `chat-bubble chat-bubble-${agent}`;

    const colorClass = type === 'success' ? 'style="color: var(--success);"'
        : type === 'error' ? 'style="color: var(--error);"'
        : type === 'warning' ? 'style="color: var(--warning);"'
        : '';

    bubble.innerHTML = `
        <div class="chat-bubble-header">
            <span>${cfg.icon}</span>
            <span class="chat-agent-name">${cfg.label}</span>
            <span class="chat-time">${time}</span>
        </div>
        <div class="chat-bubble-content" ${colorClass}>${message}</div>
    `;

    elements.chatMessages.appendChild(bubble);
    bubble.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

/**
 * Show/hide typing indicator
 */
function setTypingIndicator(visible) {
    if (elements.typingIndicator) {
        if (visible) {
            elements.typingIndicator.classList.remove('hidden');
        } else {
            elements.typingIndicator.classList.add('hidden');
        }
    }
}

/**
 * Show final output as a chat bubble
 */
function showFinalOutput(output) {
    addChatMessage(`<strong>Final Output:</strong><br><pre style="margin-top:6px;white-space:pre-wrap;font-size:13px;">${output}</pre>`, 'system', 'success');
}

// ═══════════════════════════════════════════════════════════════════════
// Status Bar Updates
// ═══════════════════════════════════════════════════════════════════════

function updateTaskStatus(status) {
    if (!elements.taskStatus) return;
    elements.taskStatus.textContent = status.charAt(0).toUpperCase() + status.slice(1);
    elements.taskStatus.className = `task-status ${status}`;
}

function updateProgress(percent) {
    if (elements.progressBar) {
        elements.progressBar.style.width = `${percent}%`;
    }
}

function updateCurrentAgent(agent) {
    if (elements.currentAgent) {
        elements.currentAgent.textContent = agent || '—';
    }
}

function updateIteration(current, max = 10) {
    if (elements.iteration) {
        elements.iteration.textContent = `${current} / ${max}`;
    }
}

// ═══════════════════════════════════════════════════════════════════════
// SSE Event Handling
// ═══════════════════════════════════════════════════════════════════════

function connectToTaskStream(taskId, streamUrl) {
    if (state.eventSource) {
        state.eventSource.close();
    }

    const eventSource = new EventSource(streamUrl);
    state.eventSource = eventSource;
    state.currentTaskId = taskId;

    eventSource.addEventListener('task_start', (e) => {
        const data = JSON.parse(e.data);
        console.log('Task started:', data);
        addChatMessage('Task started', 'system');
        setTypingIndicator(true);

        elements.submitBtn.innerHTML = '<span class="spinner"></span> Working...';
        elements.stopBtn.classList.remove('hidden');
    });

    eventSource.addEventListener('agent_start', (e) => {
        const data = JSON.parse(e.data);
        console.log('Agent starting:', data);

        updateCurrentAgent(data.agent);
        updateIteration(data.iteration);
        setTypingIndicator(true);
        addChatMessage(`Starting…`, data.agent || 'system');
    });

    eventSource.addEventListener('agent_progress', (e) => {
        const data = JSON.parse(e.data);
        console.log('Agent progress:', data);

        if (data.current_agent) {
            updateCurrentAgent(data.current_agent);
        }

        if (typeof data.iteration === 'number') {
            updateIteration(data.iteration, 10);
        }

        if (data.progress) {
            updateProgress(data.progress);
        }

        if (data.message) {
            addChatMessage(data.message, data.current_agent || 'system');
        }
    });

    eventSource.addEventListener('agent_complete', (e) => {
        const data = JSON.parse(e.data);
        console.log('Agent completed:', data);

        setTypingIndicator(false);
        addChatMessage(`Completed (${data.duration_ms}ms)`, data.agent || 'system', 'success');
    });

    eventSource.addEventListener('approval_required', (e) => {
        const data = JSON.parse(e.data);
        console.log('Approval required:', data);

        setTypingIndicator(false);
        addChatMessage('⚠️ Approval required — check the <a href="/approvals" style="color:var(--warning);">Approvals page</a>', 'system', 'warning');

        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification('Approval Required', { body: 'An operation needs your approval' });
        }
    });

    eventSource.addEventListener('approval_decided', (e) => {
        const data = JSON.parse(e.data);
        console.log('Approval decided:', data);

        const status = data.approved ? 'approved' : 'rejected';
        addChatMessage(`Approval ${status}`, 'system', status === 'approved' ? 'success' : 'error');
    });

    eventSource.addEventListener('iteration', (e) => {
        const data = JSON.parse(e.data);
        console.log('Iteration:', data);

        updateIteration(data.iteration, data.max);
        addChatMessage(`Iteration ${data.iteration}/${data.max}`, 'supervisor');
    });

    eventSource.addEventListener('routing_decision', (e) => {
        const data = JSON.parse(e.data);
        console.log('Routing decision:', data);

        addChatMessage(`Routing to: ${data.next_agent}`, 'supervisor');
    });

    eventSource.addEventListener('complete', (e) => {
        const data = JSON.parse(e.data);
        console.log('Task completed:', data);

        setTypingIndicator(false);
        updateTaskStatus('completed');
        updateProgress(100);
        addChatMessage('✓ Task completed successfully', 'system', 'success');

        if (data.final_output) {
            showFinalOutput(data.final_output);
        }

        elements.submitBtn.disabled = false;
        elements.submitBtn.textContent = 'Start Task';
        elements.stopBtn.classList.add('hidden');

        eventSource.close();
        state.eventSource = null;
    });

    eventSource.addEventListener('error', (e) => {
        if (e.data) {
            const data = JSON.parse(e.data);
            console.error('Task error:', data);

            setTypingIndicator(false);
            updateTaskStatus('failed');
            addChatMessage(`✗ Error: ${data.error}`, 'system', 'error');
        }

        elements.submitBtn.disabled = false;
        elements.submitBtn.textContent = 'Start Task';
        elements.stopBtn.classList.add('hidden');

        eventSource.close();
        state.eventSource = null;
    });

    eventSource.addEventListener('keepalive', () => {
        console.log('Keepalive ping');
    });

    eventSource.onerror = (error) => {
        console.error('SSE connection error:', error);

        if (eventSource.readyState === EventSource.CLOSED) {
            setTypingIndicator(false);
            addChatMessage('Connection closed', 'system', 'error');

            elements.submitBtn.disabled = false;
            elements.submitBtn.textContent = 'Start Task';
            elements.stopBtn.classList.add('hidden');
        }
    };
}

// ═══════════════════════════════════════════════════════════════════════
// Event Listeners
// ═══════════════════════════════════════════════════════════════════════

elements.submitBtn.addEventListener('click', async () => {
    const objective = elements.taskInput.value.trim();

    if (!objective) {
        alert('Please enter a task objective');
        return;
    }

    try {
        elements.submitBtn.disabled = true;
        elements.submitBtn.innerHTML = '<span class="spinner"></span> Starting...';

        const response = await api.startTask(objective);
        console.log('Task created:', response);

        // Show status bar
        elements.taskStatusBar.classList.remove('hidden');
        updateTaskStatus('running');
        updateProgress(0);
        updateCurrentAgent(null);
        updateIteration(0);

        // Add separator in chat for new task
        state.taskCount += 1;
        addTaskSeparator(state.taskCount);

        connectToTaskStream(response.task_id, response.stream_url);

    } catch (error) {
        console.error('Failed to start task:', error);
        alert(`Failed to start task: ${error.message}`);

        elements.submitBtn.disabled = false;
        elements.submitBtn.textContent = 'Start Task';
    }
});

elements.stopBtn.addEventListener('click', async () => {
    if (!state.currentTaskId) return;

    const confirmed = confirm('Are you sure you want to stop this task?');
    if (!confirmed) return;

    try {
        await api.cancelTask(state.currentTaskId);

        setTypingIndicator(false);
        addChatMessage('Task cancelled by user', 'system', 'warning');

        if (state.eventSource) {
            state.eventSource.close();
            state.eventSource = null;
        }

        updateTaskStatus('cancelled');
        elements.submitBtn.disabled = false;
        elements.submitBtn.textContent = 'Start Task';
        elements.stopBtn.classList.add('hidden');

    } catch (error) {
        console.error('Failed to cancel task:', error);
        alert(`Failed to cancel task: ${error.message}`);
    }
});

elements.taskInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        elements.submitBtn.click();
    }
});

// ═══════════════════════════════════════════════════════════════════════
// Initialization
// ═══════════════════════════════════════════════════════════════════════

function init() {
    console.log('Initializing Command Center...');

    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }

    console.log('Command Center ready ✓');
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
