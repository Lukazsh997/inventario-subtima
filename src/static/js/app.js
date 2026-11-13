// Componentes Alpine reutilizáveis.
document.addEventListener("alpine:init", function () {
  "use strict";

  // Setor de destino → servidores e locais daquele setor (JSON do servidor).
  window.Alpine.data("destinationPicker", function (config) {
    return {
      sector: config.sector || "",
      recipient: config.recipient || "",
      location: config.location || "",
      newName: config.newName || "",
      creating: !!config.newName,
      recipients: [],
      locations: [],
      init: function () { if (this.sector) { this.load(true); } },
      load: function (keepSelection) {
        var self = this;
        if (!keepSelection) { self.recipient = ""; self.location = ""; }
        self.recipients = []; self.locations = [];
        if (!self.sector) { return; }
        fetch(config.url + "?setor=" + encodeURIComponent(self.sector), { headers: { "Accept": "application/json" } })
          .then(function (r) { return r.json(); })
          .then(function (data) { self.recipients = data.recipients; self.locations = data.locations; });
      }
    };
  });
});

// Confirmação para operações críticas: <form data-confirm="Mensagem"> abre um modal antes de enviar.
(function () {
  "use strict";
  var pendingForm = null;

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.dataset.confirm || form.dataset.confirmed === "1") {
      return;
    }
    event.preventDefault();
    pendingForm = form;
    var body = document.getElementById("confirmModalBody");
    var okButton = document.getElementById("confirmModalOk");
    body.textContent = form.dataset.confirm;
    okButton.className = "btn " + (form.dataset.confirmStyle === "danger" ? "btn-danger" : "btn-primary");
    bootstrap.Modal.getOrCreateInstance(document.getElementById("confirmModal")).show();
  });

  document.addEventListener("click", function (event) {
    if (event.target && event.target.id === "confirmModalOk" && pendingForm) {
      pendingForm.dataset.confirmed = "1";
      bootstrap.Modal.getOrCreateInstance(document.getElementById("confirmModal")).hide();
      pendingForm.requestSubmit ? pendingForm.requestSubmit() : pendingForm.submit();
      pendingForm = null;
    }
  });

  // Evita envio duplo de formulários (ex.: duplo clique em "Salvar").
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (event.defaultPrevented || !(form instanceof HTMLFormElement)) { return; }
    form.querySelectorAll("button[type=submit]").forEach(function (button) {
      setTimeout(function () { button.disabled = true; }, 0);
    });
  });
})();
