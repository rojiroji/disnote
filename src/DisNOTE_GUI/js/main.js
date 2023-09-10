$(function () {
  $("#progress").dialog({ // 認識進捗
    autoOpen: false,
    modal: true,
    title: "音声認識",
    closeOnEscape: true,
    close: function (event, ui) { // ダイアログを閉じるときの処理
      

    },
    position:{ my: "center", at: "center top+200px"}, // 何故か縦の中央に来てくれないのでこの値を設定
    width: "500",
  });
});
/*
document.addEventListener('drop', (e) => {
  e.preventDefault();
  e.stopPropagation();

  for (const f of e.dataTransfer.files) {
    console.log('File(s) you dragged here: ', f.path)
    window.api.apiLoadFile(f.path)
  }
});
*/

let rec_progress; // 音声認識の進捗 

/**
 * 起動時
 */
window.addEventListener('load', async (event) => {
  reloadProjects(); // プロジェクト一覧描画

  /* callback登録 */
  window.api.on("engineStdout", engineStdout); // DisNOTEエンジンの標準出力を受け取る
  window.api.on("engineStderr", engineStderr); // DisNOTEエンジンのエラー出力を受け取る
  window.api.on("engineClose", engineClose); // DisNOTEエンジンの終了コードを受け取る

  window.api.on("updateCuiProgress", updateCuiProgress); // CUIの進捗文字列表示
  window.api.on("checkedAudioFiles", checkedAudioFiles); // 音声ファイルの進捗テーブルの作成
  window.api.on("updateAudioFileProgress", updateAudioFileProgress); // 音声ファイルの進捗テーブルの更新


});

/**
 * 音声ファイルドロップ時
 */
document.addEventListener('drop', async (e) => {
  e.preventDefault();
  e.stopPropagation();

  let filePaths = [];

  for (const f of e.dataTransfer.files) { // e.dataTransfer.files のまま渡すとエラーになるのでpathだけの配列を作る
    console.log('File(s) you dragged here: ', f.path)
    filePaths.push(f.path);
  }

  await window.api.dropMediaFiles(filePaths); // 音声ファイルドロップ処理 → プロジェクト一覧再生成
  reloadProjects();
});

/**
 * プロジェクト一覧再描画
 */
async function reloadProjects() {
  let table = await window.api.getProjectsTable();
  document.querySelector('#projects').innerHTML = table;

  // プロジェクトごとの編集ボタンにイベントを追加
  const editbuttons = document.querySelectorAll("button.edit");
  for (const editbutton of editbuttons) {
    // console.log("projectid=" + editbutton.getAttribute("projectid"));
    editbutton.addEventListener('click', async (e) => {
      let projectid = e.currentTarget.getAttribute("projectid"); // ボタンにはprojetid属性がついている
      //console.log("editbutton click:" + projectid);

      // TODO：認識ボタン押下時に以下の処理
      rec_progress = {}; // 進捗リセット
      await window.api.editProject(projectid);
      updateCuiProgress("音声認識準備中");
      $("#progress").dialog("open");

    });
  }

  // プロジェクトごとのfolderボタンにイベントを追加
  const folderbuttons = document.querySelectorAll("button.folder");
  for (const folderbutton of folderbuttons) {
    folderbutton.addEventListener('click', async (e) => {
      let projectid = e.currentTarget.getAttribute("projectid"); // ボタンにはprojetid属性がついている
      console.log("folderbutton click:" + projectid);
      await window.api.openProjectFolder(projectid);
    });
  }
}

document.addEventListener('dragover', (e) => {
  e.preventDefault();
  e.stopPropagation();
});

// CUIの進捗文字列表示
function updateCuiProgress(text) {
  document.querySelector('#progress_cui').innerText = text;

}

// 音声ファイルの進捗テーブルの作成
function checkedAudioFiles(tableHtml) {
  document.querySelector('#progress_table').innerHTML = tableHtml;
}

// 音声ファイルの進捗テーブルの更新
function updateAudioFileProgress(info) {
  const index = info.index;

  let progress = 0;
  if (info.max) {
    progress = 100 * info.progress / info.max;
  }

  let progress_tag = null;
  let percent_tag = null;
  let thread = "";
  if (info.engine) {
    switch (info.engine) {
      case "google":
        progress_tag = document.querySelector(`#progress_google_${index}`);
        percent_tag = document.querySelector(`#percent_google_${index}`);
        break;
      case "witai":
        progress_tag = document.querySelector(`#progress_witai_${index}`);
        percent_tag = document.querySelector(`#percent_witai_${index}`);
        break;
    }
    thread = info.engine;
  } else {
    progress_tag = document.querySelector(`#progress_main_${index}`);
    percent_tag = document.querySelector(`#percent_main_${index}`);
    thread = "main";
  }

  /**
   * rec_progressのフォーマット
   * rec_progress[index] = { // 音声ファイルごとの配列
   *    "main" : { // スレッド（main ,google, witai）
   *       "progress"{
   *          "setAudioFileInfo" : "100", // ステージごとの進捗
   *          "checkedFiles" : "50"
   *       },
   *       "stage" : "checkedFiles" // 現在のステージ
   *    }
   * }
   */
  // 進捗度合いを保持（非同期で呼び出される。巻き戻らないようにする）
  if (!(index in rec_progress)) {
    rec_progress[index] = {};
  }
  if (!(thread in rec_progress[index])) {
    rec_progress[index][thread] = {};
    rec_progress[index][thread]["progress"] = {};
  }
  // ステージが後であれば更新
  const stages = ["setAudioFileInfo", "seg", "split", "split_audio", "prepare", "rec", "conv_audio"];
  const current_stage_id = findIndexInArray(stages, rec_progress[index][thread]["stage"]);
  const new_stage_id = findIndexInArray(stages, info.stage);
  if (current_stage_id < new_stage_id) {
    rec_progress[index][thread]["stage"] = info.stage;
  }

  //ステージごとの進捗を更新
  if (rec_progress[index][thread]["progress"][info.stage] > progress) {
    // 現在保持している進捗がundefinedの場合と、現在保持している進捗の方が先に進んでいたら何もしない
  } else {
    rec_progress[index][thread]["progress"][info.stage] = progress;
  }

  // 現在のステージを表示
  document.querySelector(`#stage_${index}`).innerHTML = {
    "setAudioFileInfo": "他音声準備待ち(1/7)", "seg": "無音解析中(2/7)", "split": "音声分割設定中(3/7)",
    "split_audio": "音声分割中(4/7)", "prepare": "音声認識開始待ち(5/7)", "rec": "音声認識中(6/7)",
    "conv_audio": "音声変換処理(7/7)"
  }[rec_progress[index]["main"]["stage"]];

  // 現在のステージの進捗を表示
  if (progress_tag) {
    progress_tag.value = rec_progress[index][thread]["progress"][info.stage];
  }
  if (percent_tag) {
    percent_tag.innerText = rec_progress[index][thread]["progress"][info.stage].toFixed(1) + "%";
  }
  console.log(rec_progress);


}

// 文字列の配列からindexを返す
function findIndexInArray(arr, target) {
  for (let i = 0; i < arr.length; i++) {
    if (arr[i] === target) {
      return i; // 文字列が見つかった場合、そのインデックスを返す
    }
  }
  return -1; // 文字列が見つからなかった場合、-1を返す
}

// DisNOTEエンジンの標準出力を受け取る
function engineStdout(logbody) {
  document.querySelector('#enginestdout').innerText = logbody; // TODO
  console.log(logbody);
}

// DisNOTEエンジンのエラー出力を受け取る
function engineStderr(outputLine) {
  //document.querySelector('#engineStderr').innerText = outputLine; // TODO
}

// DisNOTEエンジンの終了コードを受け取る
function engineClose(code) {
  //alert("engine exit code=" + code);
}
