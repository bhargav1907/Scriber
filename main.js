/**
 * Scriber — Electron Main Process
 *
 * Responsibilities:
 *  - Spawn the Python backend as a child process
 *  - Connect to the backend via WebSocket
 *  - Register global hotkey (Option+Space)
 *  - Manage the tray icon, floating widget, and main window
 *  - Relay state/level updates to renderers via IPC
 */

const {
  app,
  BrowserWindow,
  Tray,
  Menu,
  globalShortcut,
  nativeImage,
  ipcMain,
  screen,
  shell,
} = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const zlib = require('zlib');
const WebSocket = require('ws');
const http = require('http');

// ─── Globals ─────────────────────────────────────────────────────────
let tray = null;
let mainWindow = null;
let widgetWindow = null;
let pythonProcess = null;
let ws = null;
let currentState = 'idle';
let reconnectTimer = null;

const BACKEND_PORT = 58932;
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;
const WS_URL = `ws://127.0.0.1:${BACKEND_PORT}/ws`;

// ─── Single Instance Guard ───────────────────────────────────────────
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  console.log('[Scriber] Another instance is already running. Exiting.');
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

// ─── PNG Icon Generator ──────────────────────────────────────────────
// Creates simple tray icons programmatically (no external files needed)

function createPNGBuffer(width, height, drawFn) {
  const pixels = Buffer.alloc(width * height * 4, 0);
  drawFn(pixels, width, height);

  // Build raw scanlines with filter byte
  const rawBuf = Buffer.alloc(height * (1 + width * 4));
  for (let y = 0; y < height; y++) {
    rawBuf[y * (1 + width * 4)] = 0; // filter: None
    for (let x = 0; x < width; x++) {
      const src = (y * width + x) * 4;
      const dst = y * (1 + width * 4) + 1 + x * 4;
      rawBuf[dst] = pixels[src];
      rawBuf[dst + 1] = pixels[src + 1];
      rawBuf[dst + 2] = pixels[src + 2];
      rawBuf[dst + 3] = pixels[src + 3];
    }
  }

  const compressed = zlib.deflateSync(rawBuf);

  function chunk(type, data) {
    const typeBuf = Buffer.from(type);
    const len = Buffer.alloc(4);
    len.writeUInt32BE(data.length);
    const crcInput = Buffer.concat([typeBuf, data]);
    const crcVal = crc32(crcInput);
    const crcBuf = Buffer.alloc(4);
    crcBuf.writeUInt32BE(crcVal >>> 0);
    return Buffer.concat([len, typeBuf, data, crcBuf]);
  }

  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; ihdr[9] = 6; // 8-bit RGBA
  return Buffer.concat([sig, chunk('IHDR', ihdr), chunk('IDAT', compressed), chunk('IEND', Buffer.alloc(0))]);
}

function crc32(buf) {
  let crc = 0xFFFFFFFF;
  for (let i = 0; i < buf.length; i++) {
    crc ^= buf[i];
    for (let j = 0; j < 8; j++) {
      crc = (crc >>> 1) ^ (crc & 1 ? 0xEDB88320 : 0);
    }
  }
  return (crc ^ 0xFFFFFFFF) >>> 0;
}

function setPixel(buf, w, x, y, r, g, b, a = 255) {
  if (x < 0 || x >= w || y < 0 || y >= w) return;
  const off = (y * w + x) * 4;
  buf[off] = r; buf[off + 1] = g; buf[off + 2] = b; buf[off + 3] = a;
}

function makeTrayIcon(state) {
  const s = 22;
  return createPNGBuffer(s, s, (px, w, h) => {
    // Draw 3-bar waveform icon
    const color = state === 'listening' ? [239, 68, 68] : [0, 0, 0]; // red when recording, black for template
    const alpha = 255;
    const cx = Math.floor(w / 2);

    // Center bar (tallest)
    for (let y = 4; y <= 17; y++) { setPixel(px, w, cx, y, ...color, alpha); setPixel(px, w, cx + 1, y, ...color, alpha); }
    // Left bar
    for (let y = 7; y <= 14; y++) { setPixel(px, w, cx - 4, y, ...color, alpha); setPixel(px, w, cx - 3, y, ...color, alpha); }
    // Right bar
    for (let y = 7; y <= 14; y++) { setPixel(px, w, cx + 4, y, ...color, alpha); setPixel(px, w, cx + 5, y, ...color, alpha); }
    // Far left bar
    for (let y = 9; y <= 12; y++) { setPixel(px, w, cx - 7, y, ...color, alpha); setPixel(px, w, cx - 6, y, ...color, alpha); }
    // Far right bar
    for (let y = 9; y <= 12; y++) { setPixel(px, w, cx + 7, y, ...color, alpha); setPixel(px, w, cx + 8, y, ...color, alpha); }
  });
}

function updateTrayIcon(state) {
  if (!tray) return;
  const buf = makeTrayIcon(state);
  const img = nativeImage.createFromBuffer(buf, { width: 22, height: 22 });
  if (state !== 'listening') img.setTemplateImage(true);
  tray.setImage(img);
}

// ─── Window Creation ─────────────────────────────────────────────────

function secureWebContents(win) {
  if (!win || !win.webContents) return;
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https:') || url.startsWith('http:')) {
      shell.openExternal(url);
    }
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith('file://')) {
      event.preventDefault();
      if (url.startsWith('https:') || url.startsWith('http:')) {
        shell.openExternal(url);
      }
    }
  });
}

function createWidgetWindow() {
  const display = screen.getPrimaryDisplay();
  const { width: screenW } = display.workAreaSize;

  widgetWindow = new BrowserWindow({
    width: 380,
    height: 56,
    x: Math.round(screenW / 2 - 190),
    y: 16,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    hasShadow: false,
    focusable: false,
    show: false,
    hiddenInMissionControl: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  widgetWindow.loadFile(path.join(__dirname, 'src', 'widget.html'));
  widgetWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  widgetWindow.setAlwaysOnTop(true, 'screen-saver', 1);
  secureWebContents(widgetWindow);
}

function showWidget() {
  if (!widgetWindow || widgetWindow.isDestroyed()) return;
  try {
    const cursor = screen.getCursorScreenPoint();
    const activeDisplay = screen.getDisplayNearestPoint(cursor);
    const { x: dispX, y: dispY, width: dispW } = activeDisplay.bounds;
    const widgetW = 380;
    const targetX = Math.round(dispX + (dispW - widgetW) / 2);
    const targetY = dispY + 16;

    widgetWindow.setPosition(targetX, targetY, false);
    widgetWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
    widgetWindow.setAlwaysOnTop(true, 'screen-saver', 1);
    widgetWindow.showInactive();
    widgetWindow.moveTop();
  } catch (err) {
    console.error('[Scriber] Failed to show widget:', err);
  }
}

function hideWidget() {
  if (!widgetWindow || widgetWindow.isDestroyed()) return;
  try {
    widgetWindow.hide();
  } catch {}
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 940,
    height: 700,
    minWidth: 720,
    minHeight: 520,
    show: false,
    titleBarStyle: 'hiddenInset',
    vibrancy: 'under-window',
    visualEffectState: 'active',
    trafficLightPosition: { x: 18, y: 18 },
    backgroundColor: '#0a0a14',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, 'src', 'index.html'));
  secureWebContents(mainWindow);

  mainWindow.on('show', () => {
    ipcMain.emit('fetch-audio-devices');
    ipcMain.emit('fetch-history');
    ipcMain.emit('request-health');
  });

  mainWindow.on('focus', () => {
    ipcMain.emit('fetch-audio-devices');
  });

  mainWindow.on('close', (e) => {
    if (!app.isQuitting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });
}

// ─── Tray ────────────────────────────────────────────────────────────

function createTray() {
  const buf = makeTrayIcon('idle');
  const img = nativeImage.createFromBuffer(buf, { width: 22, height: 22 });
  img.setTemplateImage(true);
  tray = new Tray(img);

  const contextMenu = Menu.buildFromTemplate([
    { label: 'Scriber', enabled: false },
    { type: 'separator' },
    { label: 'Toggle Recording  (Fn / ⌥ Space)', click: () => sendToggle() },
    { label: 'Open Scriber', click: () => { mainWindow.show(); mainWindow.focus(); } },
    { type: 'separator' },
    { label: 'Quit Scriber', click: () => { app.isQuitting = true; app.quit(); } },
  ]);

  tray.setToolTip('Scriber — Voice to Text');
  tray.setContextMenu(contextMenu);
  tray.on('click', () => { mainWindow.show(); mainWindow.focus(); });
}

// ─── Python Backend ──────────────────────────────────────────────────

function spawnPythonBackend() {
  const venvPython = path.join(__dirname, 'backend', 'venv', 'bin', 'python3');
  const mainPy = path.join(__dirname, 'backend', 'main.py');

  pythonProcess = spawn(venvPython, [mainPy], {
    cwd: path.join(__dirname, 'backend'),
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env },
  });

  pythonProcess.stdout.on('data', (d) => process.stdout.write(`[py] ${d}`));
  pythonProcess.stderr.on('data', (d) => process.stderr.write(`[py] ${d}`));
  pythonProcess.on('exit', (code) => {
    console.log(`[Scriber] Python backend exited with code ${code}`);
    if (!app.isQuitting) {
      // Auto-restart after a brief delay
      setTimeout(spawnPythonBackend, 2000);
    }
  });
}

// ─── WebSocket Connection ────────────────────────────────────────────

function connectWebSocket() {
  if (ws) {
    try { ws.close(); } catch {}
  }

  ws = new WebSocket(WS_URL);

  ws.on('open', () => {
    console.log('[Scriber] WebSocket connected to backend');
    if (reconnectTimer) { clearInterval(reconnectTimer); reconnectTimer = null; }
  });

  ws.on('message', (raw) => {
    try {
      const msg = JSON.parse(raw.toString());
      handleBackendMessage(msg);
    } catch {}
  });

  ws.on('close', () => {
    console.log('[Scriber] WebSocket disconnected, retrying in 2s…');
    scheduleReconnect();
  });

  ws.on('error', () => {
    scheduleReconnect();
  });
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setInterval(() => {
    if (!ws || ws.readyState === WebSocket.CLOSED) {
      connectWebSocket();
    }
  }, 2000);
}

function sendWS(data) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(data));
  }
}

function sendToggle() {
  sendWS({ type: 'toggle_recording' });
}

// ─── Handle Messages from Backend ────────────────────────────────────

function handleBackendMessage(msg) {
  switch (msg.type) {
    case 'init':
    case 'state':
      currentState = msg.state;
      updateTrayIcon(msg.state);

      // Show/hide widget
      if (msg.state === 'listening' || msg.state === 'processing' || msg.state === 'done') {
        showWidget();
      } else if (msg.state === 'idle') {
        setTimeout(() => hideWidget(), 400);
      } else if (msg.state === 'error') {
        showWidget();
        setTimeout(() => hideWidget(), 3000);
      }

      // Relay to renderers
      sendToAllRenderers('state-change', msg);
      if (msg.audio_devices) {
        sendToAllRenderers('audio-devices-update', msg.audio_devices);
      }
      if (msg.stats) {
        sendToAllRenderers('stats-update', msg.stats);
      }
      if (msg.state === 'done') {
        ipcMain.emit('fetch-stats');
      }
      break;

    case 'audio_level':
      sendToAllRenderers('audio-level', msg);
      break;

    case 'duration':
      sendToAllRenderers('duration', msg);
      break;

    case 'config':
      sendToAllRenderers('config-change', msg);
      break;

    case 'audio_devices_update':
      if (msg.audio_devices) {
        sendToAllRenderers('audio-devices-update', msg.audio_devices);
      }
      break;

    default:
      break;
  }
}

function sendToAllRenderers(channel, data) {
  [mainWindow, widgetWindow].forEach((win) => {
    if (win && !win.isDestroyed()) {
      try { win.webContents.send(channel, data); } catch {}
    }
  });
}

// ─── IPC Handlers (Renderer → Main) ─────────────────────────────────

function setupIPC() {
  ipcMain.on('toggle-recording', () => sendToggle());
  ipcMain.on('request-duration', () => sendWS({ type: 'get_duration' }));

  ipcMain.on('show-main-window', () => {
    if (mainWindow) { mainWindow.show(); mainWindow.focus(); }
  });

  // REST-backed actions (history, stats, config) with 3s timeout to protect UI thread
  ipcMain.on('fetch-history', async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/history`, { signal: AbortSignal.timeout(3000) });
      const data = await res.json();
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('history-update', data);
      }
    } catch {}
    ipcMain.emit('fetch-stats');
  });

  ipcMain.on('fetch-stats', async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/stats`, { signal: AbortSignal.timeout(3000) });
      const data = await res.json();
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('stats-update', data);
      }
    } catch {}
  });

  ipcMain.on('fetch-audio-devices', async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/audio-devices`, { signal: AbortSignal.timeout(3000) });
      const data = await res.json();
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('audio-devices-update', data);
      }
    } catch {}
  });

  ipcMain.on('delete-entry', async (_e, id) => {
    try {
      await fetch(`${BACKEND_URL}/api/history/${id}`, { method: 'DELETE', signal: AbortSignal.timeout(3000) });
      ipcMain.emit('fetch-history');
      ipcMain.emit('fetch-stats');
    } catch {}
  });

  ipcMain.on('clear-history', async () => {
    try {
      await fetch(`${BACKEND_URL}/api/history`, { method: 'DELETE', signal: AbortSignal.timeout(3000) });
      ipcMain.emit('fetch-history');
      ipcMain.emit('fetch-stats');
    } catch {}
  });

  ipcMain.on('update-config', async (_e, cfg) => {
    try {
      await fetch(`${BACKEND_URL}/api/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg),
        signal: AbortSignal.timeout(3000),
      });
    } catch {}
  });

  ipcMain.on('request-health', async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/health`, { signal: AbortSignal.timeout(3000) });
      const data = await res.json();
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('health-update', data);
      }
    } catch {}
  });
}

function stopBackendProcess() {
  if (pythonProcess) {
    const proc = pythonProcess;
    pythonProcess = null;
    try {
      proc.kill('SIGTERM');
    } catch {}
    setTimeout(() => {
      try {
        if (!proc.killed) proc.kill('SIGKILL');
      } catch {}
    }, 1200);
  }
}

// ─── App Lifecycle ───────────────────────────────────────────────────

app.whenReady().then(() => {
  // Hide dock icon — we're a menu-bar app
  app.dock?.hide();

  createTray();
  createWidgetWindow();
  createMainWindow();
  setupIPC();

  // Register global hotkey: Option+Space (⌥ Space — standard dictation hotkey, no conflicts)
  // Note: Hardware Fn key is also monitored directly by the Python backend via Quartz!
  globalShortcut.register('Alt+Space', () => {
    sendToggle();
  });

  // Spawn Python backend
  spawnPythonBackend();

  // Connect to backend WebSocket after a short delay (let Python start)
  setTimeout(connectWebSocket, 3000);
  // Start polling for connection if first attempt fails
  scheduleReconnect();
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
  stopBackendProcess();
  if (ws) {
    try { ws.close(); } catch {}
  }
});

app.on('before-quit', () => {
  app.isQuitting = true;
  stopBackendProcess();
});

process.on('SIGINT', () => {
  stopBackendProcess();
  process.exit(0);
});

process.on('SIGTERM', () => {
  stopBackendProcess();
  process.exit(0);
});

app.on('window-all-closed', (e) => {
  // Don't quit on window close — keep running in tray
  e.preventDefault?.();
});

app.on('activate', () => {
  if (mainWindow) {
    mainWindow.show();
    mainWindow.focus();
  }
});
