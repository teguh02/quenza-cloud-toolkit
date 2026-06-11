/* Quenza — realtime monitoring of background backup jobs.
 *
 * Polls GET /api/jobs/active every `pollMs` and renders progress cards into
 * #active-jobs-list. When a previously-active job disappears (i.e. it
 * finished), the page is reloaded once so the History table reflects the
 * final result.
 */
(function () {
  "use strict";

  var POLL_MS = 2500;
  var listEl = null;
  var panelEl = null;
  var timer = null;
  var knownIds = []; // job ids seen as active on the previous tick
  var reloading = false;

  function esc(value) {
    var div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
  }

  function clamp(pct) {
    var n = parseInt(pct, 10);
    if (isNaN(n)) return 0;
    if (n < 0) return 0;
    if (n > 100) return 100;
    return n;
  }

  function triggerLabel(trigger) {
    if (trigger === "schedule") return "Terjadwal";
    if (trigger === "manual") return "Manual";
    return trigger || "";
  }

  function cardHtml(job) {
    var pct = clamp(job.progress);
    var queued = job.status === "queued";
    var step =
      job.total_steps && job.step_index
        ? "Langkah " + job.step_index + "/" + job.total_steps
        : "";
    var statusText = queued ? "Menunggu antrean…" : job.current_step || "Memproses…";

    return (
      '<div class="rounded-2xl border border-line bg-canvas p-4">' +
      '<div class="mb-2 flex items-center justify-between gap-3">' +
      '<div class="min-w-0">' +
      '<p class="truncate text-sm font-semibold text-heading">' +
      esc(job.project_name || "Project #" + job.project_id) +
      "</p>" +
      '<p class="truncate text-xs text-secondary">' +
      esc(statusText) +
      "</p>" +
      "</div>" +
      '<div class="flex shrink-0 items-center gap-2">' +
      (step
        ? '<span class="text-[11px] font-medium text-label">' + esc(step) + "</span>"
        : "") +
      '<span class="rounded-full bg-pastel-blue px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-blue-500">' +
      esc(triggerLabel(job.trigger)) +
      "</span>" +
      "</div>" +
      "</div>" +
      '<div class="flex items-center gap-3">' +
      '<div class="h-2 flex-1 overflow-hidden rounded-full bg-line">' +
      '<div class="h-full rounded-full bg-brand-gradient transition-all duration-500 ease-quenza" style="width:' +
      pct +
      '%"></div>' +
      "</div>" +
      '<span class="w-10 shrink-0 text-right text-xs font-semibold text-heading">' +
      pct +
      "%</span>" +
      "</div>" +
      "</div>"
    );
  }

  function render(jobs) {
    if (!panelEl || !listEl) return;

    if (!jobs.length) {
      panelEl.classList.add("hidden");
      listEl.innerHTML = "";
    } else {
      listEl.innerHTML = jobs.map(cardHtml).join("");
      panelEl.classList.remove("hidden");
    }

    // Detect jobs that were active before but are gone now -> finished.
    var currentIds = jobs.map(function (j) {
      return j.id;
    });
    var finished = knownIds.some(function (id) {
      return currentIds.indexOf(id) === -1;
    });
    knownIds = currentIds;

    if (finished && !reloading) {
      reloading = true;
      // Give the final DB write a moment, then refresh to show results.
      setTimeout(function () {
        window.location.reload();
      }, 600);
    }
  }

  function poll() {
    fetch("/api/jobs/active", { headers: { Accept: "application/json" } })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        render(Array.isArray(data.jobs) ? data.jobs : []);
      })
      .catch(function () {
        /* transient errors are ignored; next tick retries */
      });
  }

  function init(opts) {
    opts = opts || {};
    POLL_MS = opts.pollMs || POLL_MS;
    listEl = document.getElementById("active-jobs-list");
    panelEl = document.getElementById("active-jobs");
    if (!listEl || !panelEl) return; // panel not present on this page

    poll();
    timer = window.setInterval(poll, POLL_MS);

    // Pause polling when the tab is hidden to save resources.
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) {
        if (timer) {
          window.clearInterval(timer);
          timer = null;
        }
      } else if (!timer) {
        poll();
        timer = window.setInterval(poll, POLL_MS);
      }
    });
  }

  window.QuenzaJobs = { init: init };
})();
