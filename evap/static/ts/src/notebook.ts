declare const bootstrap: typeof import("bootstrap");
import { getCookie, setCookie, selectOrError } from "./utils.js";

document.getElementById("123");

var notebook = selectOrError("notebook");
var evapContent = selectOrError("evapContent");

if (getCookie("evap_notebook_open") == "true") {
    new bootstrap.Collapse(notebook);
    new bootstrap.Collapse(selectOrError("#notebookButton"));
    onShowNotebook();
}

// make evap go away for notebook
notebook.addEventListener("show.bs.collapse", function () {
    onShowNotebook();
    setCookie("evap_notebook_open", "true");
});

notebook.addEventListener("hidden.bs.collapse", function () {
    onHideNotebook();
    setCookie("evap_notebook_open", "false");
});

export function onShowNotebook(): void {
    evapContent.classList.add("notebook-margin");
    notebook.classList.add("notebook-container");
}

export function onHideNotebook(): void {
    evapContent.classList.remove("notebook-margin");
    notebook.classList.remove("notebook-container");
}
