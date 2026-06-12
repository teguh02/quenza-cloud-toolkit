/* ==========================================================================
   Quenza Cloud Toolkit - standalone_filemanager.js
   Full-page file manager with CRUD capabilities and Math CAPTCHA.
   ========================================================================== */

(function () {
  "use strict";

  var state = {
    currentPath: "",
    parent: null,
    loading: false,
    deleteTarget: "",
    captchaAnswer: 0,
    editTarget: ""
  };

  // --- DOM helpers ---
  function $(id) { return document.getElementById(id); }
  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }
  function escapeHtml(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  var ICON = {
    folder: '<svg class="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
    file: '<svg class="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
    drive: '<svg class="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="10" rx="2"/><line x1="6" y1="12" x2="6.01" y2="12"/></svg>',
    chevron: '<svg class="h-3.5 w-3.5 shrink-0 text-label" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>',
    edit: '<svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>',
    trash: '<svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>'
  };

  // --- API ---
  function apiGet(url) {
    return fetch(url, { headers: { Accept: "application/json" } }).then(function (r) {
      if (r.status === 401) { window.location.href = "/login"; throw new Error("unauthorized"); }
      return r.json();
    });
  }
  
  function apiPost(url, payload) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (r) {
      if (r.status === 401) { window.location.href = "/login"; throw new Error("unauthorized"); }
      return r.json();
    });
  }

  // --- Rendering ---
  function renderQuickRoots() {
    var tree = $("fm-tree");
    if (!tree) return;
    apiGet("/api/fs/browse").then(function (data) {
      tree.innerHTML = "";
      var homeBtn = el("button", "flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs font-semibold text-secondary transition-colors duration-200 hover:bg-surface hover:text-heading");
      homeBtn.type = "button";
      homeBtn.innerHTML = '<span class="text-blue-500">' + ICON.drive + "</span><span>Root / Drives</span>";
      homeBtn.addEventListener("click", function () { navigate(""); });
      tree.appendChild(homeBtn);

      (data.entries || []).forEach(function (entry) {
        var b = el("button", "flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs font-medium text-secondary transition-colors duration-200 hover:bg-surface hover:text-heading");
        b.type = "button";
        var icon = entry.is_drive ? ICON.drive : ICON.folder;
        b.innerHTML = '<span class="text-blue-500">' + icon + "</span><span class='truncate'>" + escapeHtml(entry.name) + "</span>";
        b.addEventListener("click", function () { navigate(entry.path); });
        tree.appendChild(b);
      });
    }).catch(function () {
      tree.innerHTML = '<div class="px-2 py-3 text-xs text-red-500">Gagal memuat struktur.</div>';
    });
  }

  function renderBreadcrumb(data) {
    var bc = $("fm-breadcrumb");
    if (!bc) return;
    bc.innerHTML = "";
    var rootChip = el("button", "shrink-0 rounded-md px-1.5 py-0.5 text-label transition-colors duration-200 hover:bg-canvas hover:text-heading");
    rootChip.type = "button";
    rootChip.textContent = "Root";
    rootChip.addEventListener("click", function () { navigate(""); });
    bc.appendChild(rootChip);

    (data.breadcrumb || []).forEach(function (seg) {
      bc.appendChild(el("span", "shrink-0 text-line", "/"));
      var chip = el("button", "shrink-0 rounded-md px-1.5 py-0.5 transition-colors duration-200 hover:bg-canvas hover:text-heading");
      chip.type = "button";
      chip.textContent = seg.name;
      chip.addEventListener("click", function () { navigate(seg.path); });
      bc.appendChild(chip);
    });
  }

  function renderContent(data) {
    var content = $("fm-content");
    if (!content) return;
    content.innerHTML = "";

    if (!data.ok) {
      content.appendChild(el("div", "flex h-full flex-col items-center justify-center gap-2 text-center",
        '<div class="flex h-12 w-12 items-center justify-center rounded-xl bg-red-50 text-red-500"><svg class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg></div><p class="text-sm font-semibold text-heading">' + escapeHtml(data.error || "Tidak dapat membuka direktori.") + "</p>"));
      return;
    }

    var entries = data.entries || [];
    if (entries.length === 0) {
      content.appendChild(el("div", "flex h-full items-center justify-center text-sm text-label", "Direktori kosong."));
      return;
    }

    var list = el("div", "space-y-1");
    entries.forEach(function (entry) { list.appendChild(buildRow(entry)); });
    content.appendChild(list);
  }

  function buildRow(entry) {
    var isDir = entry.type === "directory";
    var row = el("div", "group flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors duration-200 hover:bg-canvas relative overflow-hidden");

    var iconWrap = el("span", "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg " + (isDir ? "bg-pastel-blue text-blue-500" : "bg-pastel-green text-brand-teal"));
    iconWrap.innerHTML = entry.is_drive ? ICON.drive : isDir ? ICON.folder : ICON.file;
    row.appendChild(iconWrap);

    var info = el("div", "min-w-0 flex-1 pr-24");
    var name = el("p", "truncate text-sm font-medium text-heading");
    name.textContent = entry.name;
    info.appendChild(name);
    var metaText = isDir ? entry.modified || "Folder" : (entry.size ? entry.size : "") + (entry.modified ? " · " + entry.modified : "");
    if (metaText) {
      var meta = el("p", "truncate text-[11px] text-label");
      meta.textContent = metaText;
      info.appendChild(meta);
    }
    row.appendChild(info);

    if (!entry.is_drive) {
      var actions = el("div", "flex items-center gap-1 opacity-0 transition-opacity duration-200 group-hover:opacity-100 absolute right-3 bg-canvas/80 rounded-lg backdrop-blur-sm p-1 shadow-sm");
      if (!isDir) {
        var editBtn = el("button", "p-1.5 text-secondary hover:text-brand-teal rounded-md hover:bg-surface transition-colors");
        editBtn.title = "Edit File";
        editBtn.innerHTML = ICON.edit;
        editBtn.addEventListener("click", function(e) {
          e.stopPropagation();
          openEditModal(entry.path, entry.name);
        });
        actions.appendChild(editBtn);
      }
      var delBtn = el("button", "p-1.5 text-secondary hover:text-red-500 rounded-md hover:bg-surface transition-colors");
      delBtn.title = "Hapus";
      delBtn.innerHTML = ICON.trash;
      delBtn.addEventListener("click", function(e) {
        e.stopPropagation();
        openDeleteModal(entry.path);
      });
      actions.appendChild(delBtn);
      row.appendChild(actions);
    }

    if (isDir) {
      row.addEventListener("dblclick", function () { navigate(entry.path); });
      row.classList.add("cursor-pointer");
    }
    return row;
  }

  // --- Actions ---
  function navigate(path) {
    if (state.loading) return;
    state.loading = true;
    setBusy(true);
    var url = "/api/fs/browse" + (path ? "?path=" + encodeURIComponent(path) : "");
    apiGet(url).then(function (data) {
      state.currentPath = data.path || "";
      state.parent = data.parent;
      renderBreadcrumb(data);
      renderContent(data);
      var up = $("fm-up");
      if (up) up.disabled = data.is_root;
    }).catch(function () {
      var content = $("fm-content");
      if (content) content.innerHTML = '<div class="flex h-full items-center justify-center text-sm text-red-500">Kesalahan jaringan.</div>';
    }).finally(function () {
      state.loading = false;
      setBusy(false);
    });
  }

  function goUp() {
    if (state.parent === null && state.currentPath === "") return;
    navigate(state.parent === null ? "" : state.parent);
  }

  function refresh() {
    navigate(state.currentPath);
  }

  function setBusy(on) {
    var refreshBtn = $("fm-refresh");
    if (refreshBtn) {
      refreshBtn.classList.toggle("animate-spin", on);
      refreshBtn.disabled = on;
    }
  }

  function toggleTree(show) {
    var panel = $("fm-tree-panel"), backdrop = $("fm-tree-backdrop");
    if (!panel) return;
    if (show) {
      panel.classList.remove("-translate-x-full");
      if (backdrop) backdrop.classList.remove("hidden");
    } else {
      panel.classList.add("-translate-x-full");
      if (backdrop) backdrop.classList.add("hidden");
    }
  }

  // --- CRUD Modals ---
  function promptCreateFolder() {
    if (!state.currentPath) return alert("Silakan pilih direktori induk terlebih dahulu.");
    var name = prompt("Nama folder baru:");
    if (!name) return;
    apiPost("/api/fs/mkdir", { path: state.currentPath, name: name }).then(function(res) {
      if (res.ok) refresh();
      else alert(res.error);
    }).catch(function(e) { alert("Gagal: " + e); });
  }

  function promptCreateFile() {
    if (!state.currentPath) return alert("Silakan pilih direktori induk terlebih dahulu.");
    var name = prompt("Nama file teks baru:");
    if (!name) return;
    apiPost("/api/fs/mkfile", { path: state.currentPath, name: name }).then(function(res) {
      if (res.ok) refresh();
      else alert(res.error);
    }).catch(function(e) { alert("Gagal: " + e); });
  }

  function openEditModal(path, name) {
    state.editTarget = path;
    $("editor-title").textContent = "Edit: " + name;
    $("editor-textarea").value = "Memuat...";
    $("editor-textarea").disabled = true;
    $("editor-save").disabled = true;
    QuenzaModal.open("modal-editor");

    apiGet("/api/fs/read?path=" + encodeURIComponent(path)).then(function(res) {
      if (res.ok) {
        $("editor-textarea").value = res.content;
        $("editor-textarea").disabled = false;
        $("editor-save").disabled = false;
      } else {
        $("editor-textarea").value = "ERROR: " + res.error;
      }
    }).catch(function(e) {
      $("editor-textarea").value = "Kesalahan jaringan: " + e;
    });
  }

  function saveEdit() {
    var content = $("editor-textarea").value;
    var btn = $("editor-save");
    btn.disabled = true;
    btn.textContent = "Menyimpan...";
    
    apiPost("/api/fs/edit", { path: state.editTarget, content: content }).then(function(res) {
      if (res.ok) {
        QuenzaModal.close("modal-editor");
        refresh();
      } else {
        alert("Gagal: " + res.error);
      }
    }).catch(function(e) {
      alert("Kesalahan: " + e);
    }).finally(function() {
      btn.disabled = false;
      btn.textContent = "Simpan Perubahan";
    });
  }

  function openDeleteModal(path) {
    state.deleteTarget = path;
    $("delete-target-path").textContent = path;
    $("delete-captcha-answer").value = "";
    
    // Generate captcha
    var x = Math.floor(Math.random() * 20) + 1;
    var y = Math.floor(Math.random() * 20) + 1;
    state.captchaAnswer = x + y;
    $("delete-captcha-question").textContent = "Berapa " + x + " + " + y + " ?";
    checkCaptcha(); // reset button state
    
    QuenzaModal.open("modal-delete");
    // Focus input
    setTimeout(function() { $("delete-captcha-answer").focus(); }, 100);
  }

  function checkCaptcha() {
    var val = parseInt($("delete-captcha-answer").value, 10);
    var btn = $("delete-confirm-btn");
    if (val === state.captchaAnswer) {
      btn.disabled = false;
      btn.classList.remove("opacity-50", "cursor-not-allowed");
    } else {
      btn.disabled = true;
      btn.classList.add("opacity-50", "cursor-not-allowed");
    }
  }

  function executeDelete() {
    var btn = $("delete-confirm-btn");
    btn.disabled = true;
    btn.textContent = "Menghapus...";
    
    apiPost("/api/fs/delete", { path: state.deleteTarget }).then(function(res) {
      if (res.ok) {
        QuenzaModal.close("modal-delete");
        refresh();
      } else {
        alert("Gagal: " + res.error);
        btn.disabled = false;
        btn.textContent = "Hapus Permanen";
      }
    }).catch(function(e) {
      alert("Kesalahan: " + e);
      btn.disabled = false;
      btn.textContent = "Hapus Permanen";
    });
  }

  function init() {
    renderQuickRoots();
    navigate("");
  }

  window.StandaloneFM = {
    init: init,
    navigate: navigate,
    goUp: goUp,
    refresh: refresh,
    toggleTree: toggleTree,
    promptCreateFolder: promptCreateFolder,
    promptCreateFile: promptCreateFile,
    saveEdit: saveEdit,
    checkCaptcha: checkCaptcha,
    executeDelete: executeDelete
  };
})();
