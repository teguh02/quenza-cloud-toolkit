/* Quenza — total size of a project's backup sources (background-computed).
 *
 * Hydrates the #source-size footer on the project detail page, polls the
 * status endpoint while a computation is running, and wires the
 * "Hitung ulang" (recompute) button.
 */
(function () {
  "use strict";

  var POLL_MS = 2500;
  var projectId = null;
  var timer = null;

  var els = {};

  function cache() {
    els.root = document.getElementById("source-size");
    els.value = document.getElementById("source-size-value");
    els.breakdown = document.getElementById("source-size-breakdown");
    els.note = document.getElementById("source-size-note");
    els.button = document.getElementById("source-size-recompute");
    els.spinner = document.getElementById("source-size-spinner");
    els.refreshIcon = document.getElementById("source-size-refresh-icon");
    els.label = document.getElementById("source-size-recompute-label");
  }

  function statusUrl() {
    return "/projects/" + projectId + "/sources/size";
  }
  function recomputeUrl() {
    return "/projects/" + projectId + "/sources/size/recompute";
  }

  function setComputing(on) {
    if (!els.button) return;
    els.button.disabled = on;
    if (els.spinner) els.spinner.classList.toggle("hidden", !on);
    if (els.refreshIcon) els.refreshIcon.classList.toggle("hidden", on);
    if (els.label) els.label.textContent = on ? "Menghitung…" : "Hitung ulang";
    if (els.value) els.value.classList.toggle("animate-pulse", on);
  }

  function breakdownText(d) {
    if (!d.dir_count && !d.file_count && !d.db_count) return "";
    var parts = [d.dir_count + " direktori", d.file_count + " file"];
    var text = parts.join(", ");
    if (d.db_count) text += " · +" + d.db_count + " database (tidak dihitung)";
    return text;
  }

  function render(d) {
    if (!els.value) return;
    var computing = d.status === "computing";

    if (d.status === "done") {
      els.value.textContent = d.total_human;
    } else if (computing) {
      els.value.textContent = "Menghitung…";
    } else if (d.status === "error") {
      els.value.textContent = "Gagal";
    } else {
      els.value.textContent = "—";
    }

    if (els.breakdown) els.breakdown.textContent = breakdownText(d);

    if (els.note) {
      if (d.status === "error" && d.error) {
        els.note.textContent = d.error;
      } else if (d.skipped) {
        els.note.textContent = d.skipped + " item dilewati (tidak terbaca).";
      } else {
        els.note.textContent = "";
      }
    }

    setComputing(computing);
  }

  function poll() {
    fetch(statusUrl(), { headers: { Accept: "application/json" } })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (d) {
        render(d);
        if (d.status !== "computing") {
          stopPolling();
        }
      })
      .catch(function () {
        /* transient; keep polling */
      });
  }

  function startPolling() {
    if (timer) return;
    timer = window.setInterval(poll, POLL_MS);
  }
  function stopPolling() {
    if (timer) {
      window.clearInterval(timer);
      timer = null;
    }
  }

  function recompute() {
    setComputing(true);
    fetch(recomputeUrl(), {
      method: "POST",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (d) {
        render(d);
        startPolling();
      })
      .catch(function () {
        setComputing(false);
      });
  }

  function init(opts) {
    opts = opts || {};
    projectId = opts.projectId;
    if (projectId == null) return;
    cache();
    if (!els.root) return;

    if (els.button) {
      els.button.addEventListener("click", recompute);
    }

    // If the server already says it's computing (auto-triggered on load),
    // start polling and fetch once immediately for a fresh snapshot.
    poll();
    if (opts.status === "computing") {
      startPolling();
    }

    document.addEventListener("visibilitychange", function () {
      if (document.hidden) {
        stopPolling();
      }
    });
  }

  window.QuenzaSize = { init: init };
})();
