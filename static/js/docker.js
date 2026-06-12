/* ==========================================================================
   Quenza Cloud Toolkit - docker.js
   Docker management logic.
   ========================================================================== */

(function () {
  "use strict";

  var state = {
    hostId: null,
    currentTab: "containers", // containers, images, volumes, networks
    loading: false,
    actionTarget: null,
    actionType: null
  };

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

  function apiGet(url) {
    return fetch(url, { headers: { Accept: "application/json" } }).then(function (r) {
      if (!r.ok) throw new Error("API error " + r.status);
      return r.json();
    });
  }

  function apiPost(url, payload) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (r) {
      if (!r.ok) throw new Error("API error " + r.status);
      return r.json();
    });
  }

  function init(hostId) {
    state.hostId = hostId;
    switchTab("containers");
  }

  function selectHost(hostId) {
    state.hostId = hostId;
    document.querySelectorAll('[id^="host-btn-"]').forEach(function(btn) {
      if (btn.id === "host-btn-" + hostId) {
        btn.classList.add("bg-canvas", "border", "border-brand-teal/30");
        btn.classList.remove("hover:bg-canvas");
      } else {
        btn.classList.remove("bg-canvas", "border", "border-brand-teal/30");
        btn.classList.add("hover:bg-canvas");
      }
    });
    refresh();
  }

  function switchTab(tab) {
    state.currentTab = tab;
    var tabs = ["containers", "images", "volumes", "networks"];
    tabs.forEach(function(t) {
      var btn = $("tab-" + t);
      if (!btn) return;
      if (t === tab) {
        btn.className = "shrink-0 rounded-lg px-4 py-2 text-sm font-semibold transition-colors bg-brand-teal/10 text-brand-teal";
      } else {
        btn.className = "shrink-0 rounded-lg px-4 py-2 text-sm font-semibold text-secondary hover:bg-canvas hover:text-heading transition-colors";
      }
    });
    refresh();
  }

  function refresh() {
    if (!state.hostId) return;
    state.loading = true;
    var content = $("tab-content");
    if (content) content.innerHTML = '<div class="flex h-full items-center justify-center text-sm text-secondary">Memuat data...</div>';

    var url = "/api/docker/" + state.hostId + "/" + state.currentTab;
    apiGet(url).then(function(data) {
      if (!data.ok) {
        content.innerHTML = '<div class="text-sm text-red-500 p-4">Error: ' + escapeHtml(data.error) + '</div>';
        return;
      }
      renderData(data);
    }).catch(function(e) {
      content.innerHTML = '<div class="text-sm text-red-500 p-4">Kesalahan jaringan: ' + e + '</div>';
    }).finally(function() {
      state.loading = false;
    });
  }

  function renderData(data) {
    var content = $("tab-content");
    content.innerHTML = "";

    var iconRemove = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>';

    if (state.currentTab === "containers") {
      var arr = data.containers || [];
      if (arr.length === 0) {
        content.innerHTML = '<div class="flex h-full items-center justify-center text-sm text-label p-4">Tidak ada kontainer.</div>';
        return;
      }
      var list = el("div", "space-y-3");
      arr.forEach(function(c) {
        var row = el("div", "flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-2xl border border-line bg-canvas/30 p-4 transition-colors hover:bg-canvas");
        var left = el("div", "min-w-0");
        left.innerHTML = '<p class="font-bold text-heading truncate">' + escapeHtml(c.name) + '</p>' +
                         '<p class="text-[11px] text-secondary font-mono mt-1 truncate" title="' + escapeHtml(c.image) + '">' + escapeHtml(c.image) + ' | ' + c.short_id + '</p>';
        
        var right = el("div", "flex items-center justify-between sm:justify-end gap-4 shrink-0");
        var statusColor = c.status === "running" ? "bg-pastel-green text-green-700 border-green-200" : (c.status === "exited" ? "bg-canvas text-secondary border-line" : "bg-red-50 text-red-600 border-red-200");
        var statusBadge = el("span", "rounded-lg border px-2 py-1 text-[10px] font-bold uppercase tracking-wider " + statusColor);
        statusBadge.textContent = c.status;
        right.appendChild(statusBadge);

        var iconStop = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect></svg>';
        var iconRestart = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>';
        var iconStart = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>';

        var actions = el("div", "flex gap-1");
        if (c.status === "running") {
          actions.appendChild(makeBtn("Stop", "stop", c.id, "text-orange-600 hover:bg-orange-50", iconStop));
          actions.appendChild(makeBtn("Restart", "restart", c.id, "text-blue-600 hover:bg-blue-50", iconRestart));
        } else {
          actions.appendChild(makeBtn("Start", "start", c.id, "text-green-600 hover:bg-green-50", iconStart));
        }
        actions.appendChild(makeBtn("Remove", "remove", c.id, "text-red-600 hover:bg-red-50", iconRemove));
        right.appendChild(actions);

        row.appendChild(left);
        row.appendChild(right);
        list.appendChild(row);
      });
      content.appendChild(list);
    } else if (state.currentTab === "images") {
       var arr = data.images || [];
       if (arr.length === 0) {
         content.innerHTML = '<div class="flex h-full items-center justify-center text-sm text-label p-4">Tidak ada images.</div>';
         return;
       }
       var list = el("div", "grid grid-cols-1 md:grid-cols-2 gap-3");
       arr.forEach(function(i) {
         var row = el("div", "flex items-center justify-between rounded-xl border border-line bg-canvas/30 p-4 transition-colors hover:bg-canvas");
         row.innerHTML = '<div class="min-w-0"><p class="font-bold text-heading truncate">' + escapeHtml((i.tags && i.tags.length > 0) ? i.tags[0] : i.short_id) + '</p>' +
                         '<p class="text-[11px] text-secondary mt-1">Size: ' + (i.size / 1024 / 1024).toFixed(2) + ' MB | ID: ' + escapeHtml(i.short_id) + '</p></div>';
         var right = el("div", "shrink-0 ml-4");
         right.appendChild(makeBtn("Remove", "remove", i.id, "text-red-600 hover:bg-red-50 hover:text-red-700", iconRemove));
         row.appendChild(right);
         list.appendChild(row);
       });
       content.appendChild(list);
    } else if (state.currentTab === "volumes") {
       var arr = data.volumes || [];
       if (arr.length === 0) {
         content.innerHTML = '<div class="flex h-full items-center justify-center text-sm text-label p-4">Tidak ada volumes.</div>';
         return;
       }
       var list = el("div", "grid grid-cols-1 md:grid-cols-2 gap-3");
       arr.forEach(function(v) {
         var row = el("div", "flex items-center justify-between rounded-xl border border-line bg-canvas/30 p-4 transition-colors hover:bg-canvas");
         row.innerHTML = '<div class="min-w-0"><p class="font-bold text-heading truncate" title="' + escapeHtml(v.name) + '">' + escapeHtml(v.name) + '</p>' +
                         '<p class="text-[11px] text-secondary mt-1 truncate">Driver: ' + escapeHtml(v.driver) + '</p></div>';
         var right = el("div", "shrink-0 ml-4");
         right.appendChild(makeBtn("Remove", "remove", v.name, "text-red-600 hover:bg-red-50 hover:text-red-700", iconRemove));
         row.appendChild(right);
         list.appendChild(row);
       });
       content.appendChild(list);
    } else if (state.currentTab === "networks") {
       var arr = data.networks || [];
       if (arr.length === 0) {
         content.innerHTML = '<div class="flex h-full items-center justify-center text-sm text-label p-4">Tidak ada networks.</div>';
         return;
       }
       var list = el("div", "grid grid-cols-1 md:grid-cols-2 gap-3");
       arr.forEach(function(n) {
         var row = el("div", "flex items-center justify-between rounded-xl border border-line bg-canvas/30 p-4 transition-colors hover:bg-canvas");
         row.innerHTML = '<div class="min-w-0"><p class="font-bold text-heading truncate">' + escapeHtml(n.name) + '</p>' +
                         '<p class="text-[11px] text-secondary mt-1">Driver: ' + escapeHtml(n.driver) + ' | Scope: ' + escapeHtml(n.scope) + '</p></div>';
         var right = el("div", "shrink-0 ml-4");
         right.appendChild(makeBtn("Remove", "remove", n.id, "text-red-600 hover:bg-red-50 hover:text-red-700", iconRemove));
         row.appendChild(right);
         list.appendChild(row);
       });
       content.appendChild(list);
    }
  }

  function makeBtn(label, action, id, colorCls, iconSvg) {
    var b = el("button", "flex items-center justify-center rounded-lg p-2 transition-colors border border-transparent hover:border-line focus:outline-none " + colorCls);
    b.title = label;
    b.innerHTML = '<span class="h-4 w-4 block">' + iconSvg + '</span>';
    b.onclick = function() {
      promptAction(id, action);
    };
    return b;
  }

  function promptAction(id, action) {
    state.actionTarget = id;
    state.actionType = action;
    var typeText = state.currentTab === "containers" ? "kontainer" : state.currentTab.slice(0, -1);
    
    $("action-modal-title").textContent = "Konfirmasi " + action.toUpperCase();
    $("action-modal-desc").textContent = "Anda yakin ingin melakukan aksi '" + action + "' pada " + typeText + " ini?";
    
    var btn = $("action-confirm-btn");
    var icon = $("action-modal-icon");
    
    btn.className = "flex-1 rounded-xl px-4 py-2.5 text-sm font-semibold text-white shadow-card hover:shadow-card-hover transition-all";
    if (action === "remove") {
      btn.classList.add("bg-red-500");
      icon.className = "mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-red-50 text-red-500";
    } else if (action === "stop") {
      btn.classList.add("bg-orange-500");
      icon.className = "mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-orange-50 text-orange-500";
    } else {
      btn.classList.add("bg-brand-gradient");
      icon.className = "mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50 text-blue-500";
    }
    
    QuenzaModal.open('modal-docker-action');
  }

  function executeAction() {
    if (!state.actionTarget || !state.actionType) return;
    var btn = $("action-confirm-btn");
    btn.disabled = true;
    btn.textContent = "Loading...";

    var url;
    var payload;
    if (state.currentTab === "containers") {
       url = "/api/docker/" + state.hostId + "/containers/" + state.actionTarget + "/action";
       payload = { action: state.actionType };
    } else {
       url = "/api/docker/" + state.hostId + "/" + state.currentTab + "/remove";
       payload = { resource_id: state.actionTarget };
    }

    apiPost(url, payload).then(function(res) {
      if (res.ok) {
        QuenzaModal.close('modal-docker-action');
        refresh();
      } else {
        alert("Gagal: " + res.error);
      }
    }).catch(function(e) {
      alert("Kesalahan: " + e);
    }).finally(function() {
      btn.disabled = false;
      btn.textContent = "Lanjutkan";
    });
  }

  window.DockerMgmt = {
    init: init,
    selectHost: selectHost,
    switchTab: switchTab,
    refresh: refresh,
    executeAction: executeAction
  };
})();
