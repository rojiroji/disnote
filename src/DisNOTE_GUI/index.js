// アプリケーション作成用のモジュールを読み込み
const { ipcMain, app, dialog, BrowserWindow, shell } = require("electron");
const localShortcut = require("electron-localshortcut");

const path = require("path");
const fs = require('fs-extra');
const { spawn } = require('child_process');
const encoding = require('encoding-japanese');
const log4js = require('log4js');
const axios = require('axios');

// 現在のバージョン（common.pyでの定義と揃えること）
const currentVersion = "v3.2.1";
let newVersion = null; // 新しいバージョンがあるかどうかチェック（新しくなければnull）

// 編集画面の編集フラグ
let edited = false;

// リリース版or開発環境で異なる設定を読み込み
const env = JSON.parse(fs.readFileSync(path.join(__dirname, 'env.json'), 'utf8'));
console.log("env. " + JSON.stringify(env));

// YMM4プロジェクトのテンプレートファイル（ユーザーが用意）
const ymm4TemplateProjectFile = path.join(env.ymm4templatedir, 'template.ymmp')

// logger設定
log4js.configure({
  appenders: {
    system: { type: 'file', filename: 'log/disnote_gui.log', maxLogSize: 5 * 1024 * 1024, backups: 4 }
  },
  categories: {
    default: { appenders: ['system'], level: env.loglevel },
  }
});
const logger = log4js.getLogger('system');
logger.info("DisNote GUI");

// プロジェクトリスト読み込み
const projectsFilePath = path.join(__dirname, 'projects.json');
let projects = [];
try {
  projects = JSON.parse(fs.readFileSync(projectsFilePath, 'utf8'));
} catch (err) {
  // ファイルがない場合は何もしない
}

// プロジェクト一覧表示のテンプレート読み込み
const template_projects_header = fs.readFileSync(path.join(__dirname, 'template_projects_header.html'), 'utf8');
const template_projects_body = fs.readFileSync(path.join(__dirname, 'template_projects_body.html'), 'utf8');
const template_projects_name = fs.readFileSync(path.join(__dirname, 'template_projects_name.html'), 'utf8');
const template_file_progress = fs.readFileSync(path.join(__dirname, 'template_file_progress.html'), 'utf8');


// ユーザーごとの設定を読み込み
const configFilePath = path.join(__dirname, 'config.json');
let config = {};
try {
  config = JSON.parse(fs.readFileSync(configFilePath, 'utf8'));
} catch (err) {
  //console.log(err); // ファイルがない場合はデフォルト設定
  config.width = 1200;
  config.height = 800;
  config.maximize = false;
  config.x = undefined;
  config.y = undefined;
  config.isusewitai = false;
  config.witaitoken = "";
  config.whispermodel = "none";
  config.project_sort_key = "id";
  config.project_sort_order = "desc"; // ソート順のデフォルトは降順
}

// メインウィンドウ
var mainWindow;
let isClose = false;
let isSaveAndExit = false;
let isSaveAndBackToHome = false;

/**
 * 終了orホームに戻る前の保存確認
 */
function checkSaveDialog(isClosing) {
  const text = isClosing ? "終了" : "ホームに戻る";
  const num = dialog.showMessageBox({
    type: 'warning',
    buttons: [`保存して${text}`, `保存せずに${text}`, 'キャンセル'],
    title: 'DisNote',
    message: "編集中のデータがあります。" + (isClosing ? "終了しますか？" : "ホームに戻りますか？"),
    noLink: true
  }).then((val) => {
    switch (val.response) {
      case 0:// 保存して終了 or ホームに戻る
        if (isClosing) {
          isSaveAndExit = true;
        } else {
          isSaveAndBackToHome = true;
        }
        mainWindow.webContents.send('apiSaveEditNotify'); // 保存通知
        break;
      case 1: // 保存せずに終了 or ホームに戻る
        if (isClosing && mainWindow) {
          isClose = true;
          app.quit();
        } else {
          backToHome();
        }
        break;
    }
  });

}

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

  // メインウィンドウに表示する
  backToHome();

  if (env.opendevtools == "true") {
    // デベロッパーツールの起動
    mainWindow.webContents.openDevTools();
  }
  // メインウィンドウが閉じるときの処理


  mainWindow.on("close", async (e) => {
    if (isClose === false && edited) {
      e.preventDefault();
      checkSaveDialog(true);
      return;
    }

    // ここから終了処理

    // コンフィグ保存
    config.width = mainWindow.getBounds().width;
    config.height = mainWindow.getBounds().height;
    config.y = mainWindow.getBounds().y;
    config.x = mainWindow.getBounds().x;
    config.maximize = mainWindow.isMaximized();

    fs.writeFile(configFilePath, JSON.stringify(config, null, 4), (err) => {
      if (err) {
        logger.error(err);
        return;
      }
    });
    logger.info("DisNote GUI:exit.");

    // 子プロセスを落とす
    killChildProcess();
  });

  // メインウィンドウが閉じられたときの処理
  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  // リンクをクリックするとWebブラウザで開く
  const handleUrlOpen = (e, url) => {
    if (url.match(/^http/)) {
      e.preventDefault()
      shell.openExternal(url)
    }
  }
  mainWindow.webContents.on('will-navigate', handleUrlOpen);
  mainWindow.webContents.on('will-redirect', handleUrlOpen);
  mainWindow.webContents.on('did-navigate', handleUrlOpen);
  mainWindow.webContents.on('new-window', handleUrlOpen);

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

  if (filePaths.length <= 0 || filePaths[0].length <= 0) {
    return null; // 空のファイルだったら何もしない
  }

  // 既存プロジェクトを取得
  let project = getProject(filePaths);
  let newProjectId = null;

  if (project == null) {// 新規プロジェクトの場合は追加    
    jsonData = createProjectJsonData(filePaths);
    jsonData.id = projects.length;
    projects.push(jsonData);
    newProjectId = jsonData.id;
  } else {
    if (!project.enabled) {
      newProjectId = project.id;
    }
    project.modified_time = new Date().toISOString();
    project.enabled = true; // 無効化していたプロジェクトを復活させる
  }

  // プロジェクトリスト出力
  writeProjects();

  return newProjectId;
})

/**
 * プロジェクトリスト出力
 */
function writeProjects() {
  if (projects.length > 0) {
    try {
      fs.writeFileSync(projectsFilePath, JSON.stringify(projects, null, 4));
    } catch (err) {
      logger.error(err);
    }
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
  tableHtml += template_projects_header.replaceAll("${currentVersion}", currentVersion);

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
 * 時刻をローカル時間のyyyyMMddHHmmss形式の文字列に変換（ライブラリを使えば簡単だがとりあえず標準で行う）
 * @param {文字列に変換する時刻} time 
 * @returns 
 */
function timeToLocalyyyyMMddHHmmss(time) {
  const localString = timeToLocalString(time);
  return timeToLocalString(time).replaceAll("/", "").replaceAll(":", "").replaceAll(" ", "");
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
    dir: path.dirname(filePaths[0]),
    result: '',
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
ipcMain.handle('recognizeProject', (event, projectId, isusewitai, witaitoken, whispermodel) => {
  logger.debug("recognizeProject:" + projectId);

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

  // Whisperのモデル
  args.push("--whispermodel", whispermodel);
  config.whispermodel = whispermodel;

  // projectの前回認識設定を記録
  project.recognize_options = { "witai": isusewitai, "whispermodel": whispermodel }
  writeProjects(); // 更新したのでプロジェクトリスト出力

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
      logger.debug(outputLine);

      const GUIMARK = "[PROGRESS]"; // GUI向けに出力されたログ
      const guilogpos = outputLine.indexOf(GUIMARK);
      if (guilogpos > -1) {
        let logbody = outputLine.slice(guilogpos + GUIMARK.length)// ログ本体を抽出
        multitracks = updateProgress(project, logbody, recfiles, multitracks);
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
      logger.debug(outputLine);
      mainWindow.webContents.send('engineStderr', outputLine); // engineStderr(main.js)に渡す
    }
  });

  childProcess.on('close', (code) => {
    logger.info(`Child process exited with code ${code} / projectId = ${projectId}`);
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
   * @return ファイルがマルチトラックかどうか
   */
  function updateProgress(project, logbody, recfiles, multitracks) {
    logger.debug("updateProgress:" + logbody);
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
            .replaceAll("${track}", multitracks ? "track" + (recfile.trackindex) : "")
            .replaceAll("${index}", recfile.index)
            .replaceAll("${disp_google}", true ? "table-row" : "none") // Googleは必ず
            .replaceAll("${disp_witai}", config.isusewitai ? "table-row" : "none") // wit.ai進捗行
            .replaceAll("${disp_whisper}", config.whispermodel != "none" ? "table-row" : "none") // Whisper進捗行
            .replaceAll("${rowspan}", 1 + 1 + (config.isusewitai ? 1 : 0) + ((config.whispermodel != "none") ? 1 : 0))
            ;
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
        writeProjects(); // 更新したのでプロジェクトリスト出力
        mainWindow.webContents.send('rewriteProjectInfo', project);
        break;
      default: // その他の進捗
        if (typeof info.index !== 'undefined') { // 特定の音声ファイルの進捗
          const index = parseInt(info.index);
          mainWindow.webContents.send('updateAudioFileProgress', info);
        }

        return;
    }
    return multitracks;
  }
});

/**
 * 音声認識エンジンキャンセル
 * js/main.js        reloadProjects -> 音声認識のdialogのキャンセルボタン：click: function () 
 * -> js/preload.js  cancelRecognize
 * -> index.js       cancelRecognize
*/
ipcMain.handle('cancelRecognize', (event) => {
  logger.info("cancelRecognize");
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
  logger.debug("openProjectFolder:" + projectId);

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
  logger.debug("disableProject:" + projectId);

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
  logger.debug("getConfig:");

  return config
});

/**
 * コンフィグの情報を更新(プロジェクトのソート設定)
 * js/main.js        reloadProjects =>
 * -> js/preload.js  updateProjectSortConfig
 * -> index.js       updateProjectSortConfig
* @returns 
 */
ipcMain.handle('updateProjectSortConfig', (event, project_sort_key, switch_project_sort_order) => {
  logger.debug("updateProjectSortConfig:");

  config.project_sort_key = project_sort_key;
  if (switch_project_sort_order) {
    config.project_sort_order = (config.project_sort_order == "desc") ? "asc" : "desc";
  }
  return config;
});

/**
 * コンフィグの情報を更新(configをそのまま指定)
 * js/main.js        reloadProjects =>
 * -> js/preload.js  updateConfig
 * -> index.js       updateConfig
* @returns 
 */
ipcMain.handle('updateConfig', (event, param_config) => {
  logger.debug("updateConfig:");

  config = param_config;
  return config;
});

/**
 * YMM4プロジェクトを保存
 * index.html        $("#download_ymm4_project").click 
 * -> js/preload.js  apiSaveYmm4Project
 * -> index.js       apiSaveYmm4Project
 */
ipcMain.handle('apiSaveYmm4Project', async (event, itemArray, mixedMediafile, mixedMediaIsMovie,
  execYmm4, openYmm4projectfolder, mixedMediafileDuration) => {
  let ymm4ProjectPath = changeExtension(edittingProject.result, ".ymmp"); // 保存先
  ymm4ProjectPath = ymm4ProjectPath.replace(".ymmp", "_" + timeToLocalyyyyMMddHHmmss(new Date()) + ".ymmp"); // 日時をファイル名に含める

  try {

    // プロジェクトのテンプレート読み込み（ユーザーに作ってもらう）
    let templateYmm4projectText = fs.readFileSync(ymm4TemplateProjectFile, 'utf8');
    if (templateYmm4projectText.charCodeAt(0) === 0xFEFF) { // BOMを消す
      templateYmm4projectText = templateYmm4projectText.substring(1);
    }
    const templateYmm4Project = JSON.parse(templateYmm4projectText);
    const fps = templateYmm4Project.Timeline.VideoInfo.FPS;


    let items = templateYmm4Project.Timeline.Items;
    let layers = templateYmm4Project.Timeline.LayerSettings.Items;

    // テンプレートファイルのキャラクター定義を読み込み（"DisNOTE自動作業用" のキャラクターが増幅しないように削除しておく）
    const setting_character = JSON.parse(fs.readFileSync(path.join(__dirname, 'ymm4setting', 'character.json'), 'utf8'));
    let characters = templateYmm4Project.Characters.filter((character) => character.Name != setting_character.Name);
    characters.push(setting_character);
    templateYmm4Project.Characters = characters; // "DisNOTE自動作業用" のキャラクターを追加

    // 空いているレイヤーを探す
    let maxLayer = 0;
    Object.values(items).forEach(item => { // アイテムが使っているレイヤーを調べる
      maxLayer = Math.max(item.Layer, maxLayer);
    });
    Object.values(layers).forEach(item => { // 定義済みのレイヤーを調べる
      maxLayer = Math.max(item.Layer, maxLayer);
    });

    // 認識した音声 or 動画をアイテムに追加
    let names = {}; // 名前とlayerの対応
    maxLayer++;
    names[path.basename(mixedMediafile)] = maxLayer;
    const settingMedia = fs.readFileSync(path.join(__dirname, 'ymm4setting', mixedMediaIsMovie ? 'movie.json' : 'audio.json'), 'utf8');
    const mixedMediaLengthFrame = Math.trunc(mixedMediafileDuration * fps);// 秒からフレーム数を計算、整数化
    const newItemStr = settingMedia.replaceAll("$filepath", path.join(edittingProject.dir, mixedMediafile).replaceAll("\\", "\\\\"))
      .replaceAll("$layer", maxLayer).replaceAll("$length", mixedMediaLengthFrame);
    const newItem = JSON.parse(newItemStr);
    items.push(newItem);

    // 出力するセリフをアイテムに追加
    const settingItem = fs.readFileSync(path.join(__dirname, 'ymm4setting', 'item.json'), 'utf8');
    Object.values(itemArray).forEach(item => { // セリフ1行ごとにアイテム追加
      const name = item[0];
      const filename = item[1];
      const time = item[2];
      const length = item[3];
      const text = item[4];

      if (!(name in names)) { // キャラクター（話者）に対応するレイヤーを決定
        maxLayer++;
        names[name] = maxLayer;
      }
      const layer = names[name];
      const frame = Math.trunc(time * fps / 1000); // ミリ秒からフレーム数を計算、整数化
      const lengthframe = Math.trunc(length * fps / 1000);

      // アイテム追加
      const newItemStr = settingItem.replaceAll("$voice", text).replaceAll("$frame", frame)
        .replaceAll("$layer", layer).replaceAll("$length", lengthframe).replaceAll("$remark", path.basename(filename));
      const newItem = JSON.parse(newItemStr);
      items.push(newItem);
    });

    // レイヤー設定
    const settingLayerSetting = fs.readFileSync(path.join(__dirname, 'ymm4setting', 'layersetting.json'), 'utf8');
    Object.keys(names).forEach(name => {
      const newItemStr = settingLayerSetting.replaceAll("$name", name).replaceAll("$layer", names[name]);
      const newItem = JSON.parse(newItemStr);
      layers.push(newItem);
    });

    // YMM4プロジェクトファイルを色々書き換え
    templateYmm4Project.FilePath = ymm4ProjectPath;
    templateYmm4Project.Timeline.MaxLayer = maxLayer;
    templateYmm4Project.Timeline.Length = mixedMediaLengthFrame;
    fs.writeFileSync(ymm4ProjectPath, JSON.stringify(templateYmm4Project, null, 2));

    // フォルダを開く
    if (openYmm4projectfolder) {
      shell.openPath(edittingProject.dir);
    }
    // YMM4を開く
    if (execYmm4) {
      shell.openPath(ymm4ProjectPath);
    }

    return true
  } catch (err) {
    logger.error('ymm4 save err:' + ymm4ProjectPath)
    logger.error(err)
    return false
  }
})


/**
 * プロジェクトの編集ボタンを押下 → htmlファイルの読み込み（同時に編集ファイルも読み込む）
 * js/main.js        editProject -> editbutton.addEventListener('click',' ...
 * -> js/preload.js  editProject
 * -> index.js       editProject
 * @returns 
 */
let editFileName = ""  // 編集ファイル
let edittingProject;
ipcMain.handle('editProject', async (event, projectId) => {
  const project = projects.find((project) => project.id == projectId);
  edittingProject = project;

  edited = false;
  isSaveAndBackToHome = false;

  project.access_time = timeToLocalString(new Date()); // 閲覧時間更新
  writeProjects(); // 更新したのでプロジェクトリスト出力

  // 編集ファイルを探す。 .js から .json のフルパスを取得
  editFileName = changeExtension(project.result, ".json");
  // 開くhtmlファイルを探す。 .js から .html のフルパスを取得
  const dsthtmlfile = changeExtension(project.result, ".html");

  // htmlファイルを作る
  const srchtmlfile = env.htmldir + "index.html";

  try {
    // 元になるファイルと認識結果を読み込む
    const srcContent = fs.readFileSync(srchtmlfile, 'binary');
    const decodedSrcContent = encoding.convert(srcContent, {
      from: 'SJIS', to: 'UNICODE', type: 'string',
    });
    const jsContent = fs.readFileSync(project.result, 'binary');
    const decodedJsContent = encoding.convert(jsContent, {
      from: 'SJIS', to: 'UNICODE', type: 'string',
    });

    // "RESULTS" を認識結果で置換
    const dstContent = decodedSrcContent.replace('RESULTS', decodedJsContent);

    // 置換結果を書き込み
    fs.writeFileSync(dsthtmlfile, encoding.convert(dstContent, {
      from: 'UNICODE', to: 'SJIS', type: 'string',
    }), 'binary');

  } catch (error) {
    logger.error('An error occurred:', error);
    return;
  }

  try {
    // 画像ファイルなどが入ったディレクトリを編集ファイルと同じフォルダに上書きコピー
    fs.copySync(env.htmldir + "htmlfiles", path.dirname(dsthtmlfile) + "/htmlfiles");
    logger.debug('Directory copied successfully.');
  } catch (err) {
    logger.error('Error copying directory:', err);
  }




  mainWindow.loadFile(dsthtmlfile, {
    query: {
      "electron": "true", // 画面遷移 パラメタelectronを指定して、Electronから開いているという情報を渡す
      "existsYmm4TemplateProjectFile": fs.existsSync(ymm4TemplateProjectFile) // YMM4プロジェクトのテンプレートが存在するかどうか（無いと出力できない）
    }
  })
    .then(_ => {

      result = loadEditFile(editFileName)
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
 * ファイルパスの拡張子を変更したものを返す
 * @param {*} filepath ファイルのパス
 * @param {*} toext 変更後の拡張子
 */
function changeExtension(filepath, toext) {
  const extension = path.extname(filepath);
  let changedPath;
  if (extension) {
    // 拡張子を置き換える
    changedPath = filepath.replace(new RegExp(`${extension}$`), toext); // 最後の一致のみ
  } else {
    // 拡張子がない場合は ".json" を追加する
    changedPath = `${filepath}.json`;
  }
  return changedPath;
}

/**
 * プロジェクトの編集ファイルの読み込み
 * @param {string} path ファイルパス
 * 
 * @return ファイル読み込み結果
 */
function loadEditFile(path) {
  try {
    fs.accessSync(path)
    return fs.readFileSync(path, 'utf8', (err, data) => {
      if (err) {
        throw null
      }
      return data
    });
  } catch (err) {
    logger.error('no file:' + path)
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
  let path = editFileName;
  let data = arg;
  let jsonData = JSON.parse(data);
  try {
    return fs.writeFile(path, data, (err) => {
      if (err) {
        throw err
      }
      logger.debug(data);
      Object.values(jsonData.personalData).forEach(person => { // 音声ファイルごとの表示名を更新
        file = edittingProject.files.find((file) => file.filename == person.orgfile);
        if (file) {
          file.name = person.displayname;
        }
      });
      edittingProject.title = jsonData.projectName; // プロジェクトのタイトルを更新  
      edittingProject.modified_time = timeToLocalString(new Date()); // 編集時間更新
      writeProjects(); // 更新したのでプロジェクトリスト出力

      if (isSaveAndExit) { // 保存して終了する
        isClose = true;
        app.quit();
      }
      if (isSaveAndBackToHome) { // 保存してホームに戻る
        backToHome();
      }
      return true
    });
  } catch (err) {
    logger.error('save err:' + path)
    logger.error(err)
    return false
  }
})


/**
 * 編集フラグの上げ下げ
 * index.html        setEdited
 * -> js/preload.js  setEdited
 * -> index.js       setEdited
 */
ipcMain.handle('setEdited', async (event, e) => {
  edited = e;
});

/**
 * ショートカットキーを登録する
 */
function registShortcut() {
  localShortcut.register("Ctrl+S", () => {
    mainWindow.webContents.send('apiSaveEditNotify');
  })
}

/**
 * ホームに戻る（編集画面から発火）
 * index.html        backToHome
 * -> js/preload.js  backToHome
 * -> index.js       backToHome
 */
ipcMain.handle('backToHome', async (event) => {
  if (edited) {
    checkSaveDialog(false);
    return;
  }
  await backToHome();
});

/**
 * ホームに戻る(index.html)
 */
async function backToHome() {
  newVersion = await checkNewVersion();
  mainWindow.loadFile("index.html", { query: { "newVersion": newVersion } });
  mainWindow.setTitle("DisNOTE");
  edited = false;
}

/**
 * 新しいバージョンが公開されているかどうかチェックする
 * @returns 新しいバージョンが公開されていればそのバージョン、そうでなければ空文字列
 */
async function checkNewVersion() {
  try {
    const response = await axios.get('https://roji3.jpn.org/disnote/version.cgi', { timeout: 1000 });

    if (response.status === 200) {
      const newVersion = 'v' + response.data.replace('DisNOTE_', '').replace('.zip', '');
      const zipVersion = newVersion.replace('v', '').split('.');
      const cVersion = currentVersion.replace('v', '').split('.');

      for (let i = 0; i < 3; i++) {
        if (parseInt(zipVersion[i]) > parseInt(cVersion[i])) {
          return newVersion;
        }
        if (parseInt(zipVersion[i]) < parseInt(cVersion[i])) {
          return "";
        }
      }
    } else {
      logger.info(`DisNOTE最新バージョンの取得に失敗: ${response.status}`); // アクセスに失敗しても特にエラーにはしない
    }
  } catch (error) {
    logger.error('An error occurred:', error.message);
  }
  return "";
}
