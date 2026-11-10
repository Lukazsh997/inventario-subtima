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
