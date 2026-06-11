/* ==========================================================================
   Quenza Cloud Toolkit - destinations.js
   Handles dynamic field visibility for the create/edit destination modals.
   Only the active type's fields are enabled so the form submits a clean
   config for the selected destination type.
   ========================================================================== */

(function () {
  "use strict";

  function setEnabled(container, enabled) {
    if (!container) return;
    var fields = container.querySelectorAll("input, textarea, select");
    Array.prototype.forEach.call(fields, function (f) {
      f.disabled = !enabled;
    });
    container.style.display = enabled ? "" : "none";
  }

  // --- Create modal ----------------------------------------------------------
  function showFields(typeKey) {
    var groups = document.querySelectorAll(".quenza-dest-fields");
    Array.prototype.forEach.call(groups, function (g) {
      setEnabled(g, g.getAttribute("data-type") === typeKey);
    });
  }

  function initCreate() {
    // Ensure only the checked type's fields are enabled initially.
    var checked = document.querySelector(".quenza-dest-type:checked");
    var groups = document.querySelectorAll(".quenza-dest-fields");
    var activeKey = checked ? checked.value : null;
    Array.prototype.forEach.call(groups, function (g) {
      var isActive = g.getAttribute("data-type") === activeKey;
      setEnabled(g, isActive);
    });
  }

  // --- Edit modal ------------------------------------------------------------
  function openEdit(id, name, typeKey) {
    var form = document.getElementById("edit-dest-form");
    var nameInput = document.getElementById("edit-dest-name");
    var typeLabel = document.getElementById("edit-dest-type-label");
    if (!form) return;

    form.action = "/destinations/" + id + "/update";
    if (nameInput) nameInput.value = name || "";
    if (typeLabel) typeLabel.textContent = (typeKey || "").toUpperCase();

    // Toggle field groups: enable only the matching type.
    var groups = document.querySelectorAll(".quenza-edit-fields");
    Array.prototype.forEach.call(groups, function (g) {
      setEnabled(g, g.getAttribute("data-type") === typeKey);
    });

    window.QuenzaModal && QuenzaModal.open("modal-edit-dest");
  }

  document.addEventListener("DOMContentLoaded", function () {
    initCreate();
  });

  window.QuenzaDest = {
    showFields: showFields,
    openEdit: openEdit,
  };
})();
