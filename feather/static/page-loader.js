/**
 * Page Loader — Auto-hides the loading spinner when fonts are ready.
 *
 * This script should be loaded synchronously immediately after the
 * page_loader() macro output so it runs before the page renders.
 */
(function() {
    var loader = document.getElementById('page-loader');
    if (!loader) return;

    function hideLoader() {
        loader.style.opacity = '0';
        loader.style.pointerEvents = 'none';
        setTimeout(function() { loader.remove(); }, 200);
    }

    // Wait for fonts to be ready (important for Material Icons)
    // Falls back to window.load if document.fonts is not supported
    if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(hideLoader);
    } else {
        window.addEventListener('load', hideLoader);
    }
})();
