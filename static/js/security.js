/* Quenza Cloud Toolkit - security.js */

(function () {
  "use strict";

  var state = {
    currentTab: "system",
    loading: false,
    actionType: null, // "kill", "firewall_rule"
    actionTarget: null // e.g. pid
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

  function init() {
    switchTab("system");
  }

  function switchTab(tab) {
    state.currentTab = tab;
    var tabs = ["system", "processes", "firewall"];
    var titles = {
      "system": "System Information",
      "processes": "Task Manager",
      "firewall": "Firewall Rules"
    };
    
    $("tab-title").textContent = titles[tab];
    
    if (tab === "firewall") {
      $("btn-add-rule").classList.remove("hidden");
    } else {
      $("btn-add-rule").classList.add("hidden");
    }

    tabs.forEach(function(t) {
      var btn = $("tab-btn-" + t);
      if (!btn) return;
      if (t === tab) {
        btn.classList.add("bg-canvas", "border", "border-brand-teal/30");
        btn.classList.remove("border-transparent", "hover:bg-canvas");
      } else {
        btn.classList.remove("bg-canvas", "border-brand-teal/30");
        btn.classList.add("border-transparent", "hover:bg-canvas");
      }
    });

    refresh();
  }

  function refresh() {
    state.loading = true;
    var content = $("tab-content");
    content.innerHTML = '<div class="flex h-full items-center justify-center text-sm text-secondary">Memuat data...</div>';

    var url = "/api/security/" + state.currentTab;
    apiGet(url).then(function(res) {
      if (!res.ok) {
        content.innerHTML = '<div class="text-sm text-red-500 p-4">Error: ' + escapeHtml(res.error) + '</div>';
        return;
      }
      renderData(res.data);
    }).catch(function(e) {
      content.innerHTML = '<div class="text-sm text-red-500 p-4">Kesalahan jaringan: ' + e + '</div>';
    }).finally(function() {
      state.loading = false;
    });
  }

  function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    var k = 1024, dm = 2, sizes = ['B', 'KB', 'MB', 'GB', 'TB'], i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
  }

  function renderData(data) {
    var content = $("tab-content");
    content.innerHTML = "";

    if (state.currentTab === "system") {
      var html = '<div class="space-y-6">';
      
      // Basic OS Info
      html += '<div class="grid grid-cols-2 gap-4"><div class="rounded-xl border border-line bg-canvas/30 p-4"><p class="text-xs text-secondary mb-1">OS</p><p class="font-bold text-heading">' + escapeHtml(data.os) + ' ' + escapeHtml(data.release) + '</p></div>';
      html += '<div class="rounded-xl border border-line bg-canvas/30 p-4"><p class="text-xs text-secondary mb-1">CPU Load</p><p class="font-bold text-heading">' + data.cpu_percent + '%</p></div></div>';
      
      // RAM & Disk Bars
      var renderBar = function(label, used, total, pct, color) {
        return '<div class="rounded-xl border border-line bg-canvas/30 p-4">' +
               '<div class="flex justify-between mb-2"><p class="text-sm font-bold text-heading">' + label + '</p><p class="text-xs text-secondary">' + formatBytes(used) + ' / ' + formatBytes(total) + ' (' + pct + '%)</p></div>' +
               '<div class="w-full bg-surface rounded-full h-2.5 overflow-hidden border border-line"><div class="' + color + ' h-2.5" style="width: ' + pct + '%"></div></div>' +
               '</div>';
      };
      html += renderBar("RAM Usage", data.ram.used, data.ram.total, data.ram.percent, data.ram.percent > 85 ? "bg-red-500" : "bg-blue-500");
      html += renderBar("Disk Usage (" + escapeHtml(data.disk.path) + ")", data.disk.used, data.disk.total, data.disk.percent, data.disk.percent > 85 ? "bg-red-500" : "bg-green-500");
      
      // IPs
      html += '<div class="rounded-xl border border-line bg-canvas/30 p-4"><p class="text-sm font-bold text-heading mb-3">Network Interfaces</p><div class="space-y-2">';
      if (data.ips.length === 0) html += '<p class="text-xs text-secondary">Tidak ada data IP.</p>';
      data.ips.forEach(function(ip) {
        html += '<div class="flex justify-between text-sm border-b border-line pb-1 last:border-0 last:pb-0"><span class="text-secondary">' + escapeHtml(ip.interface) + '</span><span class="font-mono text-heading">' + escapeHtml(ip.ip) + '</span></div>';
      });
      html += '</div></div>';

      html += '</div>';
      content.innerHTML = html;
    } 
    else if (state.currentTab === "processes") {
      var table = '<div class="w-full overflow-x-auto rounded-xl border border-line"><table class="w-full text-left text-sm"><thead class="text-xs uppercase tracking-wider text-label border-b border-line bg-canvas/80"><tr><th class="px-4 py-3">PID</th><th class="px-4 py-3">Name</th><th class="px-4 py-3">User</th><th class="px-4 py-3">CPU %</th><th class="px-4 py-3">RAM %</th><th class="px-4 py-3 text-right">Aksi</th></tr></thead><tbody class="divide-y divide-line">';
      data.forEach(function(p) {
        table += '<tr class="hover:bg-canvas/30 transition-colors"><td class="px-4 py-3 font-mono text-secondary">' + p.pid + '</td><td class="px-4 py-3 font-bold text-heading">' + escapeHtml(p.name) + '</td><td class="px-4 py-3 text-secondary">' + escapeHtml(p.user) + '</td><td class="px-4 py-3">' + p.cpu + '%</td><td class="px-4 py-3">' + p.ram + '%</td>';
        table += '<td class="px-4 py-3 text-right"><button onclick="SecurityMgmt.promptKill(' + p.pid + ', \'' + escapeHtml(p.name).replace(/'/g, "\\'") + '\')" class="rounded-lg bg-red-50 px-3 py-1.5 text-[11px] uppercase tracking-wider font-bold text-red-600 hover:bg-red-100 transition-colors">Kill</button></td></tr>';
      });
      table += '</tbody></table></div>';
      content.innerHTML = table;
    }
    else if (state.currentTab === "firewall") {
      if (data.length === 0) {
         content.innerHTML = '<div class="flex h-full items-center justify-center text-sm text-label p-4">Tidak ada aturan firewall terbaca.</div>';
         return;
      }
      var list = el("div", "space-y-2");
      data.forEach(function(rule) {
         var row = el("div", "rounded-xl border border-line bg-canvas/30 p-4 hover:bg-canvas transition-colors");
         row.innerHTML = '<p class="font-mono text-xs text-heading break-words whitespace-pre-wrap">' + escapeHtml(rule.raw) + '</p>';
         list.appendChild(row);
      });
      
      var note = el("div", "mb-4 rounded-xl border border-blue-100 bg-blue-50/50 p-4");
      note.innerHTML = '<h3 class="text-sm font-bold text-blue-800 mb-1">Catatan Firewall</h3><p class="text-xs text-blue-700 leading-relaxed">Fitur hapus (Delete Rule) via UI ini hanya dapat menghapus rules spesifik yang memiliki penamaan "Quenza". Rule bawaan OS lainnya tidak akan terpengaruh demi keselamatan server.</p>';
      
      content.appendChild(note);
      content.appendChild(list);
    }
  }

  function promptKill(pid, name) {
    state.actionType = "kill";
    state.actionTarget = pid;
    $("action-modal-title").textContent = "Konfirmasi Kill Task";
    $("action-modal-desc").textContent = "Anda akan menghentikan secara paksa proses PID " + pid + " (" + name + "). Masukkan Master Password untuk otorisasi.";
    $("firewall-inputs").classList.add("hidden");
    $("sec-master-password").value = "";
    $("sec-action-btn").textContent = "Kill Process";
    QuenzaModal.open("modal-security-action");
    setTimeout(function() { $("sec-master-password").focus(); }, 100);
  }

  function showFirewallAdd() {
    state.actionType = "firewall_rule";
    $("action-modal-title").textContent = "Tambah / Ubah Rule Firewall";
    $("action-modal-desc").textContent = "Aturan firewall dapat memutus koneksi remote Anda. Hati-hati. Masukkan Master Password untuk otorisasi.";
    $("firewall-inputs").classList.remove("hidden");
    $("sec-master-password").value = "";
    $("sec-action-btn").textContent = "Simpan Rule";
    QuenzaModal.open("modal-security-action");
    setTimeout(function() { $("fw-port").focus(); }, 100);
  }

  function executeAction() {
    var pass = $("sec-master-password").value;
    if (!pass) return;

    var btn = $("sec-action-btn");
    var ogText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Loading...";

    var payload = { master_password: pass };
    var url = "";

    if (state.actionType === "kill") {
      url = "/api/security/process/" + state.actionTarget + "/kill";
    } else if (state.actionType === "firewall_rule") {
      url = "/api/security/firewall/rule";
      payload.port = parseInt($("fw-port").value, 10);
      payload.protocol = $("fw-protocol").value;
      payload.action = $("fw-action").value;
      if (!payload.port) {
        alert("Port harus diisi.");
        btn.disabled = false; btn.textContent = ogText; return;
      }
    }

    apiPost(url, payload).then(function(res) {
      if (res.ok) {
        QuenzaModal.close("modal-security-action");
        refresh();
      } else {
        alert("Gagal: " + res.error);
      }
    }).catch(function(e) {
      alert("Kesalahan: " + e);
    }).finally(function() {
      btn.disabled = false;
      btn.textContent = ogText;
    });
  }

  window.SecurityMgmt = {
    init: init,
    switchTab: switchTab,
    refresh: refresh,
    promptKill: promptKill,
    showFirewallAdd: showFirewallAdd,
    executeAction: executeAction
  };
})();
