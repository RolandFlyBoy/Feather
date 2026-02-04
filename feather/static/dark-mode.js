/**
 * Dark Mode Toggle with Cookie Persistence
 * ==========================================
 * 1. On load: reads `dm` cookie and applies .dark class to <html> immediately.
 *    Load this script in <head> to avoid a flash of wrong theme.
 *
 * 2. On click: toggles .dark class and updates the cookie.
 *    Icon visibility is handled by CSS using dark: variants.
 *
 * Usage:
 *   <button data-toggle-dark-mode>
 *       <span class="material-symbols-outlined icon-light">bedtime</span>
 *       <span class="material-symbols-outlined icon-dark">sunny</span>
 *   </button>
 *
 * CSS (in app.css):
 *   .dark-mode-toggle .icon-light { @apply dark:hidden; }
 *   .dark-mode-toggle .icon-dark  { @apply hidden dark:inline; }
 */
(function() {
  "use strict";

  // Restore preference from cookie immediately (before render)
  if (document.cookie.split("; ").some(function(c) { return c === "dm=1"; })) {
    document.documentElement.classList.add("dark");
  }

  // Toggle on click and persist to cookie
  document.addEventListener("click", function(e) {
    var btn = e.target.closest("[data-toggle-dark-mode]");
    if (!btn) return;
    var dark = document.documentElement.classList.toggle("dark");
    document.cookie = dark ? "dm=1;path=/;max-age=31536000;SameSite=Lax" : "dm=0;path=/;max-age=0";
  });
})();
