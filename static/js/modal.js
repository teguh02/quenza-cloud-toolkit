/* ==========================================================================
   Quenza Cloud Toolkit - modal.js
   Minimal, dependency-free modal controller used across the app.
   Usage:
     QuenzaModal.open('modal-id')
     QuenzaModal.close('modal-id')
   A modal element must have class "quenza-modal" and use Tailwind's
   `hidden`/`flex` toggling for visibility.
   ========================================================================== */

(function () {
  "use strict";

  function open(id) {
    var el = document.getElementById(id);
    if (!el) return;
    el.classList.remove("hidden");
    el.classList.add("flex");
    el.setAttribute("aria-hidden", "false");
    document.body.classList.add("quenza-no-scroll");
    // Focus the first focusable element for accessibility.
    var focusable = el.querySelector(
      "input, textarea, select, button, [tabindex]:not([tabindex='-1'])"
    );
    if (focusable) {
      setTimeout(function () {
        focusable.focus();
      }, 50);
    }
    document.dispatchEvent(
      new CustomEvent("quenza:modal-open", { detail: { id: id } })
    );
  }

  function close(id) {
    var el = document.getElementById(id);
    if (!el) return;
    el.classList.add("hidden");
    el.classList.remove("flex");
    el.setAttribute("aria-hidden", "true");
    document.body.classList.remove("quenza-no-scroll");
    document.dispatchEvent(
      new CustomEvent("quenza:modal-close", { detail: { id: id } })
    );
  }

  function closeAll() {
    var modals = document.querySelectorAll(".quenza-modal");
    Array.prototype.forEach.call(modals, function (m) {
      if (!m.classList.contains("hidden")) close(m.id);
    });
  }

  // Close on Escape.
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeAll();
  });

  window.QuenzaModal = { open: open, close: close, closeAll: closeAll };
})();
