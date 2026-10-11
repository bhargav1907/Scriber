/**
 * Scriber — Floating Widget Renderer
 * Receives state + audio-level updates from the main process via IPC
 * and drives the widget UI (dot, text, timer, meter).
 */

const widget   = document.getElementById('widget');
const dot      = document.getElementById('statusDot');
const text     = document.getElementById('statusText');
const timer    = document.getElementById('timer');
const bars     = [0, 1, 2, 3, 4].map(i => document.getElementById(`bar${i}`));

let timerInterval = null;
let recordStart   = 0;

// ─── Sound Effects (tiny synthesized bleeps) ──────────────────────

function playTone(freq, duration = 0.15, vol = 0.08) {
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = 'sine';
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(vol, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
    osc.start();
    osc.stop(ctx.currentTime + duration);
  } catch {}
}

function playStartSound()   { playTone(880, 0.12, 0.06); setTimeout(() => playTone(1320, 0.1, 0.05), 100); }
function playDoneSound()    { playTone(1047, 0.1, 0.05); setTimeout(() => playTone(1319, 0.1, 0.05), 80); setTimeout(() => playTone(1568, 0.15, 0.05), 160); }
function playErrorSound()   { playTone(330, 0.2, 0.06); setTimeout(() => playTone(262, 0.25, 0.06), 150); }

// ─── Timer ────────────────────────────────────────────────────────

function startTimer() {
  recordStart = Date.now();
  timer.textContent = '0:00';
  timerInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - recordStart) / 1000);
    const mins = Math.floor(elapsed / 60);
    const secs = elapsed % 60;
    timer.textContent = `${mins}:${String(secs).padStart(2, '0')}`;
  }, 250);
}

function stopTimer() {
  if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
}

// ─── State Machine ────────────────────────────────────────────────

function setState(state, extra = {}) {
  // Remove all state classes
  widget.classList.remove('state-listening', 'state-processing', 'state-done', 'state-error');
  dot.classList.remove('processing', 'done', 'error');

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
      text.textContent = 'Processing…';
      stopTimer();
      break;

    case 'done':
      widget.classList.add('visible', 'state-done');
      dot.classList.add('done');
      text.textContent = 'Pasted!';
      stopTimer();
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
      // Reset bars
      bars.forEach(b => { b.style.height = '4px'; });
      break;
  }
}

// ─── Audio Level Visualization ────────────────────────────────────

function updateAudioBars(level) {
  // level is 0..1
  const heights = [
    4 + level * 10,
    4 + level * 16,
    4 + level * 20,
    4 + level * 14,
    4 + level * 8,
  ];
  // Add some randomness for organic feel
  bars.forEach((bar, i) => {
    const jitter = 1 + Math.random() * 3 * level;
    bar.style.height = `${Math.min(heights[i] + jitter, 22)}px`;
  });
}

// ─── IPC Listeners ────────────────────────────────────────────────

window.scriber.onStateChange((data) => {
  setState(data.state, data);
});

window.scriber.onAudioLevel((data) => {
  updateAudioBars(data.level);
});

// Start hidden
setState('idle');
