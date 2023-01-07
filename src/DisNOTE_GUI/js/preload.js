const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld(
  'api', {
    apiLoadFile: (path) => ipcRenderer.invoke("apiLoadFile", path)
      .then(result => result)
      .catch(err => console.log(err)),
    apiSaveEditFile: (path) => ipcRenderer.invoke("apiSaveEditFile", path)
        .then(result => result)
        .catch(err => console.log(err)),
    on: (channel, callback) => {
      ipcRenderer.on(channel, (_event, arg)=> callback(arg))
    },
  }
);

