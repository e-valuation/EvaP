// This file contains all typescript code for the base.html template.

// Fix autofocus on bootstrap modals -> Focus the first element with `autofocus` attribute
document.addEventListener("shown.bs.modal", e => {
    if (!e.target) return;
    const modalEl = e.target as HTMLElement;
    const autofocusEl = modalEl.querySelector<HTMLElement>("[autofocus]");
    if (autofocusEl) {
        autofocusEl.focus();
    }
});
