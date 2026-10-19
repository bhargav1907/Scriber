/**
 * Scriber — Floating Widget Renderer
 * Handles real-time status transitions, active app badge, sound synthesis,
 * and 7-bar audio reactive visualizer.
 */

const widget     = document.getElementById('widget');
const dot        = document.getElementById('statusDot');
const text       = document.getElementById('statusText');
const timer      = document.getElementById('timer');
const appBadge   = document.getElementById('appBadge');
const appIcon    = document.getElementById('appIcon');
const appName    = document.getElementById('appName');
const speedBadge = document.getElementById('speedBadge');
const speedText  = document.getElementById('speedText');

const bars = [0, 1, 2, 3, 4, 5, 6].map(i => document.getElementById(`bar${i}`));

let timerInterval = null;
let recordStart   = 0;

// ─── Sound Effects (Synthesized on Shared Apple AudioContext) ─────

let audioCtx = null;

function getAudioContext() {
  try {
    if (!audioCtx || audioCtx.state === 'closed') {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (AudioContextClass) {
        audioCtx = new AudioContextClass({ latencyHint: 'interactive' });
      }
    }
    return audioCtx;
  } catch {
    audioCtx = null;
    return null;
  }
}

async function playTone(freq, duration = 0.12, vol = 0.05) {
  try {
    const ctx = getAudioContext();
    if (!ctx) return;
    if (ctx.state === 'suspended') {
      await ctx.resume().catch(() => {});
    }
    if (ctx.state !== 'running') return;

    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = 'sine';
    osc.frequency.setValueAtTime(freq, ctx.currentTime);
    gain.gain.setValueAtTime(vol, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + duration);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + duration);
  } catch {}
}

function playStartSound() {
  playTone(880, 0.10, 0.05);
  setTimeout(() => playTone(1320, 0.08, 0.04), 80);
}

function playDoneSound() {
  playTone(1047, 0.08, 0.05);
  setTimeout(() => playTone(1319, 0.08, 0.05), 70);
  setTimeout(() => playTone(1568, 0.12, 0.05), 140);
}

function playErrorSound() {
  playTone(330, 0.18, 0.06);
  setTimeout(() => playTone(262, 0.22, 0.06), 140);
}

// ─── Timer ────────────────────────────────────────────────────────

function startTimer() {
  recordStart = Date.now();
  timer.textContent = '0:00';
  timerInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - recordStart) / 1000);
    const mins = Math.floor(elapsed / 60);
    const secs = elapsed % 60;
    timer.textContent = `${mins}:${String(secs).padStart(2, '0')}`;
  }, 200);
}

function stopTimer() {
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
}

let lastAppName = '';

function updateAppBadge(appInfo, mode) {
  if (!appInfo) return;
  const name = appInfo.name || 'System';
  const icon = appInfo.icon || '✨';

  if (name !== lastAppName) {
    lastAppName = name;
    appBadge.classList.remove('badge-updated');
    void appBadge.offsetWidth;
    appBadge.classList.add('badge-updated');
  }

  appIcon.textContent = icon;
  appName.textContent = name;
  appBadge.title = `Target: ${name} (${mode || 'auto'})`;
}

// ─── State Machine ────────────────────────────────────────────────

function setState(state, extra = {}) {
  widget.classList.remove('state-listening', 'state-processing', 'state-done', 'state-error');
  dot.classList.remove('processing', 'done', 'error');

  if (extra.active_app) {
    updateAppBadge(extra.active_app, extra.mode);
  }

  switch (state) {
    case 'listening':
      widget.classList.add('visible', 'state-listening');
      dot.className = 'status-dot';
      text.textContent = 'Listening…';
      startTimer();
      playStartSound();
      break;

    case 'processing':
      widget.classList.add('visible', 'state-processing');
      dot.classList.add('processing');
      text.textContent = 'Polishing…';
      stopTimer();
      break;

    case 'done':
      widget.classList.add('visible', 'state-done');
      dot.classList.add('done');
      text.textContent = 'Pasted!';
      stopTimer();

      if (extra.metrics) {
        const m = extra.metrics;
        const totalStr = m.total_ms < 1000 ? `${m.total_ms}ms` : `${(m.total_ms / 1000).toFixed(2)}s`;
        const breakdown = m.llm_enabled && m.llm_ms > 0
          ? `(W: ${m.whisper_ms}ms · L: ${m.llm_ms}ms)`
          : `(W: ${m.whisper_ms}ms)`;
        speedText.textContent = `⚡ ${totalStr} ${breakdown}`;
      } else {
        const timeSec = extra.pipeline_time ? `${extra.pipeline_time}s` : '0.6s';
        const words = extra.word_count ? ` · ${extra.word_count}w` : '';
        speedText.textContent = `⚡ ${timeSec}${words}`;
      }

      playDoneSound();
      break;

    case 'error':
      widget.classList.add('visible', 'state-error');
      dot.classList.add('error');
      text.textContent = extra.message || 'Error';
      stopTimer();
      playErrorSound();
      break;

    case 'idle':
    default:
      widget.classList.remove('visible');
      stopTimer();
      timer.textContent = '0:00';
      bars.forEach(b => { if (b) b.style.height = '4px'; });
      break;
  }
}

// ─── Audio Reactive Waveform ──────────────────────────────────────

function updateAudioBars(level) {
  // level is normalized roughly 0..1
  const baseProfile = [0.35, 0.65, 0.95, 1.0, 0.9, 0.6, 0.3];
  bars.forEach((bar, i) => {
    if (!bar) return;
    const profile = baseProfile[i];
    const jitter = (Math.sin(Date.now() / 60 + i) * 0.2 + 0.8);
    const dynamicHeight = 3.5 + (level * 22 * profile * jitter);
    bar.style.height = `${Math.max(3, Math.min(24, Math.round(dynamicHeight)))}px`;
  });
}

// ─── IPC Bridge Listeners ─────────────────────────────────────────

window.scriber.onStateChange((data) => {
  setState(data.state, data);
});

window.scriber.onAudioLevel((data) => {
  updateAudioBars(data.level);
});

// Start hidden
setState('idle');
