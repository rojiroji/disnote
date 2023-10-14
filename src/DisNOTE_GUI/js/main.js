$(function () {

  $("#recognize").dialog({ // 認識設定
    autoOpen: false,
    modal: true,
    title: "音声認識",
    buttons: [
      {
        id: "start_recognize",
        text: "音声認識開始",
        click: async function () {
          // wit.aiのtoken（チェックボックスが入っていなければ無視）
          const witaitoken = $("#witaitoken").val();
          const isusewitai = $("#engine_witai").prop("checked");
          if (isusewitai) {
            if (witaitoken.length <= 0) {
              alert("wit.aiのトークンが入力されていません");
              return false;
            }
          }
          $("#start_recognize").prop("disabled", true);//二度押し防止 
          $("#cancel_recognize").prop("disabled", true);//二度押し防止 
          $("#recognize_initialized").text("音声認識の準備中…（しばらくお待ちください）");

          rec_progress = {}; // 進捗リセット
          rec_process_running = true; // プロセス起動中のフラグを立てる
          window.api.recognizeProject(projectid, isusewitai, witaitoken); // 認識開始
          updateCuiProgress("音声認識準備中");
          $("body").css("cursor", "wait"); // カーソルを待ち状態に
        }
      },
      {
        id: "cancel_recognize",
        text: "キャンセル",
        click: async function () {
          $(this).dialog("close");
        }
      },
    ],
    width: "500",
  }).on('dialogclose', function (event) {
    $("body").css("cursor", "auto"); // カーソルを戻す
  });

  $("#progress").dialog({ // 認識進捗
    autoOpen: false,
    modal: true,
    title: "音声認識",
    buttons: [
      {
        text: "", // ボタン名は動的に変える
        id: "progress_button",
        click: async function () {
          $(this).dialog("close");
        }
      },
    ],
    beforeClose: function (event, ui) { // ダイアログを閉じるときの処理
      return cancelRecognize();
    },
    width: "640",
  });

});

// 音声認識エンジンキャンセル
function cancelRecognize() {
  if (rec_process_running) {
    if (confirm("音声認識を中断しますか？")) {
      $("#progress_button").text("閉じる").prop("disabled", true); // 二度押し防止
      window.api.cancelRecognize();
    } else {
      return false;
    }
  }
  return true;
}
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
let rec_process_running = false; // 音声認識エンジンの状況

/**
 * 起動時
 */
window.addEventListener('load', async (event) => {
  reloadProjects(); // プロジェクト一覧描画

  let config = await window.api.getConfig(); // コンフィグ取得
  console.log(config);
  $("#engine_witai").prop("checked", config.isusewitai);
  $("#witaitoken").val(config.witaitoken);

  /* callback登録 */
  window.api.on("engineStdout", engineStdout); // DisNOTEエンジンの標準出力を受け取る
  window.api.on("engineStderr", engineStderr); // DisNOTEエンジンのエラー出力を受け取る
  window.api.on("engineClose", engineClose); // DisNOTEエンジンの終了コードを受け取る

  window.api.on("updateCuiProgress", updateCuiProgress); // CUIの進捗文字列表示
  window.api.on("checkedAudioFiles", checkedAudioFiles); // 音声ファイルの進捗テーブルの作成
  window.api.on("updateAudioFileProgress", updateAudioFileProgress); // 音声ファイルの進捗テーブルの更新
  window.api.on("updateLastProgress", updateLastProgress); // 最終処理の進捗テーブルの更新
  window.api.on("rewriteProjectInfo", rewriteProjectInfo); // プロジェクトの情報を再表示


  document.querySelector('#disable_project').addEventListener('click', async (e) => { // プロジェクト無効化
    if (confirm("プロジェクトを削除しますか？\nもう一度同じファイルを登録すると復活します")) {
      await window.api.disableProject(projectid);
      alert("プロジェクトを削除しました");
      $("#recognize").dialog("close");
      await reloadProjects();
    }
  });
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

  const newProjectId = await window.api.dropMediaFiles(filePaths); // 音声ファイルドロップ処理 → プロジェクト一覧再生成
  await reloadProjects();

  if(newProjectId != null){ // 新しくプロジェクトを追加した場合は認識ダイアログを開く
    openRecognizeDialog(newProjectId);
  }
});

/**
 * 認識ダイアログを開く
 * @param {認識するプロジェクトのID} id 
 */
let projectid;
function openRecognizeDialog(id){
  projectid = id;
  $("#recognize").dialog("open");
  $("#start_recognize").prop("disabled", false); // ボタンを復活させる
  $("#cancel_recognize").prop("disabled", false);// ボタンを復活させる          
  $("#recognize_initialized").text("　");
}

/**
 * プロジェクト一覧再描画
 */
async function reloadProjects() {
  let table = await window.api.getProjectsTable();
  document.querySelector('#projects').innerHTML = table;

  let config = await window.api.getConfig(); // コンフィグ取得
  $("#project_sort_key").val(config.project_sort_key); // ソート条件再生成
  $("#project_sort_order").text(config.project_sort_order == "desc" ? "↑" : "↓");

  document.querySelector('#project_sort_key').addEventListener('change', async (e) => { // ソート条件変更
    await window.api.updateConfig($("#project_sort_key").val(), false);
    await reloadProjects();
  });
  document.querySelector('#project_sort_order').addEventListener('click', async (e) => { // 降順/照準変更
    await window.api.updateConfig($("#project_sort_key").val(), true);
    await reloadProjects();
  });

  // プロジェクトごとの編集ボタンにイベントを追加
  const editbuttons = document.querySelectorAll("button.edit");
  for (const editbutton of editbuttons) {
    // console.log("projectid=" + editbutton.getAttribute("projectid"));
    editbutton.addEventListener('click', async (e) => {
      projectid = e.currentTarget.getAttribute("projectid"); // ボタンにはprojetid属性がついている
      window.api.editProject(projectid); // 編集開始
    });
  }

  // プロジェクトごとのrecognizeボタンにイベントを追加
  const recognizebuttons = document.querySelectorAll("button.recognize");
  for (const recognizebutton of recognizebuttons) {
    recognizebutton.addEventListener('click', async (e) => {
      openRecognizeDialog(e.currentTarget.getAttribute("projectid")); // ボタンにはprojetid属性がついている)
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

  // witaiを使わない場合は進捗を進めないのでその旨を表示
  if (!$("#engine_witai").prop("checked")) {
    $("div.witaiprogress").text("skip");
    $("progress.witaiprogress").val(100);
  }

  $("#recognize").dialog("close"); // エンジン起動のダイアログを閉じる
  $("#progress_button").text("音声認識中断").prop("disabled", false); // ボタンを復活させる
  $("#progress").dialog("open"); // サイズがここで確定するのでダイアログを開く
  /*
    const windowWidth = window.innerWidth || document.documentElement.clientWidth || document.body.clientWidth;
  const windowHeight = window.innerHeight || document.documentElement.clientHeight || document.body.clientHeight;
  
  console.log(`ウィンドウの幅: ${windowWidth}`);
  console.log(`ウィンドウの高さ: ${windowHeight}`);
  */
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
    "setAudioFileInfo": "準備中(1/7)", "seg": "無音解析中(2/7)", "split": "音声分割設定中(3/7)",
    "split_audio": "音声分割中(4/7)", "prepare": "音声認識開始待ち(5/7)", "rec": "音声認識中(6/7)",
    "conv_audio": "音声変換中(7/7)"
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

/**
 * 最終処理の進捗を更新する
 */
function updateLastProgress(progress) {
  document.querySelector(`#progress_last`).value = progress;
  document.querySelector(`#percent_last`).innerText = progress.toFixed(1) + "%";
}

/**
 * プロジェクトの情報を書き換えて画面に表示する
 */
function rewriteProjectInfo(project) {
  console.log(project);
  $(`#project_title_${project.id}`).text(project.title);
  $(`#project_times_${project.id} div.recognized`).prop("title", project.recognized_time);
  $(`#project_times_${project.id} div.recognized span`).text(project.recognized_time.substring(0, 10)); // 日付のところ(yyyy/MM/dd)だけ切り取る
  $(`#project_times_${project.id} div.modified`).prop("title", project.modified_time);
  $(`#project_times_${project.id} div.modified span`).text(project.modified_time.substring(0, 10)); // 日付のところ(yyyy/MM/dd)だけ切り取る
  $(`#project_times_${project.id} div.access`).prop("title", project.access_time);
  $(`#project_times_${project.id} div.access span`).text(project.access_time.substring(0, 10)); // 日付のところ(yyyy/MM/dd)だけ切り取る
  $(`#project_editbutton_${project.id}`).prop("disabled", (project.recognized_time.length > 10) ? false : true); // 編集ボタン
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
  console.log("engine exit code=" + code);
  $("#progress_button").text("閉じる").prop("disabled", false); // ただの閉じるボタンにする
  if (code == 0) {
    alert("正常に音声認識が完了しました");
  } else if (code == null) {
    // キャンセル
  } else {
    alert("音声認識が上手くいきませんでした。ログを見てみてください。\ncode=" + code);
  }
  rec_process_running = false; // とにかくプロセスは落ちた
}
