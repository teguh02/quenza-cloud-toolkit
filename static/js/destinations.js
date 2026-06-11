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
  function toggleGdriveUI(typeKey) {
    var isDrive = typeKey === "gdrive";
    var note = document.getElementById("gdrive-oauth-note");
    var generic = document.getElementById("dest-submit-generic");
    var gdriveBtn = document.getElementById("dest-submit-gdrive");
    if (note) note.style.display = isDrive ? "" : "none";
    if (generic) generic.style.display = isDrive ? "none" : "";
    if (gdriveBtn) gdriveBtn.style.display = isDrive ? "" : "none";
  }

  function showFields(typeKey) {
    var groups = document.querySelectorAll(".quenza-dest-fields");
    Array.prototype.forEach.call(groups, function (g) {
      setEnabled(g, g.getAttribute("data-type") === typeKey);
    });
    toggleGdriveUI(typeKey);
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
    toggleGdriveUI(activeKey);
  }

  // Redirect to the Google Drive OAuth connect endpoint, carrying the
  // chosen name + optional folder id as query params.
  function connectGoogle() {
    var form = document.querySelector('#modal-create-dest form');
    var name = "";
    var folder = "";
    if (form) {
      var nameEl = form.querySelector('input[name="name"]');
      if (nameEl) name = nameEl.value.trim();
      // folder_id input lives in the gdrive field group.
      var group = form.querySelector('.quenza-dest-fields[data-type="gdrive"]');
      if (group) {
        var folderEl = group.querySelector('input[name="folder_id"]');
        if (folderEl) folder = folderEl.value.trim();
      }
    }
    var url =
      "/destinations/gdrive/connect?name=" +
      encodeURIComponent(name) +
      "&folder_id=" +
      encodeURIComponent(folder);
    window.location.href = url;
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
    connectGoogle: connectGoogle,
  };
})();
