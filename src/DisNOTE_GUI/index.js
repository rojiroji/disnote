// アプリケーション作成用のモジュールを読み込み
const { ipcMain, app, BrowserWindow, shell } = require("electron");
const localShortcut = require("electron-localshortcut");

const path = require("path");
const fs = require('fs');
const { spawn } = require('child_process');
const encoding = require('encoding-japanese');


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
const template_file_progress = fs.readFileSync(path.join(__dirname, 'template_file_progress.html'), 'utf8');

// リリース版or開発環境で異なる設定を読み込み
const env = JSON.parse(fs.readFileSync(path.join(__dirname, 'env.json'), 'utf8'));
console.log("env. " + JSON.stringify(env));

// ユーザーごとの設定を読み込み
const configFilePath = path.join(__dirname, 'config.json');
let config = {};
try {
  config = JSON.parse(fs.readFileSync(configFilePath, 'utf8'));
} catch (err) {
  console.log(err); // ファイルがない場合は何もしない
  config.width = 1200;
  config.height = 800;
  config.maximize = false;
  config.x = undefined;
  config.y = undefined;
  config.isusewitai = false;
  config.witaitoken = "";
  config.project_sort_key = "id";
  config.project_sort_order = "desc"; // ソート順のデフォルトは降順
}

// メインウィンドウ
var mainWindow;

const createWindow = () => {
  // メインウィンドウを作成します
  mainWindow = new BrowserWindow({
    width: config.width,
    height: config.height,
    x: config.x,
    y: config.y,
    webPreferences: {
      // プリロードスクリプトは、レンダラープロセスが読み込まれる前に実行され、
      // レンダラーのグローバル（window や document など）と Node.js 環境の両方にアクセスできます。
      preload: path.join(__dirname, "js/preload.js"),
    },
    icon: __dirname + '/favicon.ico'
  });
  mainWindow.setMenuBarVisibility(false); // メニューバー非表示
  if (config.maximize) {
    mainWindow.maximize(); // 最大化
  }

  registShortcut()

  // メインウィンドウに表示するURLを指定します
  // （今回はmain.jsと同じディレクトリのindex.html）
  mainWindow.loadFile("index.html");

  if (env.opendevtools == "true") {
    // デベロッパーツールの起動
    mainWindow.webContents.openDevTools();
  }
  // メインウィンドウが閉じるときの処理
  mainWindow.on("close", () => {
    // コンフィグ保存
    config.width = mainWindow.getBounds().width;
    config.height = mainWindow.getBounds().height;
    config.y = mainWindow.getBounds().y;
    config.x = mainWindow.getBounds().x;
    config.maximize = mainWindow.isMaximized();

    fs.writeFile(configFilePath, JSON.stringify(config, null, 4), (err) => {
      if (err) {
        console.error(err);
        return;
      }
    });

    // 子プロセスを落とす
    killChildProcess();
  });

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
    project.enabled = true; // 無効化していたプロジェクトを復活させる
  }

  // プロジェクトリスト出力
  writeProjects();

})

/**
 * プロジェクトリスト出力
 */
function writeProjects() {
  if (projects.length > 0) {
    fs.writeFile(projectsFilePath, JSON.stringify(projects, null, 4), (err) => {
      if (err) {
        console.error(err);
        mainWindow.webContents.send('output-error', err.message);
        return;
      }

      mainWindow.webContents.send('output-success', projectsFilePath);
    });
  }
}

/**
 * プロジェクトリストをtableにして返す
 * js/main.js        document.addEventListener('drop' ... , document.addEventListener('load' ...
 * -> js/preload.js  getProjectsTable
 * -> index.js       getProjectsTable
* @returns 
 */
ipcMain.handle('getProjectsTable', (event) => {
  // 選択したソートキーでソート
  projects.sort((a, b) => {
    if (!config.project_sort_key) {
      config.project_sort_key = "id";
    }
    const valA = a[config.project_sort_key];
    const valB = b[config.project_sort_key];
    let ret = 0;

    if (valA < valB) {
      ret = -1;
    }
    if (valA > valB) {
      ret = 1;
    }
    if (ret) {
      return ret * (config.project_sort_order == "desc" ? 1 : -1);
    }
    return (a["id"] - b["id"]) * (config.project_sort_order == "desc" ? 1 : -1);
  });

  let tableHtml = '<table class="projects">';

  // ヘッダ(ソート順など)
  tableHtml += template_projects_header;

  // テーブルボディを作成
  for (const item of projects) {
    if (!item.enabled) {
      continue; // 無効化したプロジェクトは表示しない
    }
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
      .replaceAll("${item.recognized_date}", item.recognized_time.substring(0, 10)) // 日付のところ(yyyy/MM/dd)だけ切り取る
      .replaceAll("${item.modified_date}", item.modified_time.substring(0, 10))
      .replaceAll("${item.access_date}", item.access_time.substring(0, 10))
      .replaceAll("${item.id}", item.id)
      .replaceAll("${name_e}", name_e)
      .replaceAll("${name_o}", name_o)
      .replaceAll("${item.edit_disabled}", (item.recognized_time.length > 10) ? "" : "disabled");
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
    recognized_time: "-",
    modified_time: "-",
    access_time: "-",

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
 * プロジェクトの音声認識ボタンを押下 → 音声認識開始
 * js/main.js        reloadProjects -> editbutton.addEventListener('click',' ...
 * -> js/preload.js  recognizeProject
 * -> index.js       recognizeProject
 * @returns 
 */
let childProcess = null;
ipcMain.handle('recognizeProject', (event, projectId, isusewitai, witaitoken) => {
  console.log("recognizeProject:" + projectId);

  // projectIdでproject取得
  const project = projects.find((project) => project.id == projectId);

  // projectに登録されたfullpathを取得
  let args = ["--files"].concat(project.files.map(file => {
    return file.fullpath;
  }))

  // wit.aiのtoken(画面で指定していない場合は"none"を明示)
  args.push("--witaitoken", isusewitai ? witaitoken : "none");
  config.isusewitai = isusewitai;
  config.witaitoken = witaitoken;

  childProcess = spawn(env.engine, args, { encoding: env.encoding }); // エンジンのサブプロセスを起動
  let recfiles = [];
  let multitracks = false;

  // サブプロセスの標準出力読み込み
  let stdoutBuffer = '';
  childProcess.stdout.on('data', function (data) {
    var lines;
    ({ lines, stdoutBuffer } = convertOutToLines(data, stdoutBuffer));
    for (var i = 0; i < lines.length - 1; i++) {
      var line = lines[i];
      const outputLine = line.trim();
      //console.log(outputLine);

      const GUIMARK = "[PROGRESS]"; // GUI向けに出力されたログ
      const guilogpos = outputLine.indexOf(GUIMARK);
      if (guilogpos > -1) {
        let logbody = outputLine.slice(guilogpos + GUIMARK.length)// ログ本体を抽出
        updateProgress(project, logbody, recfiles, multitracks);
        //mainWindow.webContents.send('engineStdout', logbody); // engineStdout(main.js)に渡す
      }
    }
  });

  // サブプロセスの標準エラー出力読み込み
  let stderrBuffer = '';
  childProcess.stderr.on('data', function (data) {
    var lines;
    ({ lines, stdErrBuffer: stderrBuffer } = convertOutToLines(data, stderrBuffer));
    for (var i = 0; i < lines.length - 1; i++) {
      var line = lines[i];
      const outputLine = line.trim();
      //console.log(outputLine);
      mainWindow.webContents.send('engineStderr', outputLine); // engineStderr(main.js)に渡す
    }
  });

  childProcess.on('close', (code) => {
    console.log(`Child process exited with code ${code} / projectId = ${projectId}`);

    if (code == 0) { // 成功時
      // 更新したのでプロジェクトリスト出力
      writeProjects();
    }

    mainWindow.webContents.send('engineClose', code); // engineClose(main.js)に渡す
    //childProcess = null; // 非同期でおかしくなるかもしれないのでnullにしない
  });

  /**
   * 標準出力、標準エラー出力を1行ごとの配列にして返す（改行前の文字列は保持して次回読み込み時に連結する）
   * @param {*} data 標準出力あるいは標準エラー出力
   * @param {*} buffer 前回の出力の最後の部分
   * @returns 1行ごとの配列、今回の出力の最後の行（改行で終わっていた場合は空文字列）
   */
  function convertOutToLines(data, buffer) {
    data = encoding.convert(data, {
      from: env.encoding,
      to: 'UNICODE',
      type: 'string',
    });
    var lines = (buffer + data).replaceAll("\r\n", "\n").split("\n");
    if (data[data.length - 1] != '\n') {
      buffer = lines.pop();
    } else {
      buffer = '';
    }
    return { lines, buffer };
  }

  /**
   * エンジンから受け取ったログを解析し、画面に音声ファイルごとの進捗として表示する
   * @param {*} logbody ログ(json形式であること)
   * @param {*} recfiles  音声ファイルの情報の一覧
   */
  function updateProgress(project, logbody, recfiles, multitracks) {
    console.log("updateProgress:" + logbody);
    const info = JSON.parse(logbody); // TODO parseできなかった場合
    switch (info.stage) {
      case "setAudioFileInfo": // 音声ファイル登録
        recfiles.push(info);
        if (info.trackindex > 0) {
          multitracks = true;
        }
        break;
      case "checkedAudioFiles": // 音声ファイル登録完了 → 画面にtableを出す
        let tableHtml = '<table class="progress"><tr><th colspan="2">ファイル</th><th colspan="2">進捗</th></tr>';
        for (const recfile of recfiles) {
          tableHtml += template_file_progress
            .replaceAll("${orgfile}", recfile.orgfile)
            .replaceAll("${track}", multitracks ? "track" + (recfile.trackindex + 1) : "")
            .replaceAll("${index}", recfile.index);
        }
        tableHtml += '<tr class="main"><td colspan="3">最終処理</td>' +
          '<td class="progress"><div class="progress-container"><progress id="progress_last" value="0" max="100"></progress>' +
          '<div class="custom-text" id="percent_last">0.0%</div></div></td>';

        tableHtml += '</table>';
        mainWindow.webContents.send('checkedAudioFiles', tableHtml);
        mainWindow.webContents.send('updateCuiProgress', "音声認識処理中"); 21
        mainWindow.webContents.send('updateLastProgress', 0);
        break;
      case "merge_mp3": // 音声マージ
        mainWindow.webContents.send('updateCuiProgress', "音声ファイルマージ中");
        mainWindow.webContents.send('updateLastProgress', 50);
        break;
      case "merge_end": // 処理終了
        mainWindow.webContents.send('updateCuiProgress', "音声認識完了");
        mainWindow.webContents.send('updateLastProgress', 100);

        project.result = info.result;
        project.recognized_time = timeToLocalString(new Date()); // 認識結果登録
        mainWindow.webContents.send('rewriteProjectInfo', project);
        break;
      default: // その他の進捗
        if (typeof info.index !== 'undefined') { // 特定の音声ファイルの進捗
          const index = parseInt(info.index);
          mainWindow.webContents.send('updateAudioFileProgress', info);
        }

        return;
    }
  }
});

/**
 * 音声認識エンジンキャンセル
 * js/main.js        reloadProjects -> 音声認識のdialogのキャンセルボタン：click: function () 
 * -> js/preload.js  cancelRecognize
 * -> index.js       cancelRecognize
*/
ipcMain.handle('cancelRecognize', (event) => {
  console.log("cancelRecognize");
  killChildProcess();
});

/**
 * 子プロセスを落とす
 */
function killChildProcess() {
  if (childProcess != null) { // 既に落ちたプロセスに再度killしても副作用はないようなので状態は見ない
    childProcess.kill('SIGTERM');  // TODO:SIGTERMで終了して、上手く落ちなかったらSIGKILLで落とす
  }
}

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
 * プロジェクト無効化（画面では"削除"という表現をしているが、実際はenabledフラグを落としているだけ）
 * js/main.js        document.querySelector('#disable_project').addEventListener('click',
 * -> js/preload.js  disableProject
 * -> index.js       disableProject
* @returns 
 */

ipcMain.handle('disableProject', (event, projectId) => {
  console.log("disableProject:" + projectId);

  // projectIdでproject取得
  const project = projects.find((project) => project.id == projectId);
  project.enabled = false; // 無効化

  // プロジェクトリスト出力
  writeProjects();
});

/**
 * コンフィグの情報を取得
 * js/main.js        window.addEventListener('load', async (event) =>
 * -> js/preload.js  getConfig
 * -> index.js       getConfig
* @returns 
 */
ipcMain.handle('getConfig', (event) => {
  console.log("getConfig:");

  return config
});

/**
 * コンフィグの情報を更新
 * js/main.js        reloadProjects =>
 * -> js/preload.js  updateConfig
 * -> index.js       updateConfig
* @returns 
 */
ipcMain.handle('updateConfig', (event, project_sort_key, switch_project_sort_order) => {
  console.log("updateConfig:");

  config.project_sort_key = project_sort_key;
  if (switch_project_sort_order) {
    config.project_sort_order = (config.project_sort_order == "desc") ? "asc" : "desc";
  }
  return config
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

