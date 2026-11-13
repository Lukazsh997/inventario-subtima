// Leitura de QR Code e código de barras pela câmera (html5-qrcode / ZXing, empacotado localmente).
// Uso: PatrimonioScanner.open(function (texto) { ... });
// Elementos com data-scan-target="#id" abrem a câmera e preenchem o campo indicado.
(function () {
  "use strict";
  var scanner = null;
  var modal = null;
  var callback = null;

  function lib() {
    return window.__Html5QrcodeLibrary__ || {};
  }

  function stop() {
    if (scanner) {
      var current = scanner;
      scanner = null;
      current.stop().catch(function () {}).finally(function () { current.clear(); });
    }
  }

  function showError(message) {
    var box = document.getElementById("scannerError");
    box.textContent = message;
    box.classList.remove("d-none");
  }

  function open(onResult) {
    callback = onResult;
    var element = document.getElementById("scannerModal");
    modal = bootstrap.Modal.getOrCreateInstance(element);
    document.getElementById("scannerError").classList.add("d-none");
    modal.show();
  }

  function start() {
    if (!window.isSecureContext) {
      showError("A câmera só funciona com o sistema acessado por HTTPS. Use o leitor USB ou digite o código.");
      return;
    }
    var L = lib();
    var F = L.Html5QrcodeSupportedFormats;
    scanner = new L.Html5Qrcode("scannerView", {
      formatsToSupport: [F.QR_CODE, F.CODE_128, F.CODE_39, F.EAN_13, F.DATA_MATRIX],
      useBarCodeDetectorIfSupported: true,
      verbose: false
    });
    scanner.start(
      { facingMode: "environment" },
      { fps: 10, qrbox: function (w, h) { return { width: Math.floor(w * 0.85), height: Math.floor(h * 0.6) }; } },
      function (text) {
        var done = callback;
        callback = null;
        modal.hide();
        if (done) { done(text); }
      },
      function () { /* quadro sem código: ignora */ }
    ).catch(function (err) {
      showError("Não foi possível abrir a câmera: " + (err && err.message ? err.message : err) +
        ". Verifique a permissão do navegador.");
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var element = document.getElementById("scannerModal");
    if (!element) { return; }
    element.addEventListener("shown.bs.modal", start);
    element.addEventListener("hidden.bs.modal", stop);
  });

  document.addEventListener("click", function (event) {
    var trigger = event.target.closest("[data-scan-target]");
    if (!trigger) { return; }
    event.preventDefault();
    var input = document.querySelector(trigger.dataset.scanTarget);
    open(function (text) {
      if (!input) { return; }
      input.value = text;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new CustomEvent("scanned", { bubbles: true, detail: text }));
      if (trigger.dataset.scanSubmit !== undefined && input.form) { input.form.requestSubmit(); }
    });
  });

  window.PatrimonioScanner = { open: open };
})();
