
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
      console.log("editbutton click:" + projectid);
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

// DisNOTEエンジンの標準出力を受け取る
function engineStdout(outputLine) {
  document.querySelector('#enginestdout').innerText = outputLine; // TODO
}

// DisNOTEエンジンのエラー出力を受け取る
function engineStderr(outputLine) {
  document.querySelector('#engineStderr').innerText = outputLine; // TODO
}

// DisNOTEエンジンの終了コードを受け取る
function engineClose(code) {
  alert("engine exit code=" + code);
}
