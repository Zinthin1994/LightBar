const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('lightbar', {
  quit: () => ipcRenderer.invoke('quit'),
});
