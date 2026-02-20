/**
 * The Orchestrator - Settings Page JavaScript
 *
 * Handles:
 * - Dark/Light theme toggle with localStorage persistence
 * - System configuration display
 */

// ═══════════════════════════════════════════════════════════════════════
// Theme Management
// ═══════════════════════════════════════════════════════════════════════

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('orchestrator-theme', theme);

    const icon = document.getElementById('theme-icon');
    const label = document.getElementById('theme-label');

    if (icon && label) {
        if (theme === 'light') {
            icon.textContent = '☀️';
            label.textContent = 'Light Mode';
        } else {
            icon.textContent = '🌙';
            label.textContent = 'Dark Mode';
        }
    }
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    const next = current === 'dark' ? 'light' : 'dark';
    applyTheme(next);
}

// ═══════════════════════════════════════════════════════════════════════
// System Config
// ═══════════════════════════════════════════════════════════════════════

async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        if (!response.ok) return;
        const config = await response.json();

        const set = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val || '—';
        };

        set('ollama-model', config.ollama_model);
        set('ollama-url', config.ollama_base_url);
        set('redis-host', config.redis_host);
        set('redis-port', config.redis_port);
    } catch (e) {
        console.error('Failed to load config:', e);
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Initialization
// ═══════════════════════════════════════════════════════════════════════

function init() {
    // Apply saved theme
    const saved = localStorage.getItem('orchestrator-theme') || 'dark';
    applyTheme(saved);

    // Load system config
    loadConfig();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
