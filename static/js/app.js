/* ==========================================================================
   Quenza Cloud Toolkit - app.js
   Phase 1 interactivity:
     * Mobile sidebar drawer (open/close + backdrop)
     * Password visibility toggle on the login page
   ========================================================================== */

(function () {
  "use strict";

  // --- Mobile sidebar drawer -------------------------------------------------
  function initSidebar() {
    var toggle = document.getElementById("quenza-menu-toggle");
    var sidebar = document.getElementById("quenza-sidebar");
    var backdrop = document.getElementById("quenza-backdrop");

    if (!sidebar) return;

    function openSidebar() {
      sidebar.classList.add("is-open");
      if (backdrop) backdrop.classList.remove("hidden");
      document.body.classList.add("quenza-no-scroll");
    }

    function closeSidebar() {
      sidebar.classList.remove("is-open");
      if (backdrop) backdrop.classList.add("hidden");
      document.body.classList.remove("quenza-no-scroll");
    }

    if (toggle) {
      toggle.addEventListener("click", function () {
        if (sidebar.classList.contains("is-open")) {
          closeSidebar();
        } else {
          openSidebar();
        }
      });
    }

    if (backdrop) {
      backdrop.addEventListener("click", closeSidebar);
    }

    // Close on Escape
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeSidebar();
    });

    // Reset state when resizing up to desktop
    window.addEventListener("resize", function () {
      if (window.innerWidth >= 1024) closeSidebar();
    });
  }

  // --- Login password toggle -------------------------------------------------
  function initPasswordToggle() {
    var btn = document.getElementById("toggle-password");
    var input = document.getElementById("master_password");
    var eyeOpen = document.getElementById("eye-open");
    var eyeClosed = document.getElementById("eye-closed");

    if (!btn || !input) return;

    btn.addEventListener("click", function () {
      var isPassword = input.type === "password";
      input.type = isPassword ? "text" : "password";
      if (eyeOpen) eyeOpen.classList.toggle("hidden", isPassword);
      if (eyeClosed) eyeClosed.classList.toggle("hidden", !isPassword);
      btn.setAttribute(
        "aria-label",
        isPassword ? "Sembunyikan password" : "Tampilkan password"
      );
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initSidebar();
    initPasswordToggle();
  });
})();
