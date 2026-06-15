/* Quenza Cloud Toolkit - security.js */

(function () {
  "use strict";

  var state = {
    currentTab: "system",
    loading: false,
    actionType: null, // "kill", "firewall_rule", "osscheduler_add", "osscheduler_delete"
    actionTarget: null, // e.g. pid, task_name
    avTargets: []
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
    var tabs = ["system", "processes", "firewall", "antivirus", "osscheduler"];
    var titles = {
      "system": "System Information",
      "processes": "Task Manager",
      "firewall": "Firewall Rules",
      "antivirus": "Antivirus & Scanner",
      "osscheduler": "OS Scheduler (Cron / Task Scheduler)"
    };
    
    $("tab-title").textContent = titles[tab];
    
    if (tab === "firewall") {
      $("btn-add-rule").classList.remove("hidden");
      $("btn-add-rule").textContent = "+ Tambah Rule";
      $("btn-add-rule").setAttribute("onclick", "SecurityMgmt.showFirewallAdd()");
    } else if (tab === "osscheduler") {
      $("btn-add-rule").classList.remove("hidden");
      $("btn-add-rule").textContent = "+ Tambah Tugas";
      $("btn-add-rule").setAttribute("onclick", "SecurityMgmt.showOsSchedulerAdd()");
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
      var iconKill = '<svg class="w-4 h-4 block" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>';
      data.forEach(function(p) {
        table += '<tr class="hover:bg-canvas/30 transition-colors"><td class="px-4 py-3 font-mono text-secondary">' + p.pid + '</td><td class="px-4 py-3 font-bold text-heading">' + escapeHtml(p.name) + '</td><td class="px-4 py-3 text-secondary">' + escapeHtml(p.user) + '</td><td class="px-4 py-3">' + p.cpu + '%</td><td class="px-4 py-3">' + p.ram + '%</td>';
        table += '<td class="px-4 py-3 text-right"><button title="Kill Process" onclick="SecurityMgmt.promptKill(' + p.pid + ', \'' + escapeHtml(p.name).replace(/'/g, "\\'") + '\')" class="inline-flex items-center justify-center p-2 rounded-lg text-red-600 hover:bg-red-50 hover:text-red-700 transition-colors focus:outline-none">' + iconKill + '</button></td></tr>';
      });
      table += '</tbody></table></div>';
      content.innerHTML = table;
    }
    else if (state.currentTab === "firewall") {
      var btnAdd = $("btn-add-rule");
      if (data.length === 1 && data[0].raw && data[0].raw.toLowerCase().indexOf("status: inactive") !== -1) {
          if (btnAdd) btnAdd.classList.add("hidden");
          var msg = '<div class="flex flex-col items-center justify-center text-center p-8 bg-canvas/30 rounded-2xl border border-line h-64">';
          msg += '<svg class="w-12 h-12 text-secondary mb-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path><line x1="9" y1="9" x2="15" y2="15"></line><line x1="15" y1="9" x2="9" y2="15"></line></svg>';
          msg += '<p class="text-sm font-bold text-heading mb-2">Firewall Tidak Aktif</p>';
          msg += '<p class="text-xs text-secondary max-w-md">Untuk menggunakan fitur Firewall Manager, Anda harus mengaktifkannya di server Anda terlebih dahulu. Jalankan perintah <code class="bg-surface px-1 py-0.5 rounded font-mono border border-line">sudo ufw enable</code> di terminal.</p>';
          msg += '</div>';
          content.innerHTML = msg;
          return;
      }
      
      if (btnAdd) btnAdd.classList.remove("hidden");

      if (data.length === 0) {
         content.innerHTML = '<div class="flex h-full items-center justify-center text-sm text-label p-4">Tidak ada aturan firewall terbaca.</div>';
         return;
      }
      var list = el("div", "space-y-2");
      var hasUfwError = false;
      data.forEach(function(rule) {
         if (rule.raw && rule.raw.indexOf("Gagal membaca UFW") !== -1) {
             hasUfwError = true;
         }
         var row = el("div", "rounded-xl border border-line bg-canvas/30 p-4 hover:bg-canvas transition-colors");
         row.innerHTML = '<p class="font-mono text-xs text-heading break-words whitespace-pre-wrap">' + escapeHtml(rule.raw) + '</p>';
         list.appendChild(row);
      });
      
      var note = el("div", "mb-4 rounded-xl border border-blue-100 bg-blue-50/50 p-4");
      note.innerHTML = '<h3 class="text-sm font-bold text-blue-800 mb-1">Catatan Firewall</h3><p class="text-xs text-blue-700 leading-relaxed">Fitur hapus (Delete Rule) via UI ini hanya dapat menghapus rules spesifik yang memiliki penamaan "Quenza". Rule bawaan OS lainnya tidak akan terpengaruh demi keselamatan server.</p>';
      
      content.appendChild(note);
      content.appendChild(list);

      if (hasUfwError) {
          var btnHelp = el("div", "mt-6 text-center");
          btnHelp.innerHTML = '<a href="/help#ufw-permissions" class="inline-flex items-center gap-2 rounded-xl bg-brand-teal px-5 py-2.5 text-sm font-bold text-white shadow-card hover:bg-brand-teal/90 transition-all"><svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path><line x1="12" y1="17" x2="12.01" y2="17"></line></svg> Solusi: Error Permission UFW</a>';
          content.appendChild(btnHelp);
      }
    }
    else if (state.currentTab === "antivirus") {
      var conf = data.config;
      var logs = data.logs;
      var hlt = data.health || {};
      
      var html = '<div class="space-y-6">';

      // ===================== AV HEALTH DASHBOARD =====================
      html += '<div class="space-y-4">';

      // Critical alerts (red)
      if (hlt.alerts && hlt.alerts.length > 0) {
        html += '<div class="flex items-start gap-4 rounded-2xl border border-red-200 bg-red-50 p-4">';
        html += '<div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-red-100 text-red-600">';
        html += '<svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
        html += '</div><div class="min-w-0 flex-1"><p class="text-sm font-bold text-red-900">Peringatan Kritis</p><ul class="mt-1.5 space-y-1">';
        hlt.alerts.forEach(function(a) {
          html += '<li class="flex items-start gap-2 text-xs text-red-800"><span class="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-red-400"></span>' + escapeHtml(a) + '</li>';
        });
        html += '</ul></div></div>';
      }

      // Warnings (amber)
      if (hlt.warnings && hlt.warnings.length > 0) {
        html += '<div class="flex items-start gap-4 rounded-2xl border border-amber-200 bg-amber-50 p-4">';
        html += '<div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-100 text-amber-600">';
        html += '<svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>';
        html += '</div><div class="min-w-0 flex-1"><p class="text-sm font-bold text-amber-900">Perhatian</p><ul class="mt-1.5 space-y-1">';
        hlt.warnings.forEach(function(w) {
          html += '<li class="flex items-start gap-2 text-xs text-amber-800"><span class="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400"></span>' + escapeHtml(w) + '</li>';
        });
        html += '</ul></div></div>';
      }

      // Engine status cards
      if (hlt.engines && hlt.engines.length > 0) {
        html += '<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">';
        hlt.engines.forEach(function(eng) {
          var borderColor = eng.available ? 'border-emerald-200' : 'border-red-200';
          var bgColor = eng.available ? 'bg-emerald-50/50' : 'bg-red-50/50';
          var dotColor = eng.available ? 'bg-emerald-500' : 'bg-red-400';
          var statusText = eng.available ? 'Tersedia' : 'Tidak Tersedia';
          var statusColor = eng.available ? 'text-emerald-700' : 'text-red-600';

          html += '<div class="rounded-xl border ' + borderColor + ' ' + bgColor + ' p-4">';
          html += '<div class="flex items-center gap-3 mb-2">';
          html += '<span class="relative flex h-3 w-3">';
          if (eng.available) {
            html += '<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>';
          }
          html += '<span class="relative inline-flex h-3 w-3 rounded-full ' + dotColor + '"></span></span>';
          html += '<span class="text-sm font-bold text-heading">' + escapeHtml(eng.name) + '</span>';
          html += '<span class="ml-auto text-xs font-semibold ' + statusColor + '">' + statusText + '</span>';
          html += '</div>';
          html += '<p class="text-xs text-secondary pl-6">' + escapeHtml(eng.detail) + '</p>';
          html += '</div>';
        });
        html += '</div>';
      }

      // Stats row: last scan + quarantine + targets
      html += '<div class="grid grid-cols-2 gap-3 sm:grid-cols-4">';

      // Last scan stat
      var scanLabel = '-';
      var scanSub = 'Belum pernah scan';
      if (hlt.last_scan) {
        var ls = hlt.last_scan;
        if (ls.hours_ago < 1) scanLabel = '<1 jam';
        else if (ls.hours_ago < 24) scanLabel = Math.round(ls.hours_ago) + ' jam';
        else scanLabel = Math.round(ls.hours_ago / 24) + ' hari';
        scanLabel += ' lalu';
        scanSub = ls.files_scanned + ' file, ' + (ls.duration_ms / 1000).toFixed(1) + 's';
        if (ls.status === 'failed') scanSub = '⚠ ' + ls.threats_found + ' ancaman ditemukan';
      }
      html += '<div class="rounded-xl border border-line bg-canvas/30 p-4 text-center"><p class="text-lg font-extrabold text-heading">' + scanLabel + '</p><p class="mt-1 text-[11px] text-secondary">Scan Terakhir</p><p class="text-[10px] text-label">' + scanSub + '</p></div>';

      // Quarantine stat
      var qCount = hlt.quarantine_count || 0;
      var qColor = qCount > 0 ? 'text-amber-600' : 'text-heading';
      html += '<div class="rounded-xl border border-line bg-canvas/30 p-4 text-center"><p class="text-lg font-extrabold ' + qColor + '">' + qCount + '</p><p class="mt-1 text-[11px] text-secondary">File Karantina</p><p class="text-[10px] text-label">Menunggu tindakan</p></div>';

      // Targets stat
      html += '<div class="rounded-xl border border-line bg-canvas/30 p-4 text-center"><p class="text-lg font-extrabold text-heading">' + (hlt.targets_accessible || 0) + '/' + (hlt.targets_configured || 0) + '</p><p class="mt-1 text-[11px] text-secondary">Target Aktif</p><p class="text-[10px] text-label">Direktori terkonfigurasi</p></div>';

      // YARA rules count
      html += '<div class="rounded-xl border border-line bg-canvas/30 p-4 text-center"><p class="text-lg font-extrabold text-heading">' + (hlt.yara_rules_count || 0) + '</p><p class="mt-1 text-[11px] text-secondary">YARA Rules</p><p class="text-[10px] text-label">File definisi</p></div>';

      html += '</div>'; // End stats row
      html += '</div>'; // End health dashboard

      // Separator
      html += '<hr class="border-line">';
      
      // Control Panel
      html += '<div class="grid grid-cols-1 gap-4 lg:grid-cols-2">';
      html += '<div class="rounded-xl border border-line bg-canvas/30 p-5">';
      html += '<h3 class="text-sm font-bold text-heading mb-4">Pengaturan Antivirus</h3>';
      
      html += '<div class="space-y-4">';
      html += '<label class="flex cursor-pointer items-center justify-between"><span class="text-sm font-semibold text-heading">Aktifkan Auto-Scan (Jadwal)</span><input type="checkbox" id="av-enabled" class="h-5 w-9 accent-brand-teal" ' + (conf.av_enabled ? 'checked' : '') + '></label>';
      html += '<label class="flex cursor-pointer items-center justify-between"><span class="text-sm font-semibold text-heading">Karantina Otomatis</span><input type="checkbox" id="av-auto-quarantine" class="h-5 w-9 accent-brand-teal" ' + (conf.av_auto_quarantine ? 'checked' : '') + '></label>';
      html += '</div>';
      
      html += '<div class="mt-5 pt-5 border-t border-line flex gap-3">';
      html += '<button onclick="SecurityMgmt.saveAvConfig()" class="flex-1 rounded-xl bg-brand-gradient px-4 py-2 text-sm font-bold text-white shadow-card hover:brightness-[1.03] transition-all">Simpan Pengaturan</button>';
      html += '<button onclick="SecurityMgmt.triggerAvScan()" class="flex-1 rounded-xl border border-line bg-surface px-4 py-2 text-sm font-bold text-secondary hover:text-brand-teal hover:border-brand-teal/30 transition-all">Scan Sekarang</button>';
      html += '</div></div>';
      
      // Target paths
      html += '<div class="rounded-xl border border-line bg-canvas/30 p-5">';
      html += '<div class="flex items-center justify-between mb-4">';
      html += '<div>';
      html += '<h3 class="text-sm font-bold text-heading mb-1">Target Direktori Scan</h3>';
      html += '<p class="text-xs text-secondary">Daftar path file atau direktori yang akan dipindai.</p>';
      html += '</div>';
      html += '<button type="button" onclick="QuenzaModal.open(\'modal-file-manager\')" class="inline-flex items-center gap-2 rounded-xl bg-brand-gradient px-3.5 py-2 text-xs font-semibold text-white shadow-card transition-all duration-quenza ease-quenza hover:shadow-card-hover hover:brightness-[1.03]">';
      html += '<svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>';
      html += 'File Explorer</button>';
      html += '</div>';
      
      state.avTargets = conf.av_targets ? conf.av_targets.slice() : [];
      html += '<div id="av-targets-container"></div>';
      
      html += '</div>';
      html += '</div>'; // End grid
      
      // Quarantine Log Table
      html += '<div class="rounded-xl border border-line bg-canvas/30 p-5">';
      html += '<h3 class="text-sm font-bold text-heading mb-4">Brankas Karantina</h3>';
      
      if (logs.length === 0) {
          html += '<p class="text-sm text-secondary p-4 text-center border border-dashed border-line rounded-xl">Belum ada file yang dikarantina.</p>';
      } else {
          var t = '<div class="overflow-x-auto"><table class="w-full text-left text-sm"><thead class="text-xs uppercase tracking-wider text-label border-b border-line"><tr><th class="pb-2">Waktu</th><th class="pb-2">File Asli</th><th class="pb-2">Rule Terdeteksi</th><th class="pb-2">Status</th><th class="pb-2 text-right">Aksi</th></tr></thead><tbody class="divide-y divide-line">';
          logs.forEach(function(l) {
              var badge = '';
              if (l.status === 'quarantined') badge = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-pastel-orange text-orange-600">Dikarantina</span>';
              else if (l.status === 'restored') badge = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-pastel-blue text-blue-600">Dipulihkan</span>';
              else badge = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-canvas text-secondary border border-line">Dihapus</span>';
              
              var d = new Date(l.created_at).toLocaleString();
              
              t += '<tr class="hover:bg-canvas transition-colors"><td class="py-2 text-secondary whitespace-nowrap">' + d + '</td>';
              t += '<td class="py-2 font-mono text-xs max-w-xs truncate text-heading" title="' + escapeHtml(l.original_path) + '">' + escapeHtml(l.original_path) + '</td>';
              t += '<td class="py-2 text-xs text-red-500 font-bold">' + escapeHtml(l.rule_matched) + '</td>';
              t += '<td class="py-2">' + badge + '</td>';
              t += '<td class="py-2 text-right space-x-2">';
              if (l.status === 'quarantined') {
                  t += '<button onclick="SecurityMgmt.avAction(' + l.id + ', \'restore\')" class="text-xs text-brand-teal hover:underline font-bold">Restore</button>';
                  t += '<button onclick="SecurityMgmt.avAction(' + l.id + ', \'delete\')" class="text-xs text-red-500 hover:underline font-bold">Hapus</button>';
              }
              t += '</td></tr>';
          });
          t += '</tbody></table></div>';
          html += t;
      }
      
      html += '</div>';
      
      html += '</div>'; // End space-y-6
      content.innerHTML = html;
      renderAvTargets();
    }
    else if (state.currentTab === "osscheduler") {
      var html = '<div class="space-y-6">';
      
      var note = el("div", "rounded-xl border border-blue-100 bg-blue-50/50 p-4");
      note.innerHTML = '<h3 class="text-sm font-bold text-blue-800 mb-1">Catatan OS Scheduler</h3><p class="text-xs text-blue-700 leading-relaxed">Kelola tugas terjadwal tingkat sistem operasi. Menghapus tugas sistem dapat berakibat fatal. Demi keamanan, Anda disarankan hanya menghapus tugas yang sengaja Anda buat (biasanya dengan prefix <code class="bg-blue-100 px-1 py-0.5 rounded font-mono">Quenza_</code>).</p>';
      
      html += note.outerHTML;
      
      if (data.length === 0) {
        html += '<div class="flex h-32 items-center justify-center text-sm text-label border border-dashed border-line rounded-xl">Tidak ada tugas terjadwal yang ditemukan.</div>';
      } else {
        var table = '<div class="w-full overflow-x-auto rounded-xl border border-line bg-surface"><table class="w-full text-left text-sm"><thead class="text-xs uppercase tracking-wider text-label border-b border-line bg-canvas/80"><tr><th class="px-4 py-3">Nama Tugas</th><th class="px-4 py-3">Jadwal / Waktu</th><th class="px-4 py-3">Perintah</th><th class="px-4 py-3 text-right">Aksi</th></tr></thead><tbody class="divide-y divide-line">';
        data.forEach(function(t) {
          table += '<tr class="hover:bg-canvas/30 transition-colors">';
          table += '<td class="px-4 py-3 font-bold text-heading">' + escapeHtml(t.name) + '</td>';
          table += '<td class="px-4 py-3 font-mono text-xs text-secondary whitespace-nowrap">' + escapeHtml(t.schedule) + '</td>';
          table += '<td class="px-4 py-3 font-mono text-xs text-secondary max-w-xs truncate" title="' + escapeHtml(t.command) + '">' + escapeHtml(t.command) + '</td>';
          
          var iconTrash = '<svg class="w-4 h-4 block" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>';
          table += '<td class="px-4 py-3 text-right"><button title="Hapus Tugas" onclick="SecurityMgmt.promptDeleteOsTask(\'' + escapeHtml(t.raw).replace(/'/g, "\\'") + '\', \'' + escapeHtml(t.name).replace(/'/g, "\\'") + '\')" class="inline-flex items-center justify-center p-2 rounded-lg text-red-600 hover:bg-red-50 hover:text-red-700 transition-colors focus:outline-none">' + iconTrash + '</button></td>';
          table += '</tr>';
        });
        table += '</tbody></table></div>';
        html += table;
      }
      
      html += '</div>';
      content.innerHTML = html;
    }
  }

  function renderAvTargets() {
    var c = $("av-targets-container");
    if (!c) return;
    if (state.avTargets.length === 0) {
      c.innerHTML = '<div class="rounded-2xl border border-dashed border-line bg-canvas px-6 py-6 text-center"><p class="text-sm font-semibold text-heading">Belum ada target direktori.</p><p class="mt-1 text-xs text-secondary">Gunakan <span class="font-semibold text-brand-teal">File Explorer</span> untuk menambahkannya.</p></div>';
      return;
    }
    var html = '<ul class="space-y-2.5 max-h-64 overflow-y-auto pr-2">';
    state.avTargets.forEach(function(t, idx) {
      html += '<li class="flex items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3 transition-colors hover:border-brand-teal/30">';
      html += '<div class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-pastel-blue text-blue-500"><svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg></div>';
      html += '<div class="min-w-0 flex-1"><p class="truncate text-sm font-mono text-heading" title="' + escapeHtml(t) + '">' + escapeHtml(t) + '</p></div>';
      html += '<button type="button" onclick="SecurityMgmt.removeAvTarget(' + idx + ')" class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-secondary hover:bg-red-50 hover:text-red-500 transition-colors"><svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></button>';
      html += '</li>';
    });
    html += '</ul>';
    c.innerHTML = html;
  }

  function addAvTargets(paths) {
    paths.forEach(function(p) {
      if (state.avTargets.indexOf(p) === -1) {
        state.avTargets.push(p);
      }
    });
    renderAvTargets();
  }

  function removeAvTarget(idx) {
    if (idx >= 0 && idx < state.avTargets.length) {
      state.avTargets.splice(idx, 1);
      renderAvTargets();
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
    $("os-scheduler-inputs").classList.add("hidden");
    $("sec-master-password").value = "";
    $("sec-action-btn").textContent = "Simpan Rule";
    QuenzaModal.open("modal-security-action");
    setTimeout(function() { $("fw-port").focus(); }, 100);
  }

  function showOsSchedulerAdd() {
    state.actionType = "osscheduler_add";
    $("action-modal-title").textContent = "Tambah OS Task";
    $("action-modal-desc").textContent = "Tugas ini akan didaftarkan pada jadwal bawaan sistem operasi. Masukkan Master Password untuk otorisasi.";
    $("firewall-inputs").classList.add("hidden");
    $("os-scheduler-inputs").classList.remove("hidden");
    
    $("os-task-name").value = "";
    $("os-task-schedule").value = "";
    $("os-task-command").value = "";
    $("sec-master-password").value = "";
    $("sec-action-btn").textContent = "Simpan Tugas";
    
    QuenzaModal.open("modal-security-action");
    setTimeout(function() { $("os-task-name").focus(); }, 100);
  }

  function promptDeleteOsTask(rawName, friendlyName) {
    state.actionType = "osscheduler_delete";
    state.actionTarget = rawName;
    $("action-modal-title").textContent = "Hapus Tugas";
    $("action-modal-desc").textContent = "Yakin ingin menghapus tugas '" + friendlyName + "'? Masukkan Master Password untuk otorisasi.";
    $("firewall-inputs").classList.add("hidden");
    $("os-scheduler-inputs").classList.add("hidden");
    $("sec-master-password").value = "";
    $("sec-action-btn").textContent = "Hapus Tugas";
    QuenzaModal.open("modal-security-action");
    setTimeout(function() { $("sec-master-password").focus(); }, 100);
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
    } else if (state.actionType === "osscheduler_add") {
      url = "/api/security/os-scheduler/action";
      payload.action = "add";
      payload.name = $("os-task-name").value;
      payload.schedule = $("os-task-schedule").value;
      payload.command = $("os-task-command").value;
      if (!payload.name || !payload.schedule || !payload.command) {
        alert("Semua field (Nama, Jadwal, Perintah) harus diisi.");
        btn.disabled = false; btn.textContent = ogText; return;
      }
    } else if (state.actionType === "osscheduler_delete") {
      url = "/api/security/os-scheduler/action";
      payload.action = "delete";
      payload.name = state.actionTarget;
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

  function saveAvConfig() {
      var enabled = $("av-enabled").checked;
      var autoq = $("av-auto-quarantine").checked;
      var tgs = state.avTargets;
      
      apiPost("/api/security/antivirus/config", {
          av_enabled: enabled,
          av_auto_quarantine: autoq,
          av_targets: tgs
      }).then(function(res) {
          if (res.ok) {
              alert("Pengaturan tersimpan!");
              refresh();
          } else {
              alert("Error: " + res.error);
          }
      }).catch(function(e) {
          alert("Error: " + e);
      });
  }

  function triggerAvScan() {
      apiPost("/api/security/antivirus/scan", {}).then(function(res) {
          if(res.ok) alert(res.message);
          else alert("Error: " + res.error);
      }).catch(function(e) {
          alert("Error: " + e);
      });
  }

  function avAction(id, action) {
      if(!confirm("Yakin ingin " + (action === "restore" ? "memulihkan file ke lokasi asli?" : "menghapus file permanen?"))) return;
      apiPost("/api/security/antivirus/quarantine/" + id, { action: action }).then(function(res) {
          if(res.ok) refresh();
          else alert("Error: " + res.error);
      }).catch(function(e) {
          alert("Error: " + e);
      });
  }

  window.SecurityMgmt = {
    init: init,
    switchTab: switchTab,
    refresh: refresh,
    promptKill: promptKill,
    showFirewallAdd: showFirewallAdd,
    showOsSchedulerAdd: showOsSchedulerAdd,
    promptDeleteOsTask: promptDeleteOsTask,
    executeAction: executeAction,
    saveAvConfig: saveAvConfig,
    triggerAvScan: triggerAvScan,
    avAction: avAction,
    addAvTargets: addAvTargets,
    removeAvTarget: removeAvTarget
  };
})();
