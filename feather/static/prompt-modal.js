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
 */
(function() {
    const modal = document.getElementById('prompt-modal');
    const titleEl = document.getElementById('prompt-title');
    const messageEl = document.getElementById('prompt-message');
    const inputEl = document.getElementById('prompt-input');
    let onConfirmCallback = null;

    window.showPrompt = function(options) {
        titleEl.textContent = options.title || 'Enter Value';
        messageEl.textContent = options.message || '';
        inputEl.placeholder = options.placeholder || '';
        inputEl.value = options.defaultValue || '';

        const confirmBtn = modal.querySelector('[data-action="confirm"]');
        confirmBtn.textContent = options.confirmText || 'OK';

        onConfirmCallback = options.onConfirm;
        modal.classList.remove('hidden');

        // Focus input after modal is visible
        setTimeout(() => inputEl.focus(), 50);
    };

    function closeModal() {
        modal.classList.add('hidden');
        inputEl.value = '';
        onConfirmCallback = null;
    }

    modal.addEventListener('click', (e) => {
        const action = e.target.dataset.action;
        if (action === 'confirm') {
            const value = inputEl.value.trim();
            if (value && onConfirmCallback) {
                onConfirmCallback(value);
            }
            closeModal();
        } else if (action === 'cancel') {
            closeModal();
        }
    });

    // Submit on Enter key
    inputEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            const value = inputEl.value.trim();
            if (value && onConfirmCallback) {
                onConfirmCallback(value);
            }
            closeModal();
        } else if (e.key === 'Escape') {
            closeModal();
        }
    });

    // Close on Escape key (when not focused on input)
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !modal.classList.contains('hidden')) {
            closeModal();
        }
    });
})();
