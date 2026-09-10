/**
 * Prompt Modal — A modal dialog for prompting user input.
 *
 * Usage:
 *   window.showPrompt({
 *       title: 'Add Item',
 *       message: 'Enter item name:',
 *       placeholder: 'Item name',
 *       confirmText: 'Create',
 *       onConfirm: (value) => { ... }
 *   });
 *
 * Elements are resolved lazily, inside showPrompt and inside the event
 * handlers, so this script can load before the modal markup exists
 * (base.html renders components after the scripts).
 */
(function() {
    let onConfirmCallback = null;

    /** Look up the modal elements at call time. Returns null if absent. */
    function getElements() {
        const modal = document.getElementById('prompt-modal');
        if (!modal) {
            return null;
        }
        return {
            modal: modal,
            titleEl: document.getElementById('prompt-title'),
            messageEl: document.getElementById('prompt-message'),
            inputEl: document.getElementById('prompt-input'),
        };
    }

    function isOpen(els) {
        return els && !els.modal.classList.contains('hidden');
    }

    function closeModal() {
        const els = getElements();
        if (!els) {
            return;
        }
        els.modal.classList.add('hidden');
        if (els.inputEl) {
            els.inputEl.value = '';
        }
        onConfirmCallback = null;
    }

    function confirmValue() {
        const els = getElements();
        if (!els) {
            return;
        }
        const value = els.inputEl ? els.inputEl.value.trim() : '';
        const callback = onConfirmCallback;
        closeModal();
        if (value && callback) {
            callback(value);
        }
    }

    window.showPrompt = function(options) {
        options = options || {};
        const els = getElements();
        if (!els) {
            console.warn('showPrompt: #prompt-modal not found. Include the prompt_modal component.');
            return;
        }

        if (els.titleEl) {
            els.titleEl.textContent = options.title || 'Enter Value';
        }
        if (els.messageEl) {
            els.messageEl.textContent = options.message || '';
        }
        if (els.inputEl) {
            els.inputEl.placeholder = options.placeholder || '';
            els.inputEl.value = options.defaultValue || '';
        }

        const confirmBtn = els.modal.querySelector('[data-action="confirm"]');
        if (confirmBtn) {
            confirmBtn.textContent = options.confirmText || 'OK';
        }

        onConfirmCallback = options.onConfirm;
        els.modal.classList.remove('hidden');

        // Focus input after modal is visible
        if (els.inputEl) {
            setTimeout(() => els.inputEl.focus(), 50);
        }
    };

    // Delegated from the document so the handlers work regardless of when the
    // modal markup is rendered (or re-rendered, e.g. by an HTMX swap).
    document.addEventListener('click', (e) => {
        const els = getElements();
        if (!isOpen(els) || !els.modal.contains(e.target)) {
            return;
        }
        const action = e.target.dataset ? e.target.dataset.action : null;
        if (action === 'confirm') {
            confirmValue();
        } else if (action === 'cancel') {
            closeModal();
        }
    });

    document.addEventListener('keydown', (e) => {
        const els = getElements();
        if (!isOpen(els)) {
            return;
        }
        if (e.key === 'Enter' && els.inputEl && e.target === els.inputEl) {
            e.preventDefault();
            confirmValue();
        } else if (e.key === 'Escape') {
            closeModal();
        }
    });
})();
