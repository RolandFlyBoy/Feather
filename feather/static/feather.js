/**
 * Feather.js - Lightweight islands framework
 * ~5KB minified, no virtual DOM
 *
 * Features:
 * - Reactive state with automatic DOM updates
 * - Action handlers via data-action attributes
 * - localStorage persistence (persist: true)
 * - Optimistic updates with rollback
 * - Event bus for cross-island communication
 */

const Feather = {
  islands: new Map(),
  instances: new Map(),

  /**
   * Define an island component
   *
   * @param {string} name - Island identifier (matches data-island attribute)
   * @param {object} definition - Island definition
   * @param {object} definition.state - Initial state object
   * @param {boolean|string} definition.persist - Enable localStorage persistence
   * @param {function} definition.init - Called after mount
   * @param {object} definition.actions - Click handlers for data-action
   * @param {function} definition.render - Return selector->value map for DOM updates
   */
  island(name, definition) {
    this.islands.set(name, definition);

    // Auto-mount any existing elements for this island
    // (handles ES modules that load after DOMContentLoaded)
    document.querySelectorAll(`[data-island="${name}"]`).forEach((el) => {
      if (!this.instances.has(el)) {
        this._mount(el, definition);
      }
    });

    return definition;
  },

  /**
   * Initialize all islands on the page
   */
  init() {
    document.querySelectorAll("[data-island]").forEach((el) => {
      const name = el.dataset.island;
      const definition = this.islands.get(name);

      if (!definition) {
        console.warn(`Island "${name}" not found`);
        return;
      }

      this._mount(el, definition);
    });
  },

  /**
   * Mount an island instance
   */
  _mount(el, definition) {
    // EARLY REGISTRATION: Prevent double-mounting from HMR race condition
    // Set a placeholder immediately so concurrent calls see this element as already mounting
    // This fixes race conditions when Vite HMR causes the script to run twice
    this.instances.set(el, null);

    const islandName = el.dataset.island;

    // Build persistence key if enabled
    // persist: true -> "feather:islandName:default"
    // persist: "custom" -> "feather:islandName:custom"
    // data-persist-key="123" -> "feather:islandName:123"
    let persistKey = null;
    if (definition.persist) {
      const suffix = el.dataset.persistKey ||
        (typeof definition.persist === "string" ? definition.persist : "default");
      persistKey = `feather:${islandName}:${suffix}`;
    }

    // Load initial state (merge definition defaults with persisted state)
    let initialState = { ...definition.state };
    if (persistKey) {
      try {
        const saved = localStorage.getItem(persistKey);
        if (saved) {
          initialState = { ...initialState, ...JSON.parse(saved) };
        }
      } catch (e) {
        console.warn(`Failed to load persisted state for ${islandName}:`, e);
      }
    }

    const instance = {
      el,
      data: { ...el.dataset },
      state: initialState,
      $: (selector) => el.querySelector(selector),
      $$: (selector) => el.querySelectorAll(selector),
      api: this._createApiClient(),
      emit: (event, data) => this._emit(event, data),
      on: (event, handler) => this._on(event, handler),

      /**
       * Apply optimistic update with automatic rollback on error.
       *
       * @param {function} mutator - Function that modifies state optimistically
       * @param {function} apiCall - Async function that performs the API request
       * @returns {Promise} - Resolves with API response, rejects on error
       *
       * Usage:
       *   await this.optimistic(
       *     () => { this.state.liked = true; this.state.count++; },
       *     () => this.api.post('/api/posts/123/like')
       *   );
       */
      async optimistic(mutator, apiCall) {
        const snapshot = JSON.stringify(this.state);

        // Apply optimistic update immediately
        mutator();
        this._render();

        try {
          // Execute API call
          const result = await apiCall();
          return result;
        } catch (e) {
          // Rollback on failure
          const restored = JSON.parse(snapshot);
          Object.keys(restored).forEach(key => {
            this.state[key] = restored[key];
          });
          this._render();
          throw e;
        }
      },

      /**
       * Clear persisted state from localStorage
       */
      clearPersisted() {
        if (persistKey) {
          try {
            localStorage.removeItem(persistKey);
          } catch (e) {
            console.warn(`Failed to clear persisted state:`, e);
          }
        }
      },

      _render() {
        if (definition.render) {
          const updates = definition.render.call(this, this.state);
          this._applyUpdates(updates);
        }

        // Persist state after render if enabled
        if (persistKey) {
          try {
            localStorage.setItem(persistKey, JSON.stringify(this.state));
          } catch (e) {
            // localStorage might be full or disabled
            console.warn(`Failed to persist state for ${islandName}:`, e);
          }
        }
      },

      _applyUpdates(updates) {
        if (!updates) return;
        for (const [selector, value] of Object.entries(updates)) {
          const targets = selector === "this" ? [el] : el.querySelectorAll(selector);
          targets.forEach((target) => {
            if (typeof value === "object" && value !== null) {
              // Handle class toggles: { class: { active: true, disabled: false } }
              if (value.class) {
                for (const [className, enabled] of Object.entries(value.class)) {
                  target.classList.toggle(className, enabled);
                }
              }
              // Handle attributes: { attr: { disabled: true, 'aria-label': 'text' } }
              if (value.attr) {
                for (const [attrName, attrValue] of Object.entries(value.attr)) {
                  if (attrValue === false || attrValue === null) {
                    target.removeAttribute(attrName);
                  } else if (attrValue === true) {
                    target.setAttribute(attrName, "");
                  } else {
                    target.setAttribute(attrName, attrValue);
                  }
                }
              }
              // Handle HTML content: { html: '<span>content</span>' }
              if (value.html !== undefined) {
                target.innerHTML = value.html;
              }
            } else {
              // Simple text content update
              target.textContent = value;
            }
          });
        }
      },
    };

    // Copy custom methods and getters from definition to instance
    const builtinKeys = ['state', 'persist', 'init', 'actions', 'render', 'draggable'];
    Object.keys(definition).forEach(key => {
      if (builtinKeys.includes(key)) return;

      const descriptor = Object.getOwnPropertyDescriptor(definition, key);
      if (descriptor) {
        if (descriptor.get || descriptor.set) {
          // Preserve getter/setter - bind to instance context
          Object.defineProperty(instance, key, {
            get: descriptor.get ? descriptor.get.bind(instance) : undefined,
            set: descriptor.set ? descriptor.set.bind(instance) : undefined,
            enumerable: descriptor.enumerable,
            configurable: descriptor.configurable,
          });
        } else if (typeof descriptor.value === 'function') {
          // Regular method - bind to instance
          instance[key] = descriptor.value.bind(instance);
        }
      }
    });

    // Make state reactive
    instance.state = this._reactive(instance.state, () => instance._render());

    // Bind actions
    if (definition.actions) {
      el.addEventListener("click", (e) => {
        const actionEl = e.target.closest("[data-action]");
        if (actionEl && el.contains(actionEl)) {
          const action = actionEl.dataset.action;
          if (definition.actions[action]) {
            definition.actions[action].call(instance, e);
          }
        }
      });

      // Also handle change events for inputs
      el.addEventListener("change", (e) => {
        const actionEl = e.target.closest("[data-action]");
        if (actionEl && el.contains(actionEl)) {
          const action = actionEl.dataset.action;
          if (definition.actions[action]) {
            definition.actions[action].call(instance, e);
          }
        }
      });
    }

    // Call init
    if (definition.init) {
      definition.init.call(instance);
    }

    // Setup drag-drop if configured
    if (definition.draggable) {
      this._setupDragDrop(el, instance, definition.draggable);
    }

    // Initial render
    instance._render();

    this.instances.set(el, instance);
  },

  /**
   * Create reactive state
   */
  _reactive(obj, onChange) {
    return new Proxy(obj, {
      set(target, prop, value) {
        target[prop] = value;
        onChange();
        return true;
      },
    });
  },

  /**
   * Setup drag-drop for an island
   *
   * Config options:
   *   items: Selector for draggable items (e.g., ".card")
   *   zones: Selector for drop zones (e.g., ".column-cards")
   *   handle: Optional selector for drag handle (e.g., ".drag-handle")
   *   onDragStart(item, e): Called when drag starts
   *   onDragOver(item, zone, e): Called during drag over zone
   *   onDrop(item, zone, info, e): Called on drop
   *     info: { itemId, fromIndex, toIndex, fromZoneId, toZoneId, sameZone }
   *   onDragEnd(item, e): Called when drag ends
   */
  _setupDragDrop(el, instance, config) {
    const { items, zones, handle, onDragStart, onDragOver, onDrop, onDragEnd } = config;

    let draggedItem = null;
    let sourceZone = null;
    let sourceIndex = -1;
    let placeholder = null;

    // Create placeholder element
    const createPlaceholder = () => {
      const ph = document.createElement("div");
      ph.className = "feather-drop-placeholder";
      return ph;
    };

    // Get item index within zone
    const getItemIndex = (zone, item) => {
      const zoneItems = Array.from(zone.querySelectorAll(items));
      return zoneItems.indexOf(item);
    };

    // Calculate drop position from mouse event
    const getDropPosition = (zone, e) => {
      const zoneItems = Array.from(zone.querySelectorAll(items)).filter(i => i !== draggedItem);
      if (zoneItems.length === 0) return 0;

      for (let i = 0; i < zoneItems.length; i++) {
        const rect = zoneItems[i].getBoundingClientRect();
        const midY = rect.top + rect.height / 2;
        if (e.clientY < midY) return i;
      }
      return zoneItems.length;
    };

    // Setup drag handlers on an item
    const setupItem = (item) => {
      // Skip if already setup
      if (item._featherDragSetup) return;
      item._featherDragSetup = true;

      item.setAttribute("draggable", "true");

      // If handle is specified, only allow drag from handle
      if (handle) {
        item.addEventListener("mousedown", (e) => {
          if (!e.target.closest(handle)) {
            item.setAttribute("draggable", "false");
          } else {
            item.setAttribute("draggable", "true");
          }
        });
      }

      item.addEventListener("dragstart", (e) => {
        draggedItem = item;
        sourceZone = item.closest(zones);
        sourceIndex = getItemIndex(sourceZone, item);

        // Set drag data
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", item.dataset.id || "");

        // Add dragging class after a frame (for visual feedback)
        requestAnimationFrame(() => {
          item.classList.add("dragging");
        });

        if (onDragStart) onDragStart.call(instance, item, e);
      });

      item.addEventListener("dragend", (e) => {
        item.classList.remove("dragging");

        // Remove placeholder
        if (placeholder && placeholder.parentNode) {
          placeholder.parentNode.removeChild(placeholder);
        }

        // Remove drag-over class from all zones
        el.querySelectorAll(zones).forEach(z => z.classList.remove("drag-over"));

        if (onDragEnd) onDragEnd.call(instance, item, e);

        draggedItem = null;
        sourceZone = null;
        sourceIndex = -1;
        placeholder = null;
      });
    };

    // Setup drop zone handlers
    const setupZone = (zone) => {
      // Skip if already setup
      if (zone._featherDropSetup) return;
      zone._featherDropSetup = true;

      zone.addEventListener("dragover", (e) => {
        if (!draggedItem) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";

        zone.classList.add("drag-over");

        // Show placeholder at drop position
        if (!placeholder) {
          placeholder = createPlaceholder();
        }

        const dropIndex = getDropPosition(zone, e);
        const zoneItems = Array.from(zone.querySelectorAll(items)).filter(i => i !== draggedItem);

        // Insert placeholder at position
        if (dropIndex >= zoneItems.length) {
          zone.appendChild(placeholder);
        } else {
          zone.insertBefore(placeholder, zoneItems[dropIndex]);
        }

        if (onDragOver) onDragOver.call(instance, draggedItem, zone, e);
      });

      zone.addEventListener("dragleave", (e) => {
        // Only remove if actually leaving the zone (not entering a child)
        if (!zone.contains(e.relatedTarget)) {
          zone.classList.remove("drag-over");
          if (placeholder && placeholder.parentNode === zone) {
            zone.removeChild(placeholder);
          }
        }
      });

      zone.addEventListener("drop", (e) => {
        e.preventDefault();
        if (!draggedItem) return;

        zone.classList.remove("drag-over");

        const dropIndex = getDropPosition(zone, e);
        const sameZone = zone === sourceZone;

        // Calculate actual target index
        let toIndex = dropIndex;
        if (sameZone && sourceIndex < dropIndex) {
          toIndex = dropIndex; // Account for removal
        }

        // Remove placeholder before moving item
        if (placeholder && placeholder.parentNode) {
          placeholder.parentNode.removeChild(placeholder);
        }

        // Build drop info
        const info = {
          itemId: draggedItem.dataset.id || null,
          fromIndex: sourceIndex,
          toIndex: toIndex,
          fromZoneId: sourceZone?.dataset.id || null,
          toZoneId: zone.dataset.id || null,
          sameZone: sameZone
        };

        // Move item in DOM
        const zoneItems = Array.from(zone.querySelectorAll(items)).filter(i => i !== draggedItem);
        if (toIndex >= zoneItems.length) {
          zone.appendChild(draggedItem);
        } else {
          zone.insertBefore(draggedItem, zoneItems[toIndex]);
        }

        if (onDrop) onDrop.call(instance, draggedItem, zone, info, e);
      });
    };

    // Initial setup
    el.querySelectorAll(items).forEach(setupItem);
    el.querySelectorAll(zones).forEach(setupZone);

    // Watch for new items added via HTMX or other means
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (node.nodeType === 1) { // Element node
            if (node.matches && node.matches(items)) {
              setupItem(node);
            }
            // Also check children
            node.querySelectorAll?.(items)?.forEach(setupItem);
            node.querySelectorAll?.(zones)?.forEach(setupZone);
          }
        });
      });
    });

    observer.observe(el, { childList: true, subtree: true });
  },

  /**
   * API client - uses global ApiUtility if available
   */
  _createApiClient() {
    // Use global ApiUtility (from api.js) if available
    if (window.ApiUtility) {
      return window.ApiUtility;
    }

    // Minimal fallback for islands loaded without api.js
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
    return {
      async request(url, options = {}) {
        const headers = {
          "Content-Type": "application/json",
          ...(csrfToken && { "X-CSRFToken": csrfToken }),
          ...options.headers,
        };
        const response = await fetch(url, { ...options, headers });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error?.message || "Request failed");
        return { success: true, data };
      },
      get(url, opts) { return this.request(url, { method: "GET", ...opts }); },
      post(url, body, opts) { return this.request(url, { method: "POST", body: JSON.stringify(body), ...opts }); },
      put(url, body, opts) { return this.request(url, { method: "PUT", body: JSON.stringify(body), ...opts }); },
      delete(url, opts) { return this.request(url, { method: "DELETE", ...opts }); },
    };
  },

  /**
   * Event bus for cross-island communication
   */
  _listeners: new Map(),

  _emit(event, data) {
    const handlers = this._listeners.get(event) || [];
    handlers.forEach((handler) => handler(data));
  },

  _on(event, handler) {
    if (!this._listeners.has(event)) {
      this._listeners.set(event, []);
    }
    this._listeners.get(event).push(handler);
  },
};

// Auto-init on DOMContentLoaded
document.addEventListener("DOMContentLoaded", () => Feather.init());

// Export globally
window.Feather = Feather;
window.island = Feather.island.bind(Feather);
