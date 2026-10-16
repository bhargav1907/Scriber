/**
 * Scriber — Main Window Renderer
 * Manages the history view, settings panel, and status bar.
 */

// ─── DOM Refs ─────────────────────────────────────────────────────

const historyList    = document.getElementById('historyList');
const emptyState     = document.getElementById('emptyState');
const statusBadge    = document.getElementById('statusBadge');
const statusInfo     = document.getElementById('statusInfo');
const healthWhisper  = document.getElementById('healthWhisper');
const healthOllama   = document.getElementById('healthOllama');
const btnSettings    = document.getElementById('btnSettings');
const btnRefresh     = document.getElementById('btnRefresh');
const viewHistory    = document.getElementById('viewHistory');
const viewSettings   = document.getElementById('viewSettings');

// Settings controls
const settingInputDevice  = document.getElementById('settingInputDevice');
const settingWhisperModel = document.getElementById('settingWhisperModel');
const settingLLMCleanup   = document.getElementById('settingLLMCleanup');
const settingAutoPaste    = document.getElementById('settingAutoPaste');
const settingLLMModel     = document.getElementById('settingLLMModel');
const settingOllamaHost   = document.getElementById('settingOllamaHost');
const btnClearHistory     = document.getElementById('btnClearHistory');

let currentView = 'history';
let history = [];

// ─── View Toggling ────────────────────────────────────────────────

btnSettings.addEventListener('click', () => {
  if (currentView === 'settings') {
    currentView = 'history';
    viewSettings.style.display = 'none';
    viewHistory.style.display = '';
    btnSettings.classList.remove('active');
  } else {
    currentView = 'settings';
    viewSettings.style.display = '';
    viewHistory.style.display = 'none';
    btnSettings.classList.add('active');
  }
});

btnRefresh.addEventListener('click', () => {
  window.scriber.fetchHistory();
  btnRefresh.style.transform = 'rotate(360deg)';
  setTimeout(() => { btnRefresh.style.transform = ''; }, 500);
});

// ─── Status Bar ───────────────────────────────────────────────────

function updateStatusBadge(state, extra = {}) {
  statusBadge.className = `status-badge ${state}`;

  switch (state) {
    case 'listening':
      statusBadge.innerHTML = '<span class="status-badge-dot"></span>Recording';
      statusInfo.textContent = 'Speak now…';
      break;
    case 'processing':
      statusBadge.innerHTML = '<span class="status-badge-dot"></span>Processing';
      statusInfo.textContent = 'Transcribing & cleaning up…';
      break;
    case 'done':
      statusBadge.innerHTML = '<span class="status-badge-dot"></span>Done';
      const timeStr = extra.pipeline_time ? ` (${extra.pipeline_time}s)` : '';
      statusInfo.textContent = extra.cleaned_text
        ? `"${extra.cleaned_text.slice(0, 50)}${extra.cleaned_text.length > 50 ? '…' : ''}"${timeStr}`
        : `Text pasted!${timeStr}`;
      // Refresh history
      setTimeout(() => window.scriber.fetchHistory(), 500);
      break;
    case 'error':
      statusBadge.innerHTML = '<span class="status-badge-dot"></span>Error';
      statusInfo.textContent = extra.message || 'Something went wrong';
      break;
    default:
      statusBadge.innerHTML = '<span class="status-badge-dot"></span>Ready';
      statusInfo.innerHTML = 'Press <kbd>Fn</kbd> or <kbd>⌥</kbd> <kbd>Space</kbd> to start';
  }
}

// ─── History Rendering ────────────────────────────────────────────

function renderHistory(items) {
  history = items;
  // Clear existing entries (keep empty state)
  const existing = historyList.querySelectorAll('.history-entry, .date-group');
  existing.forEach(el => el.remove());

  if (!items || items.length === 0) {
    emptyState.style.display = '';
    return;
  }

  emptyState.style.display = 'none';

  let lastDate = '';

  items.forEach((entry, index) => {
    const ts = new Date(entry.timestamp);
    const dateStr = getDateLabel(ts);

    // Add date group header if needed
    if (dateStr !== lastDate) {
      lastDate = dateStr;
      const dateEl = document.createElement('div');
      dateEl.className = 'date-group';
      dateEl.textContent = dateStr;
      historyList.appendChild(dateEl);
    }

    const el = document.createElement('div');
    el.className = 'history-entry';
    el.style.animationDelay = `${index * 0.04}s`;
    el.innerHTML = `
      <div class="history-entry-header">
        <div class="history-entry-meta">
          <span class="time">${formatTime(ts)}</span>
          <span class="duration">${entry.duration_seconds}s</span>
        </div>
        <div class="history-entry-actions">
          <button class="btn-small copy" title="Copy to clipboard" data-text="${escapeAttr(entry.cleaned_text)}">📋</button>
          <button class="btn-small delete" title="Delete" data-id="${entry.id}">🗑</button>
        </div>
      </div>
      <div class="history-entry-text">${escapeHtml(entry.cleaned_text)}</div>
      ${entry.raw_text !== entry.cleaned_text
        ? `<div class="history-entry-raw"><strong>Raw:</strong> ${escapeHtml(entry.raw_text)}</div>`
        : ''
      }
    `;

    // Toggle raw text on click
    el.addEventListener('click', (e) => {
      if (e.target.closest('.btn-small')) return;
      el.classList.toggle('expanded');
    });

    // Copy button
    el.querySelector('.copy')?.addEventListener('click', (e) => {
      e.stopPropagation();
      navigator.clipboard.writeText(entry.cleaned_text);
      showToast('Copied to clipboard');
    });

    // Delete button
    el.querySelector('.delete')?.addEventListener('click', (e) => {
      e.stopPropagation();
      el.style.transform = 'translateX(100%)';
      el.style.opacity = '0';
      setTimeout(() => {
        window.scriber.deleteEntry(entry.id);
      }, 300);
    });

    historyList.appendChild(el);
  });
}

function getDateLabel(date) {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  if (date.toDateString() === today.toDateString()) return 'Today';
  if (date.toDateString() === yesterday.toDateString()) return 'Yesterday';

  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatTime(date) {
  return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function escapeAttr(str) {
  return str.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ─── Toast ────────────────────────────────────────────────────────

let toastEl = null;

function showToast(message) {
  if (!toastEl) {
    toastEl = document.createElement('div');
    toastEl.className = 'toast';
    document.body.appendChild(toastEl);
  }
  toastEl.textContent = message;
  toastEl.classList.add('show');
  setTimeout(() => toastEl.classList.remove('show'), 2000);
}

// ─── Settings ─────────────────────────────────────────────────────

function renderAudioDevices(data, selectedId = null) {
  if (!data) return;
  const devices = Array.isArray(data) ? data : (data.devices || []);
  const defaultName = (!Array.isArray(data) && data.default_name && data.default_name !== 'Unknown') ? data.default_name : '';

  const currentVal = settingInputDevice.value;
  settingInputDevice.innerHTML = '';

  const optDefault = document.createElement('option');
  optDefault.value = 'default';
  optDefault.textContent = defaultName 
    ? `System Default (${defaultName})` 
    : 'System Default';
  settingInputDevice.appendChild(optDefault);

  devices.forEach((dev) => {
    if (dev.id === null) return;
    const opt = document.createElement('option');
    opt.value = String(dev.id);
    opt.textContent = dev.name;
    settingInputDevice.appendChild(opt);
  });

  if (selectedId !== null && selectedId !== undefined) {
    settingInputDevice.value = String(selectedId);
  } else if (currentVal) {
    settingInputDevice.value = currentVal;
  }
}

function applyConfig(config) {
  if (!config) return;
  settingWhisperModel.value = config.whisper_model || 'base';
  settingLLMCleanup.checked = config.llm_cleanup_enabled !== false;
  settingAutoPaste.checked = config.auto_paste !== false;
  settingLLMModel.value = config.llm_model || 'llama3.2:3b';
  settingOllamaHost.value = config.ollama_host || 'http://localhost:11434';
  if (config.input_device !== undefined) {
    settingInputDevice.value = config.input_device === null ? 'default' : String(config.input_device);
  }
}

function sendConfigUpdate(key, value) {
  window.scriber.updateConfig({ [key]: value });
}

settingInputDevice.addEventListener('change', () => {
  const val = settingInputDevice.value;
  const deviceId = val === 'default' ? null : parseInt(val, 10);
  sendConfigUpdate('input_device', deviceId);
  showToast('Microphone updated');
});
settingWhisperModel.addEventListener('change', () => sendConfigUpdate('whisper_model', settingWhisperModel.value));
settingLLMCleanup.addEventListener('change', () => sendConfigUpdate('llm_cleanup_enabled', settingLLMCleanup.checked));
settingAutoPaste.addEventListener('change', () => sendConfigUpdate('auto_paste', settingAutoPaste.checked));
settingLLMModel.addEventListener('change', () => sendConfigUpdate('llm_model', settingLLMModel.value));
settingOllamaHost.addEventListener('change', () => sendConfigUpdate('ollama_host', settingOllamaHost.value));

btnClearHistory.addEventListener('click', () => {
  if (confirm('Delete all transcription history? This cannot be undone.')) {
    window.scriber.clearHistory();
    showToast('History cleared');
  }
});

// ─── IPC Listeners ────────────────────────────────────────────────

window.scriber.onStateChange((data) => {
  updateStatusBadge(data.state, data);

  // Apply config on init
  if (data.type === 'init') {
    if (data.audio_devices) renderAudioDevices(data.audio_devices);
    if (data.config) applyConfig(data.config);
  }
});

window.scriber.onConfigChange((data) => {
  if (data.config) applyConfig(data.config);
});

window.scriber.onHistoryUpdate((data) => {
  renderHistory(data);
});

window.scriber.onAudioDevicesUpdate((devices) => {
  renderAudioDevices(devices);
});

window.scriber.onHealthUpdate((data) => {
  healthWhisper.className = `health-dot ${data.whisper_ready ? 'ok' : 'loading'}`;
  healthOllama.className = `health-dot ${data.ollama_connected ? 'ok' : 'error'}`;
  if (data.audio_devices) {
    renderAudioDevices(data.audio_devices);
  }
});

// ─── Init ─────────────────────────────────────────────────────────

// Fetch history, devices, and health on load
window.addEventListener('DOMContentLoaded', () => {
  setTimeout(() => {
    window.scriber.fetchHistory();
    window.scriber.fetchAudioDevices();
    window.scriber.requestHealth();
  }, 1000);

  // Poll health every 15 seconds
  setInterval(() => window.scriber.requestHealth(), 15000);
});
