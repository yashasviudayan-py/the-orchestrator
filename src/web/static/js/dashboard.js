/**
 * The Orchestrator — ChatGPT-style Dashboard
 *
 * - Sidebar: session history from /api/tasks
 * - User messages: right-aligned bubbles
 * - Agent activity: left-aligned bubbles with icons
 * - Final output: rendered as markdown, white text (no green)
 * - Input: fixed at bottom
 */

// ═══════════════════════════════════════════════════════════════════════
// Agent Config
// ═══════════════════════════════════════════════════════════════════════

const AGENT_CONFIG = {
    research:   { icon: '🔬', label: 'Research Agent', cls: 'chat-bubble-research' },
    context:    { icon: '🧠', label: 'Context Core',   cls: 'chat-bubble-context' },
    pr:         { icon: '⚙️',  label: 'PR-Agent',       cls: 'chat-bubble-pr' },
    supervisor: { icon: '🎯', label: 'Supervisor',     cls: 'chat-bubble-supervisor' },
    system:     { icon: '🖥️', label: 'System',         cls: 'chat-bubble-system' },
    user:       { icon: '👤', label: 'You',            cls: 'chat-bubble-user' },
};

// ═══════════════════════════════════════════════════════════════════════
// State
// ═══════════════════════════════════════════════════════════════════════

const state = {
    currentTaskId: null,
    eventSource: null,
    activeSessionId: null,   // task_id of most recent task
    isViewingHistory: false, // true when user clicked a past session from sidebar
};

// ═══════════════════════════════════════════════════════════════════════
// DOM
// ═══════════════════════════════════════════════════════════════════════

const el = {
    taskInput:    document.getElementById('task-input'),
    repoPathInput: document.getElementById('repo-path-input'),
    submitBtn:    document.getElementById('submit-btn'),
    stopBtn:      document.getElementById('stop-btn'),
    chatMessages: document.getElementById('chat-messages'),
    chatEmpty:    document.getElementById('chat-empty'),
    sessionsList: document.getElementById('sessions-list'),
    sessionTitle: document.getElementById('session-title'),
    statusPills:  document.getElementById('status-pills'),
    headerStatus: document.getElementById('header-status'),
    headerAgent:  document.getElementById('header-agent'),
    headerIter:   document.getElementById('header-iter'),
    headerTyping: document.getElementById('header-typing'),
    newChatBtn:       document.getElementById('new-chat-btn'),
    chatSidebar:      document.getElementById('chat-sidebar'),
    sidebarToggleBtn: document.getElementById('sidebar-toggle-btn'),
};

// ═══════════════════════════════════════════════════════════════════════
// API
// ═══════════════════════════════════════════════════════════════════════

const api = {
    /**
     * Smart chat: conversational → direct Ollama stream (no task),
     * agent tasks → orchestration pipeline task.
     * Returns {type:"chat"|"task", stream_url, task_id?}
     */
    async chat(message, repoPath) {
        const payload = { message };
        if (repoPath) payload.repo_path = repoPath;
        const r = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!r.ok) { const e = await r.json(); throw new Error(e.detail || 'Failed'); }
        return r.json();
    },

    async startTask(objective) {
        const r = await fetch('/api/tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ objective, max_iterations: 10, routing_strategy: 'adaptive', enable_hitl: true }),
        });
        if (!r.ok) { const e = await r.json(); throw new Error(e.detail || 'Failed'); }
        return r.json();
    },

    async getTask(id) {
        const r = await fetch(`/api/tasks/${id}`);
        if (!r.ok) throw new Error('Not found');
        return r.json();
    },

    async cancelTask(id) {
        const r = await fetch(`/api/tasks/${id}`, { method: 'DELETE' });
        if (!r.ok) throw new Error('Failed to cancel');
        return r.json();
    },

    async listTasks(limit = 30) {
        const r = await fetch(`/api/tasks?limit=${limit}`);
        if (!r.ok) return { tasks: [] };
        return r.json();
    },
};

// ═══════════════════════════════════════════════════════════════════════
// Markdown renderer (minimal)
// ═══════════════════════════════════════════════════════════════════════

function renderMarkdown(text) {
    if (!text) return '';
    return text
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^# (.+)$/gm, '<h1>$1</h1>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/`([^`]+)`/g, '<code style="background:var(--bg-card);padding:1px 5px;border-radius:4px;font-size:13px;">$1</code>')
        .replace(/^- (.+)$/gm, '<li>$1</li>')
        .replace(/(<li>.*<\/li>\n?)+/g, m => `<ul style="padding-left:18px;margin:6px 0;">${m}</ul>`)
        .replace(/\n{2,}/g, '<br><br>')
        .replace(/\n/g, '<br>');
}

// ═══════════════════════════════════════════════════════════════════════
// Chat rendering helpers
// ═══════════════════════════════════════════════════════════════════════

function hideEmpty() {
    if (el.chatEmpty) { el.chatEmpty.style.display = 'none'; }
}

function addUserBubble(text) {
    hideEmpty();
    const div = document.createElement('div');
    div.className = 'chat-bubble chat-bubble-user';
    div.innerHTML = `<div class="chat-bubble-content">${escapeHtml(text)}</div>`;
    el.chatMessages.appendChild(div);
    div.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function addChatMessage(message, agent = 'system', type = '') {
    hideEmpty();
    if (agent === 'user') { addUserBubble(message); return; }

    const cfg = AGENT_CONFIG[agent] || { icon: '●', label: agent, cls: '' };
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    const color = type === 'error' ? 'color:var(--error);'
        : type === 'warning'       ? 'color:var(--warning);'
        : '';                       // no green — 'success' treated as neutral

    const div = document.createElement('div');
    div.className = `chat-bubble ${cfg.cls}`;
    div.innerHTML = `
        <div class="chat-bubble-header">
            <span>${cfg.icon}</span>
            <span class="chat-agent-name">${cfg.label}</span>
            <span class="chat-time">${time}</span>
        </div>
        <div class="chat-bubble-content" style="${color}">${message}</div>`;
    el.chatMessages.appendChild(div);
    div.scrollIntoView({ behavior: 'smooth', block: 'end' });
    return div;
}

function addOutputBlock(text) {
    hideEmpty();
    const div = document.createElement('div');
    div.className = 'chat-output';
    div.innerHTML = renderMarkdown(text);
    el.chatMessages.appendChild(div);
    div.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function escapeHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function setTyping(on) {
    if (el.headerTyping) el.headerTyping.classList.toggle('hidden', !on);
}

// ═══════════════════════════════════════════════════════════════════════
// Status bar (header pills)
// ═══════════════════════════════════════════════════════════════════════

function showStatusBar() { if (el.statusPills) el.statusPills.style.display = 'flex'; }
function hideStatusBar() { if (el.statusPills) el.statusPills.style.display = 'none'; }

function setHeaderStatus(status) {
    if (!el.headerStatus) return;
    el.headerStatus.textContent = status.charAt(0).toUpperCase() + status.slice(1);
    el.headerStatus.className = `task-status ${status}`;
}

function setHeaderAgent(agent) { if (el.headerAgent) el.headerAgent.textContent = agent || '—'; }
function setHeaderIter(cur, max = 10) { if (el.headerIter) el.headerIter.textContent = `${cur}/${max}`; }

// ═══════════════════════════════════════════════════════════════════════
// Session sidebar
// ═══════════════════════════════════════════════════════════════════════

function renderSessions(tasks) {
    if (!tasks || tasks.length === 0) {
        el.sessionsList.innerHTML = '<div class="sessions-empty">No sessions yet.<br>Start a task to begin.</div>';
        return;
    }

    el.sessionsList.innerHTML = tasks.map(t => `
        <div class="session-item ${t.task_id === state.activeSessionId ? 'active' : ''}"
             data-id="${t.task_id}" onclick="loadSession('${t.task_id}')">
            <div class="session-title">${escapeHtml(t.objective)}</div>
            <div class="session-meta">
                <span class="session-badge ${t.status}">${t.status}</span>
                <span>${t.iteration ?? 0}/${t.max_iterations ?? 10} iter</span>
            </div>
        </div>`).join('');
}

async function loadSessions() {
    try {
        const data = await api.listTasks(40);
        renderSessions(data.tasks || []);
    } catch (e) {
        console.error('Failed to load sessions:', e);
    }
}

async function loadSession(taskId) {
    if (state.eventSource) return; // don't switch while a task is running

    state.activeSessionId = taskId;
    state.isViewingHistory = true;  // next submit will clear this historical view

    // Update sidebar active state
    document.querySelectorAll('.session-item').forEach(s => {
        s.classList.toggle('active', s.dataset.id === taskId);
    });

    try {
        const task = await api.getTask(taskId);

        // Clear chat and render the historical session
        el.chatMessages.innerHTML = '';
        if (el.chatEmpty) el.chatEmpty.style.display = 'none';

        // Show the original objective as user bubble
        addUserBubble(task.objective);

        // Show agent messages
        if (task.messages && task.messages.length > 0) {
            task.messages.forEach(msg => {
                const agent = msg.agent_name || 'system';
                const content = msg.content || {};
                const text = content.message || content.summary || content.result || content.type || '';
                if (text) addChatMessage(escapeHtml(String(text)), agent);
            });
        }

        // Show final output (white, markdown-rendered)
        if (task.final_output) {
            addOutputBlock(task.final_output);
        } else if (task.status === 'completed') {
            addChatMessage('Task completed.', 'system');
        }

        // Show errors
        if (task.errors && task.errors.length > 0) {
            task.errors.forEach(e => addChatMessage(`Error: ${escapeHtml(e)}`, 'system', 'error'));
        }

        // Update session title
        if (el.sessionTitle) {
            el.sessionTitle.textContent = task.objective.length > 60
                ? task.objective.slice(0, 60) + '…'
                : task.objective;
        }

    } catch (e) {
        addChatMessage('Failed to load session.', 'system', 'error');
    }
}

// ═══════════════════════════════════════════════════════════════════════
// SSE streaming
// ═══════════════════════════════════════════════════════════════════════

function connectStream(taskId, streamUrl) {
    if (state.eventSource) state.eventSource.close();

    const es = new EventSource(streamUrl);
    state.eventSource = es;
    state.currentTaskId = taskId;

    es.addEventListener('task_start', () => {
        setTyping(true);
        el.submitBtn.innerHTML = '<span class="spinner"></span>';
        el.submitBtn.disabled = true;
        el.stopBtn.classList.remove('hidden');
    });

    es.addEventListener('agent_start', e => {
        const d = JSON.parse(e.data);
        setTyping(true);
        setHeaderAgent(d.agent);
        setHeaderIter(d.iteration);
        addChatMessage('Starting…', d.agent || 'system');
    });

    es.addEventListener('agent_progress', e => {
        const d = JSON.parse(e.data);
        if (d.current_agent) setHeaderAgent(d.current_agent);
        if (typeof d.iteration === 'number') setHeaderIter(d.iteration);
        if (d.message) addChatMessage(escapeHtml(d.message), d.current_agent || 'system');
    });

    es.addEventListener('agent_complete', e => {
        const d = JSON.parse(e.data);
        setTyping(false);
        addChatMessage(`Done (${d.duration_ms}ms)`, d.agent || 'system');
    });

    es.addEventListener('routing_decision', e => {
        const d = JSON.parse(e.data);
        addChatMessage(`Routing → ${d.next_agent}`, 'supervisor');
    });

    es.addEventListener('iteration', e => {
        const d = JSON.parse(e.data);
        setHeaderIter(d.iteration, d.max);
        addChatMessage(`Iteration ${d.iteration}/${d.max}`, 'supervisor');
    });

    es.addEventListener('approval_required', () => {
        setTyping(false);
        addChatMessage('⚠️ Approval required — check <a href="/approvals" style="color:var(--warning);">Approvals</a>', 'system', 'warning');
        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification('Approval Required', { body: 'An operation needs your approval' });
        }
    });

    es.addEventListener('approval_decided', e => {
        const d = JSON.parse(e.data);
        addChatMessage(`Approval ${d.approved ? 'approved ✓' : 'rejected ✗'}`, 'system', d.approved ? '' : 'error');
    });

    es.addEventListener('complete', e => {
        const d = JSON.parse(e.data);
        setTyping(false);
        setHeaderStatus('completed');

        // Render final output as white markdown block, not green
        if (d.final_output) {
            addOutputBlock(d.final_output);
        } else {
            addChatMessage('✓ Task completed', 'system');
        }

        resetInput();
        es.close();
        state.eventSource = null;
        loadSessions(); // refresh sidebar
    });

    es.addEventListener('error', e => {
        if (e.data) {
            const d = JSON.parse(e.data);
            setTyping(false);
            setHeaderStatus('failed');
            addChatMessage(`✗ ${escapeHtml(d.error || 'Unknown error')}`, 'system', 'error');
        }
        resetInput();
        es.close();
        state.eventSource = null;
        loadSessions();
    });

    es.onerror = () => {
        if (es.readyState === EventSource.CLOSED) {
            setTyping(false);
            addChatMessage('Connection lost', 'system', 'error');
            resetInput();
            state.eventSource = null;
        }
    };

    es.addEventListener('keepalive', () => {});
}

function resetInput() {
    el.submitBtn.innerHTML = '↑';
    el.submitBtn.disabled = false;
    el.stopBtn.classList.add('hidden');
}

// ═══════════════════════════════════════════════════════════════════════
// Direct Ollama chat stream (conversational, no task created)
// ═══════════════════════════════════════════════════════════════════════

function connectChatStream(streamUrl) {
    if (state.eventSource) state.eventSource.close();

    setTyping(true);
    hideStatusBar();

    // Create a streaming output div that builds up token by token
    hideEmpty();
    const div = document.createElement('div');
    div.className = 'chat-output chat-output-streaming';
    el.chatMessages.appendChild(div);
    div.scrollIntoView({ behavior: 'smooth', block: 'end' });

    let buffer = '';

    const es = new EventSource(streamUrl);
    state.eventSource = es;

    es.addEventListener('chat_token', e => {
        const d = JSON.parse(e.data);
        buffer += d.token;
        div.innerHTML = renderMarkdown(buffer);
        div.scrollIntoView({ behavior: 'smooth', block: 'end' });
    });

    es.addEventListener('chat_complete', () => {
        setTyping(false);
        div.classList.remove('chat-output-streaming');
        resetInput();
        es.close();
        state.eventSource = null;
    });

    es.addEventListener('error', e => {
        setTyping(false);
        if (e.data) {
            try {
                const d = JSON.parse(e.data);
                addChatMessage(`Error: ${escapeHtml(d.error || 'Unknown error')}`, 'system', 'error');
            } catch {}
        }
        resetInput();
        es.close();
        state.eventSource = null;
    });

    es.onerror = () => {
        if (es.readyState === EventSource.CLOSED) {
            setTyping(false);
            resetInput();
            state.eventSource = null;
        }
    };
}

// ═══════════════════════════════════════════════════════════════════════
// Event listeners
// ═══════════════════════════════════════════════════════════════════════

el.submitBtn.addEventListener('click', async () => {
    const objective = el.taskInput.value.trim();
    if (!objective) return;

    try {
        el.submitBtn.innerHTML = '<span class="spinner"></span>';
        el.submitBtn.disabled = true;

        // Use smart chat router — handles both conversational and agent tasks
        const repoPath = el.repoPathInput ? el.repoPathInput.value.trim() : '';
        const response = await api.chat(objective, repoPath);

        // Only clear chat when leaving a historical session view
        if (state.isViewingHistory) {
            el.chatMessages.innerHTML = '';
            if (el.chatEmpty) el.chatEmpty.style.display = 'none';
            if (el.sessionTitle) {
                el.sessionTitle.textContent = objective.length > 60 ? objective.slice(0, 60) + '…' : objective;
            }
        } else {
            hideEmpty();
        }

        state.isViewingHistory = false;

        // Show user bubble and clear input
        addUserBubble(objective);
        el.taskInput.value = '';
        el.taskInput.style.height = '';

        if (response.type === 'chat') {
            // Conversational — direct Ollama stream, no task, no status bar
            connectChatStream(response.stream_url);
        } else {
            // Agent task — use existing task SSE pipeline
            state.activeSessionId = response.task_id;
            showStatusBar();
            setHeaderStatus('running');
            setHeaderAgent('—');
            setHeaderIter(0);
            connectStream(response.task_id, response.stream_url);
            loadSessions();
        }

    } catch (err) {
        resetInput();
        addChatMessage(`Failed: ${escapeHtml(err.message)}`, 'system', 'error');
    }
});

el.stopBtn.addEventListener('click', async () => {
    if (!state.currentTaskId) return;
    if (!confirm('Stop this task?')) return;

    try {
        await api.cancelTask(state.currentTaskId);
        if (state.eventSource) { state.eventSource.close(); state.eventSource = null; }
        setTyping(false);
        setHeaderStatus('cancelled');
        addChatMessage('Task stopped by user.', 'system', 'warning');
        resetInput();
        loadSessions();
    } catch (err) {
        addChatMessage(`Failed to stop: ${escapeHtml(err.message)}`, 'system', 'error');
    }
});

el.newChatBtn.addEventListener('click', () => {
    if (state.eventSource) return; // busy

    state.activeSessionId = null;
    state.isViewingHistory = false;
    el.chatMessages.innerHTML = '';

    // Re-show empty placeholder
    if (el.chatEmpty) {
        el.chatEmpty.style.display = '';
        el.chatMessages.appendChild(el.chatEmpty);
    }

    hideStatusBar();
    if (el.sessionTitle) el.sessionTitle.textContent = 'The Orchestrator';
    el.taskInput.focus();

    document.querySelectorAll('.session-item').forEach(s => s.classList.remove('active'));
});

// Sidebar toggle
el.sidebarToggleBtn.addEventListener('click', () => {
    const collapsed = el.chatSidebar.classList.toggle('collapsed');
    localStorage.setItem('sidebarCollapsed', collapsed ? '1' : '0');
});

// Restore sidebar state on load
if (localStorage.getItem('sidebarCollapsed') === '1') {
    el.chatSidebar.classList.add('collapsed');
}

// Auto-resize textarea
el.taskInput.addEventListener('input', () => {
    el.taskInput.style.height = 'auto';
    el.taskInput.style.height = Math.min(el.taskInput.scrollHeight, 200) + 'px';
});

el.taskInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        el.submitBtn.click();
    }
});

// ═══════════════════════════════════════════════════════════════════════
// Init
// ═══════════════════════════════════════════════════════════════════════

async function init() {
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }
    await loadSessions();

    // Auto-refresh sessions every 15s (picks up status changes)
    setInterval(loadSessions, 15000);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
