/* ==========================================================================
   Quenza Cloud Toolkit - filemanager.js
   Integrated File Manager controller.
     * Fetches directory listings from /api/fs/browse
     * Renders the quick-roots tree (left) and content list (right)
     * Handles breadcrumb navigation, up/refresh, selection + submit
   Selection model: a Set of absolute paths. On submit, hidden <input
   name="paths"> fields are generated for the form POST.
   ========================================================================== */

(function () {
  "use strict";

  var state = {
    projectId: null,
    addPathsAction: "",
    currentPath: "",      // "" => virtual root (drives on Windows)
    parent: null,
    selected: new Set(),
    loading: false,
  };

  // --- DOM helpers -----------------------------------------------------------
  function $(id) {
    return document.getElementById(id);
  }

  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }

  var ICON = {
    folder:
      '<svg class="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
    file:
      '<svg class="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
    drive:
      '<svg class="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="10" rx="2"/><line x1="6" y1="12" x2="6.01" y2="12"/></svg>',
    chevron:
      '<svg class="h-3.5 w-3.5 shrink-0 text-label" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>',
  };

  // --- API -------------------------------------------------------------------
  function browse(path) {
    var url = "/api/fs/browse";
    if (path) url += "?path=" + encodeURIComponent(path);
    return fetch(url, { headers: { Accept: "application/json" } }).then(function (r) {
      if (r.status === 401) {
        window.location.href = "/login";
        throw new Error("unauthorized");
      }
      return r.json();
    });
  }

  // --- Rendering -------------------------------------------------------------
  function renderQuickRoots() {
    var tree = $("fm-tree");
    if (!tree) return;
    browse("")
      .then(function (data) {
        tree.innerHTML = "";

        var homeBtn = el(
          "button",
          "flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs font-semibold text-secondary transition-colors duration-200 hover:bg-surface hover:text-heading"
        );
        homeBtn.type = "button";
        homeBtn.innerHTML =
          '<span class="text-blue-500">' + ICON.drive + "</span><span>Root / Drives</span>";
        homeBtn.addEventListener("click", function () {
          navigate("");
        });
        tree.appendChild(homeBtn);

        var roots = data.entries || [];
        roots.forEach(function (entry) {
          var b = el(
            "button",
            "flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs font-medium text-secondary transition-colors duration-200 hover:bg-surface hover:text-heading"
          );
          b.type = "button";
          var icon = entry.is_drive ? ICON.drive : ICON.folder;
          b.innerHTML =
            '<span class="text-blue-500">' +
            icon +
            "</span><span class='truncate'>" +
            escapeHtml(entry.name) +
            "</span>";
          b.addEventListener("click", function () {
            navigate(entry.path);
          });
          tree.appendChild(b);
        });
      })
      .catch(function () {
        tree.innerHTML =
          '<div class="px-2 py-3 text-xs text-red-500">Gagal memuat struktur.</div>';
      });
  }

  function renderBreadcrumb(data) {
    var bc = $("fm-breadcrumb");
    if (!bc) return;
    bc.innerHTML = "";

    var rootChip = el(
      "button",
      "shrink-0 rounded-md px-1.5 py-0.5 text-label transition-colors duration-200 hover:bg-canvas hover:text-heading"
    );
    rootChip.type = "button";
    rootChip.textContent = "Root";
    rootChip.addEventListener("click", function () {
      navigate("");
    });
    bc.appendChild(rootChip);

    (data.breadcrumb || []).forEach(function (seg) {
      bc.appendChild(el("span", "shrink-0 text-line", "/"));
      var chip = el(
        "button",
        "shrink-0 rounded-md px-1.5 py-0.5 transition-colors duration-200 hover:bg-canvas hover:text-heading"
      );
      chip.type = "button";
      chip.textContent = seg.name;
      chip.addEventListener("click", function () {
        navigate(seg.path);
      });
      bc.appendChild(chip);
    });
  }

  function renderContent(data) {
    var content = $("fm-content");
    if (!content) return;
    content.innerHTML = "";

    if (!data.ok) {
      content.appendChild(
        el(
          "div",
          "flex h-full flex-col items-center justify-center gap-2 text-center",
          '<div class="flex h-12 w-12 items-center justify-center rounded-xl bg-red-50 text-red-500"><svg class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg></div><p class="text-sm font-semibold text-heading">' +
            escapeHtml(data.error || "Tidak dapat membuka direktori.") +
            "</p>"
        )
      );
      return;
    }

    var entries = data.entries || [];
    if (entries.length === 0) {
      content.appendChild(
        el(
          "div",
          "flex h-full items-center justify-center text-sm text-label",
          "Direktori kosong."
        )
      );
      return;
    }

    var list = el("div", "space-y-1");
    entries.forEach(function (entry) {
      list.appendChild(buildRow(entry));
    });
    content.appendChild(list);
  }

  function buildRow(entry) {
    var isDir = entry.type === "directory";
    var selectable = !entry.is_drive; // drives are navigated, not selected
    var checked = state.selected.has(entry.path);

    var row = el(
      "div",
      "group flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors duration-200 hover:bg-canvas" +
        (checked ? " bg-canvas" : "")
    );

    // Checkbox (skip for drives)
    if (selectable) {
      var cbWrap = el("label", "flex shrink-0 cursor-pointer items-center");
      var cb = el("input");
      cb.type = "checkbox";
      cb.className = "h-4 w-4 rounded accent-brand-teal";
      cb.checked = checked;
      cb.addEventListener("change", function (e) {
        e.stopPropagation();
        toggleSelect(entry.path, cb.checked, row);
      });
      cbWrap.appendChild(cb);
      cbWrap.addEventListener("click", function (e) {
        e.stopPropagation();
      });
      row.appendChild(cbWrap);
    } else {
      row.appendChild(el("span", "h-4 w-4 shrink-0"));
    }

    // Icon
    var iconWrap = el(
      "span",
      "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg " +
        (isDir ? "bg-pastel-blue text-blue-500" : "bg-pastel-green text-brand-teal")
    );
    iconWrap.innerHTML = entry.is_drive ? ICON.drive : isDir ? ICON.folder : ICON.file;
    row.appendChild(iconWrap);

    // Name + meta
    var info = el("div", "min-w-0 flex-1");
    var name = el("p", "truncate text-sm font-medium text-heading");
    name.textContent = entry.name;
    info.appendChild(name);
    var metaText = isDir
      ? entry.modified || "Folder"
      : (entry.size ? entry.size : "") + (entry.modified ? " · " + entry.modified : "");
    if (metaText) {
      var meta = el("p", "truncate text-[11px] text-label");
      meta.textContent = metaText;
      info.appendChild(meta);
    }
    row.appendChild(info);

    // Open affordance for directories
    if (isDir) {
      var open = el(
        "button",
        "flex h-7 items-center gap-1 rounded-lg px-2 text-[11px] font-semibold text-label opacity-0 transition-all duration-200 hover:bg-surface hover:text-brand-teal group-hover:opacity-100"
      );
      open.type = "button";
      open.innerHTML = "Buka" + ICON.chevron;
      open.addEventListener("click", function (e) {
        e.stopPropagation();
        navigate(entry.path);
      });
      row.appendChild(open);

      // Double-click row to open
      row.addEventListener("dblclick", function () {
        navigate(entry.path);
      });
      row.classList.add("cursor-pointer");
    }

    return row;
  }

  // --- Selection -------------------------------------------------------------
  function toggleSelect(path, on, row) {
    if (on) {
      state.selected.add(path);
      if (row) row.classList.add("bg-canvas");
    } else {
      state.selected.delete(path);
      if (row) row.classList.remove("bg-canvas");
    }
    updateSelectionUI();
  }

  function clearSelection() {
    state.selected.clear();
    updateSelectionUI();
    // Uncheck visible checkboxes
    var boxes = document.querySelectorAll("#fm-content input[type=checkbox]");
    Array.prototype.forEach.call(boxes, function (b) {
      b.checked = false;
      var row = b.closest(".group");
      if (row) row.classList.remove("bg-canvas");
    });
  }

  function updateSelectionUI() {
    var count = state.selected.size;
    var countEl = $("fm-count");
    var submit = $("fm-submit");
    if (countEl) countEl.textContent = String(count);
    if (submit) submit.disabled = count === 0;
  }

  // --- Navigation ------------------------------------------------------------
  function navigate(path) {
    if (state.loading) return;
    state.loading = true;
    setBusy(true);

    browse(path)
      .then(function (data) {
        state.currentPath = data.path || "";
        state.parent = data.parent;
        renderBreadcrumb(data);
        renderContent(data);

        var up = $("fm-up");
        if (up) up.disabled = data.is_root;
      })
      .catch(function () {
        /* handled in renderContent for non-ok; network errors below */
        var content = $("fm-content");
        if (content) {
          content.innerHTML =
            '<div class="flex h-full items-center justify-center text-sm text-red-500">Kesalahan jaringan.</div>';
        }
      })
      .finally(function () {
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

  // --- Mobile tree drawer ----------------------------------------------------
  function toggleTree(show) {
    var panel = $("fm-tree-panel");
    var backdrop = $("fm-tree-backdrop");
    if (!panel) return;
    if (show) {
      panel.classList.remove("-translate-x-full");
      if (backdrop) backdrop.classList.remove("hidden");
    } else {
      panel.classList.add("-translate-x-full");
      if (backdrop) backdrop.classList.add("hidden");
    }
  }

  // --- Submit ----------------------------------------------------------------
  function onSubmit(e) {
    var form = $("fm-form");
    var holder = $("fm-selected-inputs");
    if (!form || !holder) return;
    holder.innerHTML = "";
    state.selected.forEach(function (p) {
      var input = document.createElement("input");
      input.type = "hidden";
      input.name = "paths";
      input.value = p;
      holder.appendChild(input);
    });
    // Allow normal POST submission.
  }

  // --- Utils -----------------------------------------------------------------
  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // --- Init ------------------------------------------------------------------
  function init(opts) {
    opts = opts || {};
    state.projectId = opts.projectId;
    state.addPathsAction = opts.addPathsAction || "";

    var form = $("fm-form");
    if (form) {
      form.action = state.addPathsAction;
      form.addEventListener("submit", onSubmit);
    }

    var initialized = false;
    document.addEventListener("quenza:modal-open", function (ev) {
      if (ev.detail && ev.detail.id === "modal-file-manager" && !initialized) {
        initialized = true;
        renderQuickRoots();
        navigate("");
      }
    });
  }

  window.QuenzaFileManager = {
    init: init,
    navigate: navigate,
    goUp: goUp,
    refresh: refresh,
    clearSelection: clearSelection,
    toggleTree: toggleTree,
  };
})();
