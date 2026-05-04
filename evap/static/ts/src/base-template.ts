import { copyToClipboard } from "./copy-to-clipboard.js";

// This file contains all typescript code for the base.html template.

// Fix autofocus on bootstrap modals -> Focus the first element with `autofocus` attribute
document.addEventListener("shown.bs.modal", e => {
    if (!e.target) {
        return;
    }
    const modalEl = e.target as HTMLElement;
    const autofocusEl = modalEl.querySelector<HTMLElement>("[autofocus]");
    if (autofocusEl) {
        autofocusEl.focus();
    }
});

document.addEventListener("click", e => {
    if (!e.target) {
        return;
    }
    const element = e.target as HTMLElement;
    console.log(element.dataset)
    if ("copyonclick" in element.dataset) {
        void copyToClipboard(element.dataset.copyOnClick!);
        console.log("test");
        navigator.clipboard.writeText(element.dataset.copyOnClick!);
    }
});
