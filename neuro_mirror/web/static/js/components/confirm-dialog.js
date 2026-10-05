// neuro_mirror/web/static/js/components/confirm-dialog.js
//
// In-page confirmation dialog. Used instead of window.confirm(): the native
// dialog cannot be styled to the 58+ requirements (18px text, 44px targets)
// and blocks the page. Resolves true when the user confirms.

export function confirmDialog({
  title,
  message,
  confirmLabel = "Да",
  cancelLabel = "Отмена",
}) {
  return new Promise((resolve) => {
    const previousFocus = document.activeElement;
    const backdrop = document.createElement("div");
    backdrop.className = "nm-dialog-backdrop";

    const dialog = document.createElement("div");
    dialog.className = "nm-dialog";
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-labelledby", "nm-dialog-title");
    dialog.setAttribute("aria-describedby", "nm-dialog-text");

    const heading = document.createElement("h2");
    heading.className = "nm-dialog-title";
    heading.id = "nm-dialog-title";
    heading.textContent = title;

    const text = document.createElement("p");
    text.className = "nm-dialog-text";
    text.id = "nm-dialog-text";
    text.textContent = message;

    const row = document.createElement("div");
    row.className = "nm-btn-row";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "nm-btn nm-btn-primary";
    cancel.textContent = cancelLabel;
    const confirm = document.createElement("button");
    confirm.type = "button";
    confirm.className = "nm-btn nm-btn-secondary";
    confirm.textContent = confirmLabel;
    row.append(confirm, cancel);

    dialog.append(heading, text, row);
    backdrop.appendChild(dialog);

    const close = (result) => {
      document.removeEventListener("keydown", onKey, true);
      backdrop.remove();
      if (previousFocus && previousFocus.focus) previousFocus.focus();
      resolve(result);
    };
    const onKey = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close(false);
      } else if (event.key === "Tab") {
        // Keep keyboard focus inside the dialog
        const targets = [confirm, cancel];
        const index = targets.indexOf(document.activeElement);
        event.preventDefault();
        const next = event.shiftKey ? index - 1 : index + 1;
        targets[(next + targets.length) % targets.length].focus();
      }
    };

    cancel.addEventListener("click", () => close(false));
    confirm.addEventListener("click", () => close(true));
    document.addEventListener("keydown", onKey, true);
    document.body.appendChild(backdrop);
    // The safe choice (stay) is the default focus
    cancel.focus();
  });
}
