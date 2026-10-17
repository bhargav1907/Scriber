/**
 * Scriber — Electron Preload Script
 * Exposes a safe IPC bridge between the main process and renderer windows.
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('scriber', {
  // State updates from main → renderer
  onStateChange: (cb) => ipcRenderer.on('state-change', (_e, data) => cb(data)),
  onAudioLevel: (cb) => ipcRenderer.on('audio-level', (_e, data) => cb(data)),
  onConfigChange: (cb) => ipcRenderer.on('config-change', (_e, data) => cb(data)),
  onDuration: (cb) => ipcRenderer.on('duration', (_e, data) => cb(data)),
  onHealthUpdate: (cb) => ipcRenderer.on('health-update', (_e, data) => cb(data)),
  onHistoryUpdate: (cb) => ipcRenderer.on('history-update', (_e, data) => cb(data)),
  onAudioDevicesUpdate: (cb) => ipcRenderer.on('audio-devices-update', (_e, data) => cb(data)),
  onStatsUpdate: (cb) => ipcRenderer.on('stats-update', (_e, data) => cb(data)),

  // Actions: renderer → main
  toggleRecording: () => ipcRenderer.send('toggle-recording'),
  requestDuration: () => ipcRenderer.send('request-duration'),
  fetchHistory: () => ipcRenderer.send('fetch-history'),
  fetchStats: () => ipcRenderer.send('fetch-stats'),
  fetchAudioDevices: () => ipcRenderer.send('fetch-audio-devices'),
  deleteEntry: (id) => ipcRenderer.send('delete-entry', id),
  clearHistory: () => ipcRenderer.send('clear-history'),
  updateConfig: (cfg) => ipcRenderer.send('update-config', cfg),
  showMainWindow: () => ipcRenderer.send('show-main-window'),
  requestHealth: () => ipcRenderer.send('request-health'),
});
