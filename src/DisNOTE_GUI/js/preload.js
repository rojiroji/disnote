const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld(
  'api', {
  editProject: (projectId) => ipcRenderer.invoke("editProject", projectId) // htmlファイルとjsonファイル読み込み
    .then(result => result)
    .catch(err => console.log(err)),
  getConfig: () => ipcRenderer.invoke("getConfig") // コンフィグを取得
    .then(result => result)
    .catch(err => console.log(err)),
  updateConfig: (project_sort_key, switch_project_sort_order) => ipcRenderer.invoke("updateConfig", project_sort_key, switch_project_sort_order) // コンフィグを更新
    .then(result => result)
    .catch(err => console.log(err)),
  dropMediaFiles: (filePaths) => ipcRenderer.invoke("dropMediaFiles", filePaths) // 音声ファイル読み込み
    .then(result => result)
    .catch(err => console.log(err)),
  getProjectsTable: () => ipcRenderer.invoke("getProjectsTable") // プロジェクトリストのtableを取得
    .then(result => result)
    .catch(err => console.log(err)),
  recognizeProject: (projectId, isusewitai, witaitoken) => ipcRenderer.invoke("recognizeProject", projectId, isusewitai, witaitoken) // 音声認識開始
    .then(result => result)
    .catch(err => console.log(err)),
  openProjectFolder: (projectId) => ipcRenderer.invoke("openProjectFolder", projectId) // プロジェクトのファイルが置いてあるフォルダを開く
    .then(result => result)
    .catch(err => console.log(err)),
  disableProject: (projectId) => ipcRenderer.invoke("disableProject", projectId) // プロジェクト無効化
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

