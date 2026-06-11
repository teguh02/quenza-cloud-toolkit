/* ==========================================================================
   Quenza Cloud Toolkit - restore.js
   Drives the passive restore flow:
     1. Select a destination -> fetch its archives (JSON)
     2. Pick an archive (radio)
     3. Enter target dir -> submit (download + extract on the server)
   ========================================================================== */

(function () {
  "use strict";

  var selected = { ref: null, name: null };

  function $(id) {
    return document.getElementById(id);
  }

  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }

  function humanSize(bytes) {
    if (!bytes) return "";
    var units = ["B", "KB", "MB", "GB", "TB"];
    var i = 0;
    var n = bytes;
    while (n >= 1024 && i < units.length - 1) {
      n /= 1024;
      i++;
    }
    return n.toFixed(1) + " " + units[i];
  }

  function setBusy(on) {
    var btn = $("restore-refresh");
    if (btn) {
      btn.classList.toggle("animate-spin", on);
      btn.disabled = on;
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function clearSelection() {
    selected = { ref: null, name: null };
    var sel = $("restore-selected");
    var refIn = $("restore-archive-ref");
    var nameIn = $("restore-archive-name");
    var submit = $("restore-submit");
    if (sel) sel.textContent = "Belum dipilih";
    if (refIn) refIn.value = "";
    if (nameIn) nameIn.value = "";
    if (submit) submit.disabled = true;
  }

  function selectArchive(ref, name) {
    selected = { ref: ref, name: name };
    var sel = $("restore-selected");
    var refIn = $("restore-archive-ref");
    var nameIn = $("restore-archive-name");
    var submit = $("restore-submit");
    if (sel) sel.textContent = name;
    if (refIn) refIn.value = ref;
    if (nameIn) nameIn.value = name;
    if (submit) submit.disabled = false;
  }

  function renderArchives(entries) {
    var container = $("restore-archives");
    if (!container) return;
    container.innerHTML = "";

    if (!entries || entries.length === 0) {
      container.appendChild(
        el(
          "div",
          "flex h-[160px] items-center justify-center rounded-2xl border border-dashed border-line bg-canvas text-sm text-label",
          "Tidak ada arsip di destinasi ini."
        )
      );
      return;
    }

    var list = el("div", "space-y-2");
    entries.forEach(function (entry) {
      var row = el(
        "label",
        "flex cursor-pointer items-center gap-3 rounded-2xl border border-line bg-canvas px-4 py-3 transition-all duration-200 ease-out hover:bg-surface has-[:checked]:border-brand-teal has-[:checked]:bg-surface has-[:checked]:ring-2 has-[:checked]:ring-brand-teal/20"
      );

      var radio = el("input");
      radio.type = "radio";
      radio.name = "archive_choice";
      radio.className = "h-4 w-4 accent-brand-teal";
      radio.addEventListener("change", function () {
        selectArchive(entry.ref, entry.name);
      });
      row.appendChild(radio);

      var icon = el(
        "span",
        "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-pastel-purple text-purple-500",
        '<svg class="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 8v13H3V8"/><rect x="1" y="3" width="22" height="5" rx="1"/><line x1="10" y1="12" x2="14" y2="12"/></svg>'
      );
      row.appendChild(icon);

      var info = el("div", "min-w-0 flex-1");
      info.appendChild(
        el("p", "truncate text-sm font-semibold text-heading", escapeHtml(entry.name))
      );
      var meta = [];
      if (entry.size) meta.push(humanSize(entry.size));
      if (entry.modified) meta.push(entry.modified);
      info.appendChild(
        el("p", "truncate text-[11px] text-label", meta.join(" \u00b7 "))
      );
      row.appendChild(info);

      list.appendChild(row);
    });
    container.appendChild(list);
  }

  function renderError(message) {
    var container = $("restore-archives");
    if (!container) return;
    container.innerHTML = "";
    container.appendChild(
      el(
        "div",
        "flex h-[160px] flex-col items-center justify-center gap-2 rounded-2xl border border-red-100 bg-red-50 text-center",
        '<svg class="h-6 w-6 text-red-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg><p class="px-4 text-sm font-medium text-red-600">' +
          escapeHtml(message) +
          "</p>"
      )
    );
  }

  function renderLoading() {
    var container = $("restore-archives");
    if (!container) return;
    container.innerHTML =
      '<div class="flex h-[160px] items-center justify-center rounded-2xl border border-dashed border-line bg-canvas text-sm text-label">Memuat arsip...</div>';
  }

  function loadArchives() {
    var sel = $("restore-dest");
    var destIdInput = $("restore-dest-id");
    if (!sel) return;
    var destId = sel.value;

    clearSelection();
    if (destIdInput) destIdInput.value = destId;

    if (!destId) {
      var container = $("restore-archives");
      if (container) {
        container.innerHTML =
          '<div class="flex h-[160px] items-center justify-center rounded-2xl border border-dashed border-line bg-canvas text-sm text-label">Pilih destinasi untuk melihat arsip.</div>';
      }
      return;
    }

    renderLoading();
    setBusy(true);

    fetch("/api/restore/archives?destination_id=" + encodeURIComponent(destId), {
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        if (r.status === 401) {
          window.location.href = "/login";
          throw new Error("unauthorized");
        }
        return r.json();
      })
      .then(function (data) {
        if (!data.ok) {
          renderError(data.error || "Gagal memuat arsip.");
          return;
        }
        renderArchives(data.entries);
      })
      .catch(function () {
        renderError("Kesalahan jaringan saat memuat arsip.");
      })
      .finally(function () {
        setBusy(false);
      });
  }

  function onSubmit(form) {
    if (!selected.ref) {
      return false;
    }
    var btn = $("restore-submit");
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="animate-pulse">Memulihkan...</span>';
    }
    return true;
  }

  window.QuenzaRestore = {
    loadArchives: loadArchives,
    onSubmit: onSubmit,
  };
})();
