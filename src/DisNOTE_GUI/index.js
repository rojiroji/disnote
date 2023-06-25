// アプリケーション作成用のモジュールを読み込み
const { ipcMain, app, BrowserWindow } = require("electron");
const localShortcut = require("electron-localshortcut");

const path = require("path");
const fs = require('fs');

// メインウィンドウ
var mainWindow;

const createWindow = () => {
  // メインウィンドウを作成します
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    webPreferences: {
      // プリロードスクリプトは、レンダラープロセスが読み込まれる前に実行され、
      // レンダラーのグローバル（window や document など）と Node.js 環境の両方にアクセスできます。
      preload: path.join(__dirname, "js/preload.js"),
    },
  });

  registShortcut()

  // メインウィンドウに表示するURLを指定します
  // （今回はmain.jsと同じディレクトリのindex.html）
  mainWindow.loadFile("index.html");

  if(process.env.ELECTRON_DEBUG == "true"){
    // デベロッパーツールの起動
    mainWindow.webContents.openDevTools();
  }

  // メインウィンドウが閉じられたときの処理
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
};

//  初期化が完了した時の処理
app.whenReady().then(() => {
  createWindow();

  // アプリケーションがアクティブになった時の処理(Macだと、Dockがクリックされた時）
  app.on("activate", () => {
    // メインウィンドウが消えている場合は再度メインウィンドウを作成する
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

// 全てのウィンドウが閉じたときの処理
app.on("window-all-closed", () => {

  // macOSのとき以外はアプリケーションを終了させます
  if (process.platform !== "darwin") {
    app.quit();
  }
});


let load_filename = ""  /* 拡張子無しのファイル名 */
// 非同期メッセージの受信と返信
ipcMain.handle('apiLoadFile', async(event, arg) => {
  load_filename = arg.split('.')[0]
  mainWindow.loadFile(arg)
    .then(_=>{
      result = readFile(load_filename+".json")
      /* 同一フォルダに編集済みデータがある場合は読み込む */
      if (result != null){
        /* BOMが付いている場合は外す */
        if (result.charCodeAt(0) === 0xFEFF) {
          result = result.substr(1);
        }
        mainWindow.webContents.send('apiLoadEditData', result);
      }
    });
})
ipcMain.handle('apiSaveEditFile', async(event, arg) => {
  saveFile(load_filename+".json", arg)
})

/**
 * ファイルを読み込む
 * @param {string} path ファイルパス
 * 
 * @return ファイル読み込み結果
 */
function readFile(path){
  try{
    fs.accessSync(path)
    return fs.readFileSync(path, 'utf8', (err, data) => {
      if (err){
        throw null
      }
      return data
      });
  }catch(err){
      console.error('no file:'+ path)
      return null
  }
}
  
/**
 * ファイルを保存する
 * @param {string} path ファイルパス
 * @param {string} data 保存データ
 * 
 * @return ファイル保存成功可否
 */
function saveFile(path, data){
  try{
      return fs.writeFile(path, data, (err) => {
          if (err){
            throw err
          }
          return true
      });
  }catch(err){
      console.error('save err:'+ path)
      console.error(err)
      return false
  }
}

/**
 * ショートカットキーを登録する
 */
function registShortcut(){
  localShortcut.register("Ctrl+S", () => {
    mainWindow.webContents.send('apiSaveEditNotify'); 
  })
}

