/* eslint-disable  @typescript-eslint/no-non-null-assertion */
declare const bootstrap: typeof import("bootstrap");
import { getCookie, setCookie } from "./utils.js";

const NOTEBOOK_COOKIE_NAME = "evap_notebook_open";

if (getCookie("evap_notebook_open") == "true") {
    new bootstrap.Collapse(document.getElementById("notebook")!);
    new bootstrap.Collapse(document.getElementById("notebookButton")!);
    onShowNotebook();
}

// generic event listnerfor all events
document.addEventListener("notebook", function () {
    console.log("notebook event fired");
});

// make evap go away for notebook
document.getElementById("notebook")!.addEventListener("show.bs.collapse", function () {
    setCookie(NOTEBOOK_COOKIE_NAME, "true");
    onShowNotebook();
});

document.getElementById("notebook")!.addEventListener("hidden.bs.collapse", function () {
    setCookie(NOTEBOOK_COOKIE_NAME, "false");
    onHideNotebook();
});

export function onShowNotebook(): void {
    document.getElementById("evapContent")!.classList.add("notebook-margin");
    document.getElementById("notebook")!.classList.add("notebook-container");
    document.getElementById("notebookButton")!.classList.remove("show");
    document.getElementById("notebookButton")!.classList.add("hide");
}

export function onHideNotebook(): void {
    document.getElementById("evapContent")!.classList.remove("notebook-margin");
    document.getElementById("notebook")!.classList.remove("notebook-container");
    document.getElementById("notebookButton")!.classList.remove("hide");
    document.getElementById("notebookButton")!.classList.add("show");
}
