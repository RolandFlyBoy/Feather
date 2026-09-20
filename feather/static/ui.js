// Feather's UI foundation: the behaviours behind static/css/ui.css.
//
// Lightbox (data-lightbox on gallery links), uploader (data-uploader with
// drag and drop, previews and a progress bar when submitted through fetch),
// dialogs (data-dialog-open / data-dialog-close) and confirms
// (data-confirm on forms). No inline scripts, no inline handlers; everything
// is wired here with addEventListener, and it re-wires after HTMX swaps.
(function () {
  "use strict";

  // ── Lightbox ───────────────────────────────────────────────
  // <a href="full.jpg" data-lightbox="album" data-caption="..."><img ...></a>
  // Links sharing a data-lightbox value become one set with prev and next.
  function ensureLightbox() {
    let dialog = document.getElementById("ui-lightbox");
    if (dialog) return dialog;
    dialog = document.createElement("dialog");
    dialog.id = "ui-lightbox";
    dialog.className = "ui-lightbox";
    dialog.setAttribute("aria-label", "Image viewer");
    dialog.innerHTML =
      '<div class="ui-lightbox-frame">' +
      '<img alt="">' +
      '<div class="ui-lightbox-caption" hidden></div>' +
      '<button type="button" class="ui-lightbox-close" aria-label="Close"><span class="icon">close</span></button>' +
      '<button type="button" class="ui-lightbox-prev" aria-label="Previous"><span class="icon">chevron_left</span></button>' +
      '<button type="button" class="ui-lightbox-next" aria-label="Next"><span class="icon">chevron_right</span></button>' +
      "</div>";
    document.body.appendChild(dialog);
    const state = { items: [], index: 0 };
    const img = dialog.querySelector("img");
    const caption = dialog.querySelector(".ui-lightbox-caption");
    function show(i) {
      state.index = (i + state.items.length) % state.items.length;
      const item = state.items[state.index];
      img.src = item.href;
      img.alt = item.alt || "";
      caption.textContent = item.caption || "";
      caption.hidden = !item.caption;
      dialog.classList.toggle("ui-lightbox-single", state.items.length < 2);
    }
    dialog.open = function (items, index) {
      state.items = items;
      show(index);
      if (!dialog.hasAttribute("open")) dialog.showModal();
      document.body.style.overflow = "hidden";
    };
    function close() {
      if (dialog.hasAttribute("open")) dialog.close();
    }
    dialog.addEventListener("close", () => { document.body.style.overflow = ""; });
    dialog.querySelector(".ui-lightbox-close").addEventListener("click", close);
    dialog.querySelector(".ui-lightbox-prev").addEventListener("click", () => show(state.index - 1));
    dialog.querySelector(".ui-lightbox-next").addEventListener("click", () => show(state.index + 1));
    dialog.addEventListener("click", (event) => { if (event.target === dialog || event.target.classList.contains("ui-lightbox-frame")) close(); });
    dialog.addEventListener("keydown", (event) => {
      if (event.key === "ArrowLeft") show(state.index - 1);
      if (event.key === "ArrowRight") show(state.index + 1);
    });
    let touchStart = null;
    dialog.addEventListener("touchstart", (event) => { touchStart = event.touches[0].clientX; }, { passive: true });
    dialog.addEventListener("touchend", (event) => {
      if (touchStart === null) return;
      const delta = event.changedTouches[0].clientX - touchStart;
      if (Math.abs(delta) > 40) show(state.index + (delta < 0 ? 1 : -1));
      touchStart = null;
    });
    return dialog;
  }

  function wireLightboxes(root) {
    root.querySelectorAll("[data-lightbox]:not([data-ui-wired])").forEach((link) => {
      link.setAttribute("data-ui-wired", "1");
      link.addEventListener("click", (event) => {
        event.preventDefault();
        const group = link.getAttribute("data-lightbox");
        const links = Array.from(document.querySelectorAll('[data-lightbox="' + group + '"]'));
        const items = links.map((a) => ({
          href: a.getAttribute("href"),
          caption: a.getAttribute("data-caption") || "",
          alt: (a.querySelector("img") || {}).alt || "",
        }));
        ensureLightbox().open(items, Math.max(0, links.indexOf(link)));
      });
    });
  }

  // ── Uploader ───────────────────────────────────────────────
  // <label class="ui-uploader" data-uploader>
  //   <input type="file" name="photos" multiple accept="image/*">
  //   ... <div class="ui-uploader-previews"></div>
  // </label>
  // Inside a form with data-upload-progress, the form submits with fetch
  // and shows progress; otherwise the form submits as usual.
  function wireUploaders(root) {
    root.querySelectorAll("[data-uploader]:not([data-ui-wired])").forEach((zone) => {
      zone.setAttribute("data-ui-wired", "1");
      const input = zone.querySelector('input[type="file"]');
      const previews = zone.querySelector(".ui-uploader-previews");
      if (!input) return;
      function preview() {
        if (!previews) return;
        previews.innerHTML = "";
        Array.from(input.files || []).slice(0, 24).forEach((file) => {
          if (!file.type.startsWith("image/")) return;
          const img = document.createElement("img");
          img.alt = "";
          // A data URL rather than a blob URL: the app's content policy allows
          // data: images everywhere, and a blob: source is blocked by default.
          const reader = new FileReader();
          reader.addEventListener("load", () => { img.src = reader.result; });
          reader.readAsDataURL(file);
          previews.appendChild(img);
        });
        const title = zone.querySelector(".ui-uploader-title");
        if (title && input.files && input.files.length) {
          title.textContent = input.files.length === 1 ? input.files[0].name : input.files.length + " files chosen";
        }
        if (zone.hasAttribute("data-submit-on-choose") && input.form) input.form.requestSubmit();
      }
      input.addEventListener("change", preview);
      ["dragenter", "dragover"].forEach((name) => zone.addEventListener(name, (event) => { event.preventDefault(); zone.classList.add("is-dragging"); }));
      ["dragleave", "drop"].forEach((name) => zone.addEventListener(name, (event) => { event.preventDefault(); zone.classList.remove("is-dragging"); }));
      zone.addEventListener("drop", (event) => {
        if (event.dataTransfer && event.dataTransfer.files.length) {
          input.files = event.dataTransfer.files;
          preview();
        }
      });
    });

    root.querySelectorAll("form[data-upload-progress]:not([data-ui-wired])").forEach((form) => {
      form.setAttribute("data-ui-wired", "1");
      form.addEventListener("submit", (event) => {
        if (!window.XMLHttpRequest) return;
        event.preventDefault();
        const bar = form.querySelector(".ui-progress-bar");
        const progress = form.querySelector(".ui-progress");
        if (progress) progress.hidden = false;
        const submit = form.querySelector('[type="submit"]');
        if (submit) submit.disabled = true;
        const request = new XMLHttpRequest();
        request.open(form.method || "POST", form.action);
        request.setRequestHeader("X-Requested-With", "XMLHttpRequest");
        const token = document.querySelector('meta[name="csrf-token"]');
        if (token) request.setRequestHeader("X-CSRFToken", token.content);
        request.upload.addEventListener("progress", (e) => { if (bar && e.lengthComputable) bar.style.width = Math.round((e.loaded / e.total) * 100) + "%"; });
        request.addEventListener("load", () => {
          if (request.status >= 200 && request.status < 400) {
            const to = request.getResponseHeader("HX-Redirect") || request.responseURL || form.getAttribute("data-upload-done") || window.location.href;
            window.location.assign(to);
          } else {
            if (submit) submit.disabled = false;
            if (progress) progress.hidden = true;
            if (window.showToast) window.showToast("The upload did not go through. Please try again.", "error");
          }
        });
        request.addEventListener("error", () => { if (submit) submit.disabled = false; if (window.showToast) window.showToast("The upload did not go through. Please try again.", "error"); });
        request.send(new FormData(form));
      });
    });
  }

  // ── Dialogs ────────────────────────────────────────────────
  // <button data-dialog-open="share">…</button> <dialog id="share" class="ui-dialog">…<button data-dialog-close>…</dialog>
  function wireDialogs(root) {
    root.querySelectorAll("[data-dialog-open]:not([data-ui-wired])").forEach((button) => {
      button.setAttribute("data-ui-wired", "1");
      button.addEventListener("click", () => {
        const dialog = document.getElementById(button.getAttribute("data-dialog-open"));
        if (dialog && !dialog.hasAttribute("open")) { dialog.showModal(); document.body.style.overflow = "hidden"; }
      });
    });
    root.querySelectorAll("dialog.ui-dialog:not([data-ui-wired])").forEach((dialog) => {
      dialog.setAttribute("data-ui-wired", "1");
      dialog.addEventListener("close", () => { document.body.style.overflow = ""; });
      dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
      dialog.querySelectorAll("[data-dialog-close]").forEach((b) => b.addEventListener("click", () => dialog.close()));
    });
  }

  // ── Confirm ────────────────────────────────────────────────
  // <form data-confirm="Delete this photo?"> uses the app's styled confirm
  // (window.showConfirm from Feather) and never the native dialog.
  function wireConfirms(root) {
    root.querySelectorAll("form[data-confirm]:not([data-ui-wired])").forEach((form) => {
      form.setAttribute("data-ui-wired", "1");
      form.addEventListener("submit", (event) => {
        if (form.dataset.confirmed === "1") { form.dataset.confirmed = ""; return; }
        event.preventDefault();
        const message = form.getAttribute("data-confirm") || "Are you sure?";
        const proceed = () => { form.dataset.confirmed = "1"; form.requestSubmit(); };
        if (window.showConfirm) {
          const result = window.showConfirm(message);
          if (result && typeof result.then === "function") result.then((ok) => { if (ok) proceed(); });
        } else {
          proceed();
        }
      });
    });
  }

  function wire(root) {
    wireLightboxes(root);
    wireUploaders(root);
    wireDialogs(root);
    wireConfirms(root);
  }

  document.addEventListener("DOMContentLoaded", () => wire(document));
  document.body.addEventListener("htmx:afterSwap", (event) => wire(event.target || document));
  document.body.addEventListener("htmx:afterSettle", (event) => wire(event.target || document));
  if (document.readyState !== "loading") wire(document);
})();
