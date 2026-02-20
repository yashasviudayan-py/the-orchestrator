/**
 * The Orchestrator - Health Page JavaScript
 *
 * Handles:
 * - Polling /api/health every 10s
 * - Updating service indicator dots and status text
 * - Start/stop service actions via /api/services/{service}/{action}
 */

const STATUS_LABELS = {
    healthy: 'Healthy',
    degraded: 'Degraded',
    down: 'Offline',
    unknown: 'Unknown',
};

// ═══════════════════════════════════════════════════════════════════════
// Health Polling
// ═══════════════════════════════════════════════════════════════════════

async function pollHealth() {
    try {
        const response = await fetch('/api/health');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();

        // Update overall banner
        const overall = data.status || 'unknown';
        const indicator = document.getElementById('overall-indicator');
        const statusText = document.getElementById('overall-status-text');
        const lastCheck = document.getElementById('last-health-check');

        if (indicator) {
            indicator.className = `health-banner-indicator ${overall}`;
        }
        if (statusText) {
            statusText.textContent = `System ${STATUS_LABELS[overall] || overall}`;
        }
        if (lastCheck) {
            lastCheck.textContent = `Last checked: ${new Date().toLocaleTimeString()}`;
        }

        // Update per-service indicators
        const agents = data.agents || {};
        const serviceMap = {
            research: 'research',
            context: 'context',
            pr: 'pr',
            ollama: 'ollama',
            redis: 'redis',
        };

        for (const [key, agentKey] of Object.entries(serviceMap)) {
            const agentStatus = agents[agentKey] || 'unknown';
            const dot = document.querySelector(`[data-indicator="${key}"]`);
            const statusEl = document.getElementById(`status-${key}`);

            if (dot) {
                dot.className = `agent-indicator ${agentStatus}`;
            }
            if (statusEl) {
                statusEl.textContent = STATUS_LABELS[agentStatus] || agentStatus;
                statusEl.style.color = agentStatus === 'healthy' ? 'var(--success)'
                    : agentStatus === 'degraded' ? 'var(--warning)'
                    : agentStatus === 'down' ? 'var(--error)'
                    : 'var(--text-dim)';
            }
        }

    } catch (e) {
        console.error('Health check failed:', e);
        const statusText = document.getElementById('overall-status-text');
        if (statusText) statusText.textContent = 'Health check failed';
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Service Toggle
// ═══════════════════════════════════════════════════════════════════════

async function toggleService(service, action) {
    const spinner = document.getElementById(`spinner-${service}`);
    const msgEl = document.getElementById(`msg-${service}`);
    const startBtn = document.getElementById(`btn-${service}-start`);
    const stopBtn = document.getElementById(`btn-${service}-stop`);

    // Show spinner, disable buttons
    if (spinner) spinner.classList.remove('hidden');
    if (startBtn) startBtn.disabled = true;
    if (stopBtn) stopBtn.disabled = true;
    if (msgEl) msgEl.textContent = `${action === 'start' ? 'Starting' : 'Stopping'} ${service}…`;

    try {
        const response = await fetch(`/api/services/${service}/${action}`, { method: 'POST' });
        const data = await response.json();

        if (msgEl) {
            msgEl.textContent = data.message || (data.success ? 'Done' : 'Failed');
            msgEl.style.color = data.success ? 'var(--success)' : 'var(--error)';
        }

        // Re-poll health after a short delay
        setTimeout(pollHealth, 1500);

    } catch (e) {
        console.error(`Failed to ${action} ${service}:`, e);
        if (msgEl) {
            msgEl.textContent = `Error: ${e.message}`;
            msgEl.style.color = 'var(--error)';
        }
    } finally {
        if (spinner) spinner.classList.add('hidden');
        if (startBtn) startBtn.disabled = false;
        if (stopBtn) stopBtn.disabled = false;
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Initialization
// ═══════════════════════════════════════════════════════════════════════

function init() {
    pollHealth();
    setInterval(pollHealth, 10000);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
