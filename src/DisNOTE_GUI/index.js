// アプリケーション作成用のモジュールを読み込み
const { ipcMain, app, BrowserWindow , shell } = require("electron");
const localShortcut = require("electron-localshortcut");

const path = require("path");
const fs = require('fs');
const { spawn } = require('child_process');


// プロジェクトリスト読み込み
const projectsFilePath = path.join(__dirname, 'projects.json');
let projects = [];
try {
  projects = JSON.parse(fs.readFileSync(projectsFilePath, 'utf8'));
} catch (err) {
  console.log(err); // ファイルがない場合は何もしない
}

// プロジェクト一覧表示のテンプレート読み込み
const template_projects_header = fs.readFileSync(path.join(__dirname, 'template_projects_header.html'), 'utf8');
const template_projects_body = fs.readFileSync(path.join(__dirname, 'template_projects_body.html'), 'utf8');
const template_projects_name = fs.readFileSync(path.join(__dirname, 'template_projects_name.html'), 'utf8');

// リリース版or開発環境で異なる設定を読み込み
const env = JSON.parse(fs.readFileSync("env.json", 'utf8'));
console.log("env. " + JSON.stringify(env));

// エンジンから返ってくる文字列がsjisなのでデコードする
const sjisDecoder = new TextDecoder(env.decoder);

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
  mainWindow.setMenuBarVisibility(false); // メニューバー非表示

  registShortcut()

  // メインウィンドウに表示するURLを指定します
  // （今回はmain.jsと同じディレクトリのindex.html）
  mainWindow.loadFile("index.html");

  if (process.env.ELECTRON_DEBUG == "true") {
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


/**
 * 音声ファイル読み込み開始
 * js/main.js        document.addEventListener('drop' ...
 * -> js/preload.js  dropMediaFiles
 * -> index.js       dropMediaFiles
 */

/**
 * 音声ファイルのドロップ
 */
ipcMain.handle('dropMediaFiles', (event, filePaths) => {
  filePaths.sort(); // 重複判断などをしやすくするためにソート

  // 既存プロジェクトを取得
  let project = getProject(filePaths);

  if (project == null) {// 新規プロジェクトの場合は追加    
    jsonData = createProjectJsonData(filePaths);
    jsonData.id = projects.length;
    projects.push(jsonData);
  } else {
    project.modified_time = new Date().toISOString();
  }

  // プロジェクトリスト出力
  writeProjects();

})

/**
 * プロジェクトリスト出力
 */
function writeProjects() {
  fs.writeFile(projectsFilePath, JSON.stringify(projects, null, 4), (err) => {
    if (err) {
      console.error(err);
      mainWindow.webContents.send('output-error', err.message);
      return;
    }

    mainWindow.webContents.send('output-success', projectsFilePath);
  });
}

/**
 * プロジェクトリストをtableにして返す
 * js/main.js        document.addEventListener('drop' ... , document.addEventListener('load' ...
 * -> js/preload.js  getProjectsTable
 * -> index.js       getProjectsTable
* @returns 
 */
ipcMain.handle('getProjectsTable', (event) => {
  let tableHtml = '<table class="projects">';
  tableHtml += template_projects_header.replaceAll("${order}", "↓");

  // テーブルボディを作成
  for (const item of projects) {
    let name_e = "";//偶数番号の名前
    let name_o = "";//奇数番号の名前
    for (const [index, file] of item.files.entries()) {
      const temp = template_projects_name.replaceAll("${file.name}", file.name);
      if (index % 2 == 0) {
        name_e += temp;
      } else {
        name_o += temp;
      }
    }

    tableHtml += template_projects_body.replaceAll("${item.title}", item.title)
      .replaceAll("${item.recognized_time}", item.recognized_time)
      .replaceAll("${item.modified_time}", item.modified_time)
      .replaceAll("${item.access_time}", item.access_time)
      .replaceAll("${item.id}", item.id)
      .replaceAll("${name_e}", name_e)
      .replaceAll("${name_o}", name_o);
  }

  tableHtml += '</table>';

  return tableHtml;
})

/**
 * 時刻をローカル時間の文字列に変換（ライブラリを使えば簡単だがとりあえず標準で行う）
 * @param {文字列に変換する時刻} time 
 * @returns 
 */
function timeToLocalString(time) {

  const year = time.getFullYear();
  const month = String(time.getMonth() + 1).padStart(2, '0');
  const day = String(time.getDate()).padStart(2, '0');

  const hours = String(time.getHours()).padStart(2, '0');
  const minutes = String(time.getMinutes()).padStart(2, '0');
  const seconds = String(time.getSeconds()).padStart(2, '0');

  return `${year}/${month}/${day} ${hours}:${minutes}`; // :${seconds}
}

/**
 * ドロップしたファイルパスから、プロジェクトのjsonデータを作成する
 * @param {ファイルパス} filePaths 
 * @returns 
 */
function createProjectJsonData(filePaths) {

  const localTimeString = timeToLocalString(new Date());

  const jsonData = {
    id: 'id',
    created_time: localTimeString,
    recognized_time: "未認識",
    modified_time: "未認識",
    access_time: "未認識",

    title: localTimeString,
    status: 'recognizing',
    dir: path.dirname(filePaths[0]),
    result: 'xxx',
    files: [],
    enabled: true
  };

  jsonData.dir = path.dirname(filePaths[0]);
  for (const filePath of filePaths) {
    const file = {
      fullpath: filePath,
      filename: path.basename(filePath),
      name: path.basename(filePath).split('.').slice(0, -1).join('.')
    };
    jsonData.files.push(file);
  }

  return jsonData;
}

/**
 * ドロップしたファイルパスが、既存のプロジェクトと合致しているかを返す
 * @param {ファイルパス} filePaths 
 * @returns 重複しているプロジェクト（存在しなければnull）
 */
function getProject(filePaths) {
  for (const project of projects) {
    if (project.files.length !== filePaths.length) {
      continue;
    }

    let same = true;
    for (let i = 0; i < project.files.length; i++) {
      if (project.files[i].fullpath !== filePaths[i]) {
        same = false;
        continue;
      }
    }
    if (same) {
      return project;
    }

  }

  return null;
}

/**
 * プロジェクトの編集ボタンを押下 → 編集開始。
 * js/main.js        reloadProjects -> editbutton.addEventListener('click',' ...
 * -> js/preload.js  editProject
 * -> index.js       editProject
* @returns 
 */

ipcMain.handle('editProject', (event, projectId) => {
  console.log("editProject:" + projectId);

  // projectIdでproject取得
  const project = projects.find((project) => project.id == projectId);

  // projectに登録されたfullpathを取得
  let args = project.files.map(file => {
    return file.fullpath;
  })
  const childProcess = spawn(env.engine, args); // ここにコマンドと引数を指定

  childProcess.stdout.on('data', (data) => {
    const outputLine = sjisDecoder.decode(data).trim(); // 標準出力を文字列に変換
    console.log(outputLine);

    // TODO 色々処理

    mainWindow.webContents.send('engineStdout', outputLine); // engineStdout(main.js)に渡す
  });

  childProcess.stderr.on('data', (data) => {
    const outputLine = sjisDecoder.decode(data).trim(); // エラー出力を文字列に変換
    console.log(outputLine);
    mainWindow.webContents.send('engineStderr', outputLine); // engineStderr(main.js)に渡す
  });

  childProcess.on('close', (code) => {
    console.log(`Child process exited with code ${code} / projectId = ${projectId}`);

    if (code == 0) { // 成功時
      project.recognized_time = timeToLocalString(new Date());

      // 更新したのでプロジェクトリスト出力
      writeProjects();

      // TODO 再描画
    }

    mainWindow.webContents.send('engineClose', code); // engineClose(main.js)に渡す
  });
});


/**
 * プロジェクトのfolderボタンを押下 → フォルダを開く。
 * js/main.js        reloadProjects -> folderbutton.addEventListener('click',' ...
 * -> js/preload.js  openProjectFolder
 * -> index.js       openProjectFolder
* @returns 
 */

ipcMain.handle('openProjectFolder', (event, projectId) => {
  console.log("openProjectFolder:" + projectId);
  
  // projectIdでproject取得
  const project = projects.find((project) => project.id == projectId);

  // フォルダを開く
  shell.openPath(project.dir);
});

/**
 * htmlファイル読み込み開始
 * js/main.js        document.addEventListener('drop' ...
 * -> js/preload.js  apiLoadFile
 * -> index.js       apiLoadFile
 */
let load_filename = ""  /* 拡張子無しのファイル名 */


/**
 * htmlファイルの読み込み（同時に編集ファイルも読み込む）
 */
ipcMain.handle('apiLoadFile', async (event, arg) => {
  load_filename = arg.split('.')[0]
  mainWindow.loadFile(arg)
    .then(_ => {
      result = readFile(load_filename + ".json")
      /* 同一フォルダに編集済みデータがある場合は読み込む */
      if (result != null) {
        /* BOMが付いている場合は外す */
        if (result.charCodeAt(0) === 0xFEFF) {
          result = result.substr(1);
        }
        mainWindow.webContents.send('apiLoadEditData', result);
      }
    });
})

/**
 * 編集ファイルの読み込み
 * @param {string} path ファイルパス
 * 
 * @return ファイル読み込み結果
 */
function readFile(path) {
  try {
    fs.accessSync(path)
    return fs.readFileSync(path, 'utf8', (err, data) => {
      if (err) {
        throw null
      }
      return data
    });
  } catch (err) {
    console.error('no file:' + path)
    return null
  }
}

/**
 * 編集ファイルの保存
 * index.js          localShortcut.register("Ctrl+S"
 * -> js/preload.js  apiSaveEditFile
 * -> index.js       apiSaveEditFile
 */
ipcMain.handle('apiSaveEditFile', async (event, arg) => {
  let path = load_filename + ".json";
  let data = arg;
  try {
    return fs.writeFile(path, data, (err) => {
      if (err) {
        throw err
      }
      return true
    });
  } catch (err) {
    console.error('save err:' + path)
    console.error(err)
    return false
  }
})

/**
 * ショートカットキーを登録する
 */
function registShortcut() {
  localShortcut.register("Ctrl+S", () => {
    mainWindow.webContents.send('apiSaveEditNotify');
  })
}

