const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld(
  'api', {
  editProject: (projectId) => ipcRenderer.invoke("editProject", projectId) // htmlファイルとjsonファイル読み込み
    .then(result => result)
    .catch(err => console.log(err)),
  getConfig: () => ipcRenderer.invoke("getConfig") // コンフィグを取得
    .then(result => result)
    .catch(err => console.log(err)),
  updateProjectSortConfig: (project_sort_key, switch_project_sort_order) => ipcRenderer.invoke("updateProjectSortConfig", project_sort_key, switch_project_sort_order) // コンフィグを更新(プロジェクトのソート設定)
    .then(result => result)
    .catch(err => console.log(err)),
  updateConfig: (param_config) => ipcRenderer.invoke("updateConfig", param_config) // コンフィグを更新
    .then(result => result)
    .catch(err => console.log(err)),
  dropMediaFiles: (filePaths) => ipcRenderer.invoke("dropMediaFiles", filePaths) // 音声ファイル読み込み
    .then(result => result)
    .catch(err => console.log(err)),
  getProjectsTable: () => ipcRenderer.invoke("getProjectsTable") // プロジェクトリストのtableを取得
    .then(result => result)
    .catch(err => console.log(err)),
  recognizeProject: (projectId, isusewitai, witaitoken, whispermodel) => ipcRenderer.invoke("recognizeProject", projectId, isusewitai, witaitoken, whispermodel) // 音声認識開始
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
  apiSaveYmm4Project: (itemArray, mixedMediafile, mixedMediaIsMovie, // YMM4プロジェクトを保存
    execYmm4, openYmm4projectfolder, mixedMediafileDuration) =>
    ipcRenderer.invoke("apiSaveYmm4Project", itemArray, mixedMediafile, mixedMediaIsMovie,
      execYmm4, openYmm4projectfolder, mixedMediafileDuration)
      .then(result => result)
      .catch(err => console.log(err)),
  apiSaveEditFile: (path) => ipcRenderer.invoke("apiSaveEditFile", path) // 保存
    .then(result => result)
    .catch(err => console.log(err)),
  setEdited: (edited) => ipcRenderer.invoke("setEdited", edited) // 編集フラグの上げ下げ
    .then(result => result)
    .catch(err => console.log(err)),
  backToHome: () => ipcRenderer.invoke("backToHome") // ホームに戻る
    .then(result => result)
    .catch(err => console.log(err)),
  on: (channel, callback) => {
    ipcRenderer.on(channel, (_event, arg) => callback(arg))
  },
}
);

