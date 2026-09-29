/**
 * The email sign-in code (feather/templates/auth/email_sign_in.html).
 *
 * Turns the one code field into a box per digit, and signs in as soon as the last digit arrives: typed, pasted as a
 * whole (with or without spaces or a dash), or filled in by the phone from the
 * email (autocomplete="one-time-code"). No button to press. Without this
 * script the page still works: one field and a Sign in button.
 */
(function () {
  "use strict";

  function init(form) {
    var field = form.querySelector("input[name=code]");
    if (!field || form.dataset.codeReady) return;
    form.dataset.codeReady = "1";
    var length = parseInt(field.dataset.length, 10) || 6;
    var submitted = false;

    var boxes = document.createElement("div");
    boxes.className = "fsi-boxes";
    boxes.setAttribute("role", "group");
    boxes.setAttribute("aria-label", "Sign-in code");

    var inputs = [];
    for (var i = 0; i < length; i++) {
      if (length === 6 && i === 3) {
        var sep = document.createElement("span");
        sep.className = "fsi-sep";
        sep.setAttribute("aria-hidden", "true");
        boxes.appendChild(sep);
      }
      var box = document.createElement("input");
      box.className = "fsi-box";
      box.type = "text";
      box.inputMode = "numeric";
      box.maxLength = length; // room for a whole pasted or autofilled code
      box.setAttribute("aria-label", "Digit " + (i + 1) + " of " + length);
      box.autocomplete = i === 0 ? "one-time-code" : "off";
      boxes.appendChild(box);
      inputs.push(box);
    }

    // The original field carries the code to the server, out of sight.
    field.type = "hidden";
    field.removeAttribute("required");
    field.parentNode.insertBefore(boxes, field);
    var label = form.querySelector("label[for=fsi-code]");
    if (label) label.setAttribute("aria-hidden", "true");
    var button = form.querySelector("[data-sign-in-submit]");
    if (button) button.hidden = true;

    function digits(text) {
      return (text || "").replace(/\D/g, "");
    }

    function value() {
      return inputs.map(function (b) { return b.value; }).join("");
    }

    function fill(from, text) {
      var d = digits(text);
      for (var j = 0; j < d.length && from + j < length; j++) {
        inputs[from + j].value = d[j];
      }
      var next = Math.min(from + d.length, length - 1);
      inputs[next].focus();
      maybeSubmit();
    }

    function maybeSubmit() {
      var code = value();
      if (submitted || code.length !== length || !/^\d+$/.test(code)) return;
      submitted = true;
      field.value = code;
      boxes.setAttribute("aria-busy", "true");
      if (form.requestSubmit) form.requestSubmit();
      else form.submit();
    }

    inputs.forEach(function (box, index) {
      box.addEventListener("input", function () {
        var d = digits(box.value);
        if (d.length > 1) {
          // Autofill or a paste the browser put straight in the box.
          box.value = "";
          fill(index, d);
          return;
        }
        box.value = d;
        if (d && index < length - 1) inputs[index + 1].focus();
        maybeSubmit();
      });

      box.addEventListener("paste", function (event) {
        var text = (event.clipboardData || window.clipboardData).getData("text");
        if (!digits(text)) return;
        event.preventDefault();
        fill(index, text);
      });

      box.addEventListener("keydown", function (event) {
        if (event.key === "Backspace" && !box.value && index > 0) {
          inputs[index - 1].value = "";
          inputs[index - 1].focus();
          event.preventDefault();
        } else if (event.key === "ArrowLeft" && index > 0) {
          inputs[index - 1].focus();
          event.preventDefault();
        } else if (event.key === "ArrowRight" && index < length - 1) {
          inputs[index + 1].focus();
          event.preventDefault();
        }
      });

      box.addEventListener("focus", function () { box.select(); });
    });

    inputs[0].focus();
  }

  function start() {
    document.querySelectorAll("form[data-sign-in-code]").forEach(init);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
