/**
 * Dropdown Component
 * ==================
 * Custom styled dropdown with keyboard navigation and form integration.
 *
 * Usage:
 *   <script src="/feather-static/dropdown.js"></script>
 *
 * The script auto-initializes dropdowns on DOMContentLoaded and after HTMX swaps.
 * Call initDropdowns() manually after dynamically adding dropdowns.
 */

(function () {
  "use strict";

  /**
   * Initialize all dropdowns in the given container.
   * @param {HTMLElement} container - Container to search for dropdowns (default: document)
   */
  function initDropdowns(container = document) {
    const dropdowns = container.querySelectorAll("[data-dropdown]");
    dropdowns.forEach(initDropdown);
  }

  /**
   * Initialize a single dropdown.
   * @param {HTMLElement} dropdown - The dropdown container element
   */
  function initDropdown(dropdown) {
    // Skip if already initialized
    if (dropdown.dataset.dropdownInitialized) return;
    dropdown.dataset.dropdownInitialized = "true";

    const trigger = dropdown.querySelector("[data-dropdown-trigger]");
    const options = dropdown.querySelector("[data-dropdown-options]");
    const hiddenInput = dropdown.querySelector('input[type="hidden"]');
    const selectedDisplay = dropdown.querySelector(".dropdown-selected");

    if (!trigger || !options) return;

    let isOpen = false;
    let focusedIndex = -1;

    // Get all option elements
    function getOptions() {
      return Array.from(options.querySelectorAll("[data-value]"));
    }

    // Open dropdown
    function open() {
      isOpen = true;
      options.classList.remove("hidden");
      trigger.setAttribute("aria-expanded", "true");

      // Focus current selection or first option
      const opts = getOptions();
      const currentValue = hiddenInput?.value;
      focusedIndex = opts.findIndex((o) => o.dataset.value === currentValue);
      if (focusedIndex === -1) focusedIndex = 0;
      updateFocus(opts);
    }

    // Close dropdown
    function close() {
      isOpen = false;
      options.classList.add("hidden");
      trigger.setAttribute("aria-expanded", "false");
      focusedIndex = -1;
    }

    // Toggle dropdown
    function toggle() {
      if (isOpen) {
        close();
      } else {
        open();
      }
    }

    // Update visual focus
    function updateFocus(opts) {
      opts.forEach((opt, i) => {
        if (i === focusedIndex) {
          opt.classList.add("dropdown-option-focused");
          opt.scrollIntoView({ block: "nearest" });
        } else {
          opt.classList.remove("dropdown-option-focused");
        }
      });
    }

    // Select an option
    function selectOption(option) {
      const value = option.dataset.value;
      const label = option.querySelector(".dropdown-option-label")?.textContent || value;

      // Update hidden input
      if (hiddenInput) {
        hiddenInput.value = value;
      }

      // Update display
      if (selectedDisplay) {
        selectedDisplay.textContent = label;
        selectedDisplay.classList.remove("text-gray-400", "dark:text-gray-500");
      }

      // Update selected state
      const opts = getOptions();
      opts.forEach((opt) => {
        const isSelected = opt === option;
        opt.classList.toggle("dropdown-option-selected", isSelected);
        opt.setAttribute("aria-selected", isSelected ? "true" : "false");

        // Update checkmark
        const check = opt.querySelector(".dropdown-check");
        if (isSelected && !check) {
          const checkHtml = `<span class="dropdown-check">
            <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fill-rule="evenodd" d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z" clip-rule="evenodd" />
            </svg>
          </span>`;
          opt.insertAdjacentHTML("beforeend", checkHtml);
        } else if (!isSelected && check) {
          check.remove();
        }
      });

      // Dispatch change event
      dropdown.dispatchEvent(
        new CustomEvent("dropdown:change", {
          bubbles: true,
          detail: { value, label },
        })
      );

      close();
    }

    // Event: Click trigger
    trigger.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggle();
    });

    // Event: Click option
    options.addEventListener("click", (e) => {
      const option = e.target.closest("[data-value]");
      if (option) {
        selectOption(option);
      }
    });

    // Event: Keyboard navigation
    trigger.addEventListener("keydown", (e) => {
      const opts = getOptions();

      switch (e.key) {
        case "Enter":
        case " ":
          e.preventDefault();
          if (!isOpen) {
            open();
          } else if (focusedIndex >= 0 && focusedIndex < opts.length) {
            selectOption(opts[focusedIndex]);
          }
          break;

        case "ArrowDown":
          e.preventDefault();
          if (!isOpen) {
            open();
          } else {
            focusedIndex = Math.min(focusedIndex + 1, opts.length - 1);
            updateFocus(opts);
          }
          break;

        case "ArrowUp":
          e.preventDefault();
          if (!isOpen) {
            open();
          } else {
            focusedIndex = Math.max(focusedIndex - 1, 0);
            updateFocus(opts);
          }
          break;

        case "Escape":
          if (isOpen) {
            e.preventDefault();
            close();
            trigger.focus();
          }
          break;

        case "Tab":
          if (isOpen) {
            close();
          }
          break;

        case "Home":
          if (isOpen) {
            e.preventDefault();
            focusedIndex = 0;
            updateFocus(opts);
          }
          break;

        case "End":
          if (isOpen) {
            e.preventDefault();
            focusedIndex = opts.length - 1;
            updateFocus(opts);
          }
          break;
      }
    });

    // Event: Close on outside click
    document.addEventListener("click", (e) => {
      if (isOpen && !dropdown.contains(e.target)) {
        close();
      }
    });
  }

  // Auto-initialize on DOM ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => initDropdowns());
  } else {
    initDropdowns();
  }

  // Re-initialize after HTMX swaps
  document.addEventListener("htmx:afterSwap", (e) => {
    initDropdowns(e.detail.target);
  });

  // Expose globally
  window.initDropdowns = initDropdowns;
})();
