const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld(
  'api', {
  apiLoadFile: (path) => ipcRenderer.invoke("apiLoadFile", path) // htmlファイルとjsonファイル読み込み
    .then(result => result)
    .catch(err => console.log(err)),
  dropMediaFiles: (filePaths) => ipcRenderer.invoke("dropMediaFiles", filePaths) // 音声ファイル読み込み
    .then(result => result)
    .catch(err => console.log(err)),
  getProjectsTable: () => ipcRenderer.invoke("getProjectsTable") // プロジェクトリストのtableを取得
    .then(result => result)
    .catch(err => console.log(err)),
  editProject: (projectId,witaitoken) => ipcRenderer.invoke("editProject", projectId, witaitoken) // プロジェクト編集
    .then(result => result)
    .catch(err => console.log(err)),
  openProjectFolder: (projectId) => ipcRenderer.invoke("openProjectFolder", projectId) // プロジェクトのファイルが置いてあるフォルダを開く
    .then(result => result)
    .catch(err => console.log(err)),
  cancelRecognize: () => ipcRenderer.invoke("cancelRecognize") // 音声認識エンジンキャンセル
    .then(result => result)
    .catch(err => console.log(err)),
  apiSaveEditFile: (path) => ipcRenderer.invoke("apiSaveEditFile", path) // 保存
    .then(result => result)
    .catch(err => console.log(err)),
  on: (channel, callback) => {
    ipcRenderer.on(channel, (_event, arg) => callback(arg))
  },
}
);

