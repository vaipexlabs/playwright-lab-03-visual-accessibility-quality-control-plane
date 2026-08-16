const dialog = document.querySelector("#policy-dialog");

if (dialog?.dataset.autoOpen === "true") {
  dialog.showModal();
}

for (const trigger of document.querySelectorAll("[data-open-dialog]")) {
  trigger.addEventListener("click", () => {
    if (dialog && !dialog.open) {
      dialog.showModal();
    }
  });
}

for (const trigger of document.querySelectorAll("[data-close-dialog]")) {
  trigger.addEventListener("click", () => dialog?.close());
}
