declare const bootstrap: typeof import("bootstrap");
import { getCookie, setCookie } from "./utils.js";

document.getElementById("123");

if (getCookie("evap_notebook_open") == "true") {
    new bootstrap.Collapse(document.querySelector("#notebook")!);
    new bootstrap.Collapse(document.querySelector("#notebookButton")!);
    onShowNotebook();
}

// make evap go away for notebook
document.querySelector("#notebook")!.addEventListener("show.bs.collapse", function () {
    onShowNotebook();
    setCookie("evap_notebook_open", "true");
});

document.querySelector("#notebook")!.addEventListener("hidden.bs.collapse", function () {
    onHideNotebook();
    setCookie("evap_notebook_open", "false");
});

export function onShowNotebook(): void {
    document.getElementById("evapContent")!.classList.add("notebook-margin");
    document.getElementById("notebook")!.classList.add("notebook-container");
}

export function onHideNotebook(): void {
    document.getElementById("evapContent")!.classList.remove("notebook-margin");
    document.getElementById("notebook")!.classList.remove("notebook-container");
}
