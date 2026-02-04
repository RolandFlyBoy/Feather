/**
 * Toast Notifications — Displays toast messages for user feedback.
 *
 * Usage (JavaScript):
 *   window.showToast('Item saved successfully', 'success');
 *   window.showToast('Something went wrong', 'error');
 *   window.showToast('Please wait...', 'info');
 *
 * Usage (HX-Trigger response header from server):
 *   response.headers["HX-Trigger"] = json.dumps({
 *       "showToast": {"message": "Saved!", "type": "success"}
 *   })
 *
 * Types: success (green), error (red), info (blue)
 */
(function() {
    function showToast(message, type, duration) {
        type = type || 'info';
        duration = duration || 3000;

        var container = document.getElementById('toast-container');
        if (!container) return;

        var toast = document.createElement('div');
        toast.className = 'toast toast-' + type;
        toast.textContent = message;
        container.appendChild(toast);

        setTimeout(function() {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.3s ease';
            setTimeout(function() { toast.remove(); }, 300);
        }, duration);
    }

    // Expose globally
    window.showToast = showToast;

    // Listen for HX-Trigger events from server
    document.body.addEventListener('htmx:afterRequest', function(evt) {
        var trigger = evt.detail.xhr && evt.detail.xhr.getResponseHeader('HX-Trigger');
        if (trigger) {
            try {
                var data = JSON.parse(trigger);
                if (data.showToast) {
                    showToast(data.showToast.message, data.showToast.type || 'success');
                }
            } catch (e) {}
        }
    });

    // Show pending toast from server redirect (data stored in hidden div)
    document.addEventListener('DOMContentLoaded', function() {
        var el = document.getElementById('pending-toast-data');
        if (el && window.showToast) {
            window.showToast(el.dataset.message, el.dataset.type || 'info');
        }
    });
})();
