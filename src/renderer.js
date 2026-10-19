/**
 * Scriber — Main Dashboard Renderer
 * Controls live stats, history filtering, 1-click copy, dictation modes,
 * custom vocabulary, shorthand replacements, and audio configuration.
 */

// ─── DOM References ───────────────────────────────────────────────

const historyList       = document.getElementById('historyList');
const emptyState        = document.getElementById('emptyState');
const statusBadge       = document.getElementById('statusBadge');
const statusInfo        = document.getElementById('statusInfo');
const healthWhisper     = document.getElementById('healthWhisper');
const healthOllama      = document.getElementById('healthOllama');
const btnRefresh        = document.getElementById('btnRefresh');
const tabHistory        = document.getElementById('tabHistory');
const tabSettings       = document.getElementById('tabSettings');
const viewHistory       = document.getElementById('viewHistory');
const viewSettings      = document.getElementById('viewSettings');

// Live stats
const statDictations    = document.getElementById('statDictations');
const statWords         = document.getElementById('statWords');
const statSaved         = document.getElementById('statSaved');

// Search
const historySearch     = document.getElementById('historySearch');
const searchClear       = document.getElementById('searchClear');

// Mode selectors
const quickModeSelect   = document.getElementById('quickModeSelect');
const settingDictationMode = document.getElementById('settingDictationMode');

// Settings controls
const settingInputDevice  = document.getElementById('settingInputDevice');
const settingWhisperModel = document.getElementById('settingWhisperModel');
const settingAudioDucking = document.getElementById('settingAudioDucking');
const settingLLMCleanup   = document.getElementById('settingLLMCleanup');
const settingAutoPaste    = document.getElementById('settingAutoPaste');
const settingLLMModel     = document.getElementById('settingLLMModel');
const settingOllamaHost   = document.getElementById('settingOllamaHost');
const btnClearHistory     = document.getElementById('btnClearHistory');

// Custom Vocabulary controls
const inputNewVocab       = document.getElementById('inputNewVocab');
const btnAddVocab         = document.getElementById('btnAddVocab');
const vocabTagsContainer  = document.getElementById('vocabTagsContainer');

// Shorthand Replacements controls
const repTrigger          = document.getElementById('repTrigger');
const repExpansion        = document.getElementById('repExpansion');
const btnAddRep           = document.getElementById('btnAddRep');
const replacementsList    = document.getElementById('replacementsList');
const settingLLMDesc      = document.getElementById('settingLLMDesc');

let currentView = 'history';
let history = [];
let searchQuery = '';
let currentCustomVocabulary = [];
let currentWordReplacements = {};
let currentConfigDevice = null;

// ─── View Toggling (Apple Segmented Navigation) ────────────────────

function switchView(viewName) {
  currentView = viewName;
  if (viewName === 'settings') {
    viewSettings.style.display = '';
    viewHistory.style.display = 'none';
    viewSettings.scrollTop = 0;
    if (tabSettings) {
      tabSettings.classList.add('active');
      tabSettings.setAttribute('aria-selected', 'true');
    }
    if (tabHistory) {
      tabHistory.classList.remove('active');
      tabHistory.setAttribute('aria-selected', 'false');
    }
  } else {
    viewSettings.style.display = 'none';
    viewHistory.style.display = '';
    viewHistory.scrollTop = 0;
    if (tabHistory) {
      tabHistory.classList.add('active');
      tabHistory.setAttribute('aria-selected', 'true');
    }
    if (tabSettings) {
      tabSettings.classList.remove('active');
      tabSettings.setAttribute('aria-selected', 'false');
    }
  }
}

if (tabHistory) tabHistory.addEventListener('click', () => switchView('history'));
if (tabSettings) tabSettings.addEventListener('click', () => switchView('settings'));

// ─── Native macOS Keyboard Shortcuts ──────────────────────────────

window.addEventListener('keydown', (e) => {
  // Cmd+1 -> Switch to History
  if ((e.metaKey || e.ctrlKey) && e.key === '1') {
    e.preventDefault();
    switchView('history');
  }
  // Cmd+, or Cmd+2 -> Switch to Preferences
  else if ((e.metaKey || e.ctrlKey) && (e.key === ',' || e.key === '2')) {
    e.preventDefault();
    switchView('settings');
  }
  // Escape -> Clear search filter or exit preferences back to history
  else if (e.key === 'Escape') {
    if (historySearch && document.activeElement === historySearch && historySearch.value) {
      historySearch.value = '';
      searchQuery = '';
      searchClear.style.display = 'none';
      renderFilteredHistory();
    } else if (currentView === 'settings') {
      switchView('history');
    }
  }
  // Cmd+R -> Refresh
  else if ((e.metaKey || e.ctrlKey) && (e.key === 'r' || e.key === 'R')) {
    e.preventDefault();
    btnRefresh?.click();
  }
});

btnRefresh?.addEventListener('click', () => {
  window.scriber.fetchHistory();
  window.scriber.fetchStats();
  btnRefresh.style.transform = 'rotate(360deg)';
  setTimeout(() => { btnRefresh.style.transform = ''; }, 500);
});

// ─── Live Stats ───────────────────────────────────────────────────

function updateStats(stats) {
  if (!stats) return;
  statDictations.textContent = (stats.total_transcriptions || 0).toLocaleString();
  statWords.textContent = (stats.total_words || 0).toLocaleString();
  const mins = stats.time_saved_minutes || 0;
  statSaved.textContent = mins >= 60 ? `${(mins / 60).toFixed(1)}h` : `${mins}m`;
}

// ─── Search Filtering ─────────────────────────────────────────────

historySearch.addEventListener('input', (e) => {
  searchQuery = e.target.value.toLowerCase().trim();
  searchClear.style.display = searchQuery ? 'block' : 'none';
  renderFilteredHistory();
});

searchClear.addEventListener('click', () => {
  historySearch.value = '';
  searchQuery = '';
  searchClear.style.display = 'none';
  renderFilteredHistory();
  historySearch.focus();
});

function renderFilteredHistory() {
  if (!searchQuery) {
    renderHistory(history);
    return;
  }
  const filtered = history.filter(item => {
    const cleaned = (item.cleaned_text || '').toLowerCase();
    const raw = (item.raw_text || '').toLowerCase();
    return cleaned.includes(searchQuery) || raw.includes(searchQuery);
  });
  renderHistory(filtered);
}

// ─── Status Bar ───────────────────────────────────────────────────

function updateStatusBadge(state, extra = {}) {
  statusBadge.className = `status-badge ${state}`;

  switch (state) {
    case 'listening':
      const appName = extra.active_app?.name ? ` · ${extra.active_app.name}` : '';
      statusBadge.innerHTML = `<span class="status-badge-dot"></span>Recording${appName}`;
      statusInfo.textContent = 'Speak clearly into your microphone…';
      break;
    case 'processing':
      statusBadge.innerHTML = '<span class="status-badge-dot"></span>Processing';
      statusInfo.textContent = 'Metal GPU STT + AI Polishing…';
      break;
    case 'done':
      statusBadge.innerHTML = '<span class="status-badge-dot"></span>Done';
      const timeStr = extra.pipeline_time ? ` (${extra.pipeline_time}s)` : '';
      statusInfo.textContent = extra.cleaned_text
        ? `"${extra.cleaned_text.slice(0, 50)}${extra.cleaned_text.length > 50 ? '…' : ''}"${timeStr}`
        : `Text pasted!${timeStr}`;
      setTimeout(() => {
        window.scriber.fetchHistory();
        window.scriber.fetchStats();
      }, 500);
      break;
    case 'error':
      statusBadge.innerHTML = '<span class="status-badge-dot"></span>Error';
      statusInfo.textContent = extra.message || 'Something went wrong';
      break;
    default:
      statusBadge.innerHTML = '<span class="status-badge-dot"></span>Ready';
      statusInfo.innerHTML = 'Press <kbd>Fn</kbd> or <kbd>⌥</kbd> <kbd>Space</kbd> to dictate';
  }
}

// ─── History Rendering ────────────────────────────────────────────

function renderHistory(items) {
  // Clear existing entries (keep empty state)
  const existing = historyList.querySelectorAll('.history-entry, .date-group');
  existing.forEach(el => el.remove());

  if (!items || items.length === 0) {
    emptyState.style.display = '';
    if (searchQuery) {
      emptyState.querySelector('h3').textContent = 'No matching dictations';
      emptyState.querySelector('p').textContent = `No results found for "${searchQuery}"`;
    } else {
      emptyState.querySelector('h3').textContent = 'No transcriptions yet';
      emptyState.querySelector('p').innerHTML = 'Press <kbd>Fn</kbd> or <kbd>⌥</kbd> <kbd>Space</kbd> to dictate anywhere';
    }
    return;
  }

  emptyState.style.display = 'none';

  let lastDate = '';

  items.forEach((entry, index) => {
    const ts = new Date(entry.timestamp);
    const dateStr = getDateLabel(ts);

    // Date group header
    if (dateStr !== lastDate) {
      lastDate = dateStr;
      const dateEl = document.createElement('div');
      dateEl.className = 'date-group';
      dateEl.textContent = dateStr;
      historyList.appendChild(dateEl);
    }

    const words = (entry.cleaned_text || '').split(/\s+/).filter(Boolean).length;
    const el = document.createElement('div');
    el.className = 'history-entry';
    el.style.animationDelay = `${Math.min(index * 0.03, 0.3)}s`;
    el.innerHTML = `
      <div class="history-entry-header">
        <div class="history-entry-meta">
          <span class="time">${formatTime(ts)}</span>
          <span class="duration">${entry.duration_seconds || 0}s</span>
          <span class="words-tag">${words} words</span>
        </div>
        <div class="history-entry-actions">
          <button class="btn-small copy" title="Copy to clipboard">📋</button>
          <button class="btn-small delete" title="Delete" data-id="${entry.id}">🗑</button>
        </div>
      </div>
      <div class="history-entry-text">${escapeHtml(entry.cleaned_text)}</div>
      ${entry.raw_text && entry.raw_text !== entry.cleaned_text
        ? `<div class="history-entry-raw"><strong>Raw STT:</strong> ${escapeHtml(entry.raw_text)}</div>`
        : ''
      }
    `;

    // Toggle raw text diff view on card click
    el.addEventListener('click', (e) => {
      if (e.target.closest('.btn-small')) return;
      el.classList.toggle('expanded');
    });

    // 1-Click Copy with visual checkmark feedback
    const btnCopy = el.querySelector('.copy');
    btnCopy?.addEventListener('click', (e) => {
      e.stopPropagation();
      navigator.clipboard.writeText(entry.cleaned_text);
      btnCopy.textContent = '✓';
      btnCopy.classList.add('copied');
      showToast('Copied to clipboard');
      setTimeout(() => {
        btnCopy.textContent = '📋';
        btnCopy.classList.remove('copied');
      }, 1200);
    });

    // Delete
    el.querySelector('.delete')?.addEventListener('click', (e) => {
      e.stopPropagation();
      el.style.transform = 'translateX(80px)';
      el.style.opacity = '0';
      setTimeout(() => {
        window.scriber.deleteEntry(entry.id);
      }, 250);
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

// ─── Toast Notifications ──────────────────────────────────────────

let toastEl = null;

function showToast(message) {
  if (!toastEl) {
    toastEl = document.createElement('div');
    toastEl.className = 'toast';
    document.body.appendChild(toastEl);
  }
  toastEl.textContent = message;
  toastEl.classList.add('show');
  setTimeout(() => toastEl.classList.remove('show'), 1800);
}

// ─── Custom Vocabulary Management ─────────────────────────────────

function renderVocabularyTags(vocabList) {
  currentCustomVocabulary = Array.isArray(vocabList) ? vocabList : [];
  vocabTagsContainer.innerHTML = '';

  if (currentCustomVocabulary.length === 0) {
    vocabTagsContainer.innerHTML = '<span style="color: var(--text-muted); font-size: 12px;">No custom terms yet. Add names, brand words, or code identifiers below.</span>';
    return;
  }

  currentCustomVocabulary.forEach((term, index) => {
    const tag = document.createElement('div');
    tag.className = 'vocab-tag';
    tag.innerHTML = `
      <span>${escapeHtml(term)}</span>
      <button class="vocab-tag-remove" data-index="${index}" title="Remove">✕</button>
    `;
    tag.querySelector('.vocab-tag-remove').addEventListener('click', () => {
      removeVocabularyTerm(index);
    });
    vocabTagsContainer.appendChild(tag);
  });
}

function addVocabularyTerm() {
  const val = inputNewVocab.value.trim();
  if (!val) return;
  // Split multiple if comma separated
  const terms = val.split(',').map(s => s.trim()).filter(Boolean);
  terms.forEach(term => {
    if (!currentCustomVocabulary.includes(term)) {
      currentCustomVocabulary.push(term);
    }
  });
  inputNewVocab.value = '';
  renderVocabularyTags(currentCustomVocabulary);
  sendConfigUpdate('custom_vocabulary', currentCustomVocabulary);
  showToast('Vocabulary updated');
}

function removeVocabularyTerm(index) {
  currentCustomVocabulary.splice(index, 1);
  renderVocabularyTags(currentCustomVocabulary);
  sendConfigUpdate('custom_vocabulary', currentCustomVocabulary);
}

btnAddVocab.addEventListener('click', addVocabularyTerm);
inputNewVocab.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    addVocabularyTerm();
  }
});

// ─── Shorthand Replacements Management ────────────────────────────

function renderReplacements(replacements) {
  currentWordReplacements = (replacements && typeof replacements === 'object') ? replacements : {};
  replacementsList.innerHTML = '';

  const entries = Object.entries(currentWordReplacements);
  if (entries.length === 0) {
    replacementsList.innerHTML = '<span style="color: var(--text-muted); font-size: 12px; padding: 6px;">No replacements added yet.</span>';
    return;
  }

  entries.forEach(([trigger, expansion]) => {
    const row = document.createElement('div');
    row.className = 'replacement-item';
    row.innerHTML = `
      <span class="rep-trigger">${escapeHtml(trigger)}</span>
      <span class="rep-arrow">→</span>
      <span class="rep-expansion">${escapeHtml(expansion)}</span>
      <button class="rep-delete" title="Delete replacement">🗑</button>
    `;
    row.querySelector('.rep-delete').addEventListener('click', () => {
      delete currentWordReplacements[trigger];
      renderReplacements(currentWordReplacements);
      sendConfigUpdate('word_replacements', currentWordReplacements);
    });
    replacementsList.appendChild(row);
  });
}

function addReplacement() {
  const trigger = repTrigger.value.trim().toLowerCase();
  const expansion = repExpansion.value.trim();
  if (!trigger || !expansion) return;

  currentWordReplacements[trigger] = expansion;
  repTrigger.value = '';
  repExpansion.value = '';
  renderReplacements(currentWordReplacements);
  sendConfigUpdate('word_replacements', currentWordReplacements);
  showToast('Shorthand added');
}

btnAddRep.addEventListener('click', addReplacement);
repExpansion.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    addReplacement();
  }
});

// ─── Audio Devices ────────────────────────────────────────────────

function renderAudioDevices(data, selectedId = null) {
  if (!data) return;
  const devices = Array.isArray(data) ? data : (data.devices || []);
  const defaultName = (!Array.isArray(data) && data.default_name && data.default_name !== 'Unknown') ? data.default_name : '';

  const prevVal = (selectedId !== null && selectedId !== undefined)
    ? String(selectedId)
    : (currentConfigDevice !== null ? String(currentConfigDevice) : settingInputDevice.value);

  settingInputDevice.innerHTML = '';

  const optDefault = document.createElement('option');
  optDefault.value = 'default';
  optDefault.textContent = defaultName 
    ? `System Default (${defaultName})` 
    : 'System Default';
  settingInputDevice.appendChild(optDefault);

  devices.forEach((dev) => {
    if (!dev || !dev.name) return;
    const opt = document.createElement('option');
    opt.value = dev.name;
    opt.dataset.id = String(dev.id);
    opt.textContent = dev.name;
    settingInputDevice.appendChild(opt);
  });

  if (!prevVal || prevVal === 'null' || prevVal === 'default') {
    settingInputDevice.value = 'default';
  } else {
    const match = Array.from(settingInputDevice.options).find(o => o.value === prevVal || o.dataset?.id === prevVal);
    settingInputDevice.value = match ? match.value : 'default';
  }
}

// ─── Config Sync ──────────────────────────────────────────────────

function applyConfig(config) {
  if (!config) return;

  // Whisper & Cleanup
  settingWhisperModel.value = config.whisper_model || 'large-v3-turbo';
  settingLLMCleanup.checked = config.llm_cleanup_enabled !== false;
  settingAutoPaste.checked = config.auto_paste !== false;
  settingAudioDucking.checked = config.audio_ducking === true;
  settingLLMModel.value = config.llm_model || 'llama3.2:3b';
  settingOllamaHost.value = config.ollama_host || 'http://localhost:11434';

  // Dictation Mode
  const mode = config.dictation_mode || 'auto';
  quickModeSelect.value = mode;
  settingDictationMode.value = mode;

  // Custom Vocab & Replacements
  if (config.custom_vocabulary) {
    renderVocabularyTags(config.custom_vocabulary);
  }
  if (config.word_replacements) {
    renderReplacements(config.word_replacements);
  }

  // Input Device
  if (config.input_device !== undefined) {
    currentConfigDevice = config.input_device;
    if (config.input_device === null || config.input_device === 'default') {
      settingInputDevice.value = 'default';
    } else {
      const valStr = String(config.input_device);
      const match = Array.from(settingInputDevice.options).find(o => o.value === valStr || o.dataset?.id === valStr);
      settingInputDevice.value = match ? match.value : 'default';
    }
  }

  // LLM latency hint
  if (config.llm_cleanup_enabled !== undefined && settingLLMDesc) {
    settingLLMDesc.textContent = config.llm_cleanup_enabled
      ? 'Active: AI formatting & filler removal (adds ~120ms latency)'
      : 'Disabled: 0ms LLM overhead (fastest raw delivery)';
  }
}

function sendConfigUpdate(key, value) {
  window.scriber.updateConfig({ [key]: value });
}

// Event Listeners for Config Controls
quickModeSelect.addEventListener('change', () => {
  const mode = quickModeSelect.value;
  settingDictationMode.value = mode;
  sendConfigUpdate('dictation_mode', mode);
  showToast(`Dictation mode: ${mode}`);
});

settingDictationMode.addEventListener('change', () => {
  const mode = settingDictationMode.value;
  quickModeSelect.value = mode;
  sendConfigUpdate('dictation_mode', mode);
  showToast(`Dictation mode: ${mode}`);
});

settingInputDevice.addEventListener('change', () => {
  const val = settingInputDevice.value;
  const deviceVal = val === 'default' ? null : val;
  currentConfigDevice = deviceVal;
  sendConfigUpdate('input_device', deviceVal);
  showToast('Microphone updated');
});

settingWhisperModel.addEventListener('change', () => sendConfigUpdate('whisper_model', settingWhisperModel.value));
settingAudioDucking.addEventListener('change', () => sendConfigUpdate('audio_ducking', settingAudioDucking.checked));
settingLLMCleanup.addEventListener('change', () => {
  const enabled = settingLLMCleanup.checked;
  sendConfigUpdate('llm_cleanup_enabled', enabled);
  if (settingLLMDesc) {
    settingLLMDesc.textContent = enabled
      ? 'Active: AI formatting & filler removal (adds ~120ms latency)'
      : 'Disabled: 0ms LLM overhead (fastest raw delivery)';
  }
  showToast(`AI Text Cleanup: ${enabled ? 'Enabled' : 'Disabled'}`);
});
settingAutoPaste.addEventListener('change', () => sendConfigUpdate('auto_paste', settingAutoPaste.checked));
settingLLMModel.addEventListener('change', () => sendConfigUpdate('llm_model', settingLLMModel.value));
settingOllamaHost.addEventListener('change', () => sendConfigUpdate('ollama_host', settingOllamaHost.value));

btnClearHistory.addEventListener('click', () => {
  if (confirm('Delete all transcription history? This cannot be undone.')) {
    window.scriber.clearHistory();
    showToast('History cleared');
  }
});

// Auto-refresh devices on user interaction
settingInputDevice.addEventListener('focus', () => window.scriber.fetchAudioDevices());
settingInputDevice.addEventListener('mousedown', () => window.scriber.fetchAudioDevices());

if (navigator.mediaDevices && navigator.mediaDevices.addEventListener) {
  navigator.mediaDevices.addEventListener('devicechange', () => {
    window.scriber.fetchAudioDevices();
  });
}

// ─── IPC Listeners ────────────────────────────────────────────────

window.scriber.onStateChange((data) => {
  updateStatusBadge(data.state, data);

  if (data.type === 'init') {
    if (data.audio_devices) renderAudioDevices(data.audio_devices);
    if (data.config) applyConfig(data.config);
    if (data.stats) updateStats(data.stats);
  }
});

window.scriber.onConfigChange((data) => {
  if (data.config) applyConfig(data.config);
});

window.scriber.onHistoryUpdate((data) => {
  history = data || [];
  renderFilteredHistory();
});

window.scriber.onStatsUpdate((data) => {
  updateStats(data);
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
  if (data.stats) {
    updateStats(data.stats);
  }
});

// ─── Initialization ───────────────────────────────────────────────

window.addEventListener('DOMContentLoaded', () => {
  setTimeout(() => {
    window.scriber.fetchHistory();
    window.scriber.fetchStats();
    window.scriber.fetchAudioDevices();
    window.scriber.requestHealth();
  }, 400);

  // Poll health, stats, and audio devices every 5 seconds
  setInterval(() => {
    window.scriber.requestHealth();
    window.scriber.fetchStats();
    window.scriber.fetchAudioDevices();
  }, 5000);
});
