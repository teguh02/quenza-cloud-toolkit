/* ==========================================================================
   Quenza Cloud Toolkit - dashboard.js
   Phase 2: Backup trend line chart (Chart.js) with Quenza styling,
   transparent area fill, and a 7/30-day range toggle.
   ========================================================================== */

(function () {
  "use strict";

  var QUENZA = {
    teal: "#14B8A6",
    green: "#22C55E",
    danger: "#F43F5E",
    grid: "#E5E9F2",
    label: "#94A3B8",
    heading: "#0F172A",
    font: "Inter, ui-sans-serif, system-ui, sans-serif",
  };

  var chartInstance = null;

  /**
   * Build a vertical gradient fill for an area dataset.
   */
  function makeGradient(ctx, area, hexColor) {
    var g = ctx.createLinearGradient(0, area.top, 0, area.bottom);
    g.addColorStop(0, hexToRgba(hexColor, 0.22));
    g.addColorStop(1, hexToRgba(hexColor, 0.0));
    return g;
  }

  function hexToRgba(hex, alpha) {
    var h = hex.replace("#", "");
    var r = parseInt(h.substring(0, 2), 16);
    var gg = parseInt(h.substring(2, 4), 16);
    var b = parseInt(h.substring(4, 6), 16);
    return "rgba(" + r + "," + gg + "," + b + "," + alpha + ")";
  }

  function buildDatasets(data) {
    return [
      {
        label: "Berhasil",
        data: data.success,
        borderColor: QUENZA.teal,
        borderWidth: 2.5,
        tension: 0.4,
        fill: true,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBackgroundColor: QUENZA.teal,
        pointHoverBorderColor: "#ffffff",
        pointHoverBorderWidth: 2,
        backgroundColor: function (context) {
          var chart = context.chart;
          var chartArea = chart.chartArea;
          if (!chartArea) return "transparent";
          return makeGradient(chart.ctx, chartArea, QUENZA.teal);
        },
      },
      {
        label: "Gagal",
        data: data.failed,
        borderColor: QUENZA.danger,
        borderWidth: 2.5,
        tension: 0.4,
        fill: true,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBackgroundColor: QUENZA.danger,
        pointHoverBorderColor: "#ffffff",
        pointHoverBorderWidth: 2,
        backgroundColor: function (context) {
          var chart = context.chart;
          var chartArea = chart.chartArea;
          if (!chartArea) return "transparent";
          return makeGradient(chart.ctx, chartArea, QUENZA.danger);
        },
      },
    ];
  }

  function chartOptions() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#ffffff",
          titleColor: QUENZA.heading,
          bodyColor: QUENZA.heading,
          borderColor: QUENZA.grid,
          borderWidth: 1,
          padding: 12,
          cornerRadius: 12,
          titleFont: { family: QUENZA.font, weight: "700", size: 12 },
          bodyFont: { family: QUENZA.font, size: 12 },
          boxPadding: 6,
          usePointStyle: true,
          displayColors: true,
        },
      },
      scales: {
        x: {
          grid: { display: false, drawBorder: false },
          ticks: {
            color: QUENZA.label,
            font: { family: QUENZA.font, size: 11 },
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: 8,
          },
        },
        y: {
          beginAtZero: true,
          grid: { color: QUENZA.grid, drawBorder: false },
          border: { display: false },
          ticks: {
            color: QUENZA.label,
            font: { family: QUENZA.font, size: 11 },
            precision: 0,
            padding: 8,
          },
        },
      },
      elements: { line: { borderJoinStyle: "round" } },
    };
  }

  function render(trendByRange, range) {
    var canvas = document.getElementById("backupTrendChart");
    if (!canvas || typeof Chart === "undefined") return;

    var data = trendByRange[range] || trendByRange[7];

    if (chartInstance) {
      chartInstance.data.labels = data.labels;
      chartInstance.data.datasets = buildDatasets(data);
      chartInstance.update();
      return;
    }

    chartInstance = new Chart(canvas.getContext("2d"), {
      type: "line",
      data: { labels: data.labels, datasets: buildDatasets(data) },
      options: chartOptions(),
    });
  }

  function setActiveButton(buttons, active) {
    buttons.forEach(function (btn) {
      var isActive = btn.getAttribute("data-range") === String(active);
      if (isActive) {
        btn.classList.add("bg-surface", "text-heading", "shadow-card");
        btn.classList.remove("text-secondary");
      } else {
        btn.classList.remove("bg-surface", "text-heading", "shadow-card");
        btn.classList.add("text-secondary");
      }
    });
  }

  // Exposed entry point called from the dashboard template.
  window.initQuenzaDashboard = function (trendByRange) {
    var defaultRange = 7;
    render(trendByRange, defaultRange);

    var buttons = Array.prototype.slice.call(
      document.querySelectorAll(".range-btn")
    );
    setActiveButton(buttons, defaultRange);

    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var range = parseInt(btn.getAttribute("data-range"), 10);
        render(trendByRange, range);
        setActiveButton(buttons, range);
      });
    });
  };
})();
