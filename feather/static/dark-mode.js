/**
 * Dark Mode Toggle Utility
 * ========================
 * Toggles .dark class on <html> when clicking [data-toggle-dark-mode] elements.
 * Swaps visibility of [data-light-icon] and [data-dark-icon] children.
 *
 * Usage:
 *   <button data-toggle-dark-mode>
 *       <span data-light-icon class="material-symbols-outlined">bedtime</span>
 *       <span data-dark-icon class="material-symbols-outlined hidden">sunny</span>
 *   </button>
 *
 * Apps should implement their own persistence strategy (localStorage, user
 * preference in DB, etc.) by reading document.documentElement.classList.contains('dark').
 */
(function() {
  "use strict";

  function updateIcons() {
    var isDark = document.documentElement.classList.contains("dark");
    document.querySelectorAll("[data-toggle-dark-mode]").forEach(function(btn) {
      var lightIcon = btn.querySelector("[data-light-icon]");
      var darkIcon = btn.querySelector("[data-dark-icon]");
      if (lightIcon) lightIcon.classList.toggle("hidden", isDark);
      if (darkIcon) darkIcon.classList.toggle("hidden", !isDark);
    });
  }

  document.addEventListener("click", function(e) {
    var btn = e.target.closest("[data-toggle-dark-mode]");
    if (!btn) return;
    document.documentElement.classList.toggle("dark");
    updateIcons();
  });

  // Sync icons on load (in case .dark class was set server-side or by another script)
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", updateIcons);
  } else {
    updateIcons();
  }
})();
