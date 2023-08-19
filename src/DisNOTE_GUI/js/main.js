
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

/**
 * 起動時
 */
window.addEventListener('load', async (event) => {
  reloadProjects(); // プロジェクト一覧描画

  /* callback登録 */
  window.api.on("engineStdout", engineStdout); // DisNOTEエンジンの標準出力を受け取る
  window.api.on("engineStderr", engineStderr); // DisNOTEエンジンのエラー出力を受け取る
  window.api.on("engineClose", engineClose); // DisNOTEエンジンの終了コードを受け取る

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
      await window.api.editProject(projectid);
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

// 音声ファイルの進捗テーブルの作成
function checkedAudioFiles(tableHtml) {
  document.querySelector('#progress').innerHTML = tableHtml;

}

// 音声ファイルの進捗テーブルの更新
function updateAudioFileProgress(info) {
  const index = info.index;
  document.querySelector(`#stage_${index}`).innerHTML = {
    "setAudioFileInfo": "他音声準備待ち(1/7)", "seg": "無音解析中(2/7)", "split": "音声分割設定中(3/7)",
    "split_audio": "音声分割中(4/7)", "prepare": "音声認識開始待ち(5/7)", "rec": "音声認識中(6/7)",
    "conv_audio": "音声変換処理(7/7)"
  }[info.stage];

  let progress = 0;
  if (info.max) {
    progress = 100 * info.progress / info.max;
  }

  let progress_tag = null;
  let percent_tag = null;
  if (info.engine) {
    let progressTarget;
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
  } else {
    progress_tag = document.querySelector(`#progress_main_${index}`);
    percent_tag = document.querySelector(`#percent_main_${index}`);
  }
  if (progress_tag) {
    progress_tag.value = progress;
  }
  if (percent_tag) {
    percent_tag.innerText = progress.toFixed(1) + "%";
  }


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
