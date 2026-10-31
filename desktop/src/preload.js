'use strict';
const { contextBridge, ipcRenderer } = require('electron');

// The setup screen gets a small, explicit API; no Node, no file system. The app itself (the same window shows it)
// sees only `installed` and `addSets`: the Models page offers to add a set the first run left out.
contextBridge.exposeInMainWorld('remiqoraVideo', {
  context: () => ipcRenderer.invoke('setup:context'),
  checks: () => ipcRenderer.invoke('setup:checks'),
  setSets: (sets) => ipcRenderer.invoke('setup:set-sets', sets),
  setLang: (lang) => ipcRenderer.invoke('setup:set-lang', lang),
  chooseFolder: (kind) => ipcRenderer.invoke('setup:choose-folder', kind),
  setFolder: (kind, dir) => ipcRenderer.invoke('setup:set-folder', kind, dir),
  dropFind: (dir) => ipcRenderer.invoke('setup:drop-find', dir),
  checkHfToken: (token) => ipcRenderer.invoke('setup:hf-check', token),
  start: () => ipcRenderer.invoke('setup:start'),
  pause: () => ipcRenderer.invoke('setup:pause'),
  launch: () => ipcRenderer.invoke('setup:launch'),
  openExternal: (key) => ipcRenderer.invoke('setup:open-external', key),
  openLogs: () => ipcRenderer.invoke('setup:open-logs'),
  showData: () => ipcRenderer.invoke('setup:show-data'),
  installed: () => ipcRenderer.invoke('app:installed'),
  addSets: () => ipcRenderer.invoke('app:add-sets'),
  onEvent: (callback) => {
    const handler = (_event, payload) => callback(payload);
    ipcRenderer.on('setup:event', handler);
    return () => ipcRenderer.removeListener('setup:event', handler);
  },
});
