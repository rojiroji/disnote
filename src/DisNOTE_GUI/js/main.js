

document.addEventListener('drop', (e) => {
    e.preventDefault();
    e.stopPropagation();
  
    for (const f of e.dataTransfer.files) {
      console.log('File(s) you dragged here: ', f.path)
      window.api.apiLoadFile(f.path)
    }
  });
  document.addEventListener('dragover', (e) => {
    e.preventDefault();
    e.stopPropagation();
  });