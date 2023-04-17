/* eslint-disable  @typescript-eslint/no-non-null-assertion */
declare const bootstrap: typeof import("bootstrap");
import { getCookie, setCookie, assertDefinedUnwrap } from "./utils.js";

const NOTEBOOK_COOKIE_NAME = "evap_notebook_open";

if (getCookie("evap_notebook_open") == "true") {
    new bootstrap.Collapse(assertDefinedUnwrap(document.getElementById("notebook")));
    new bootstrap.Collapse(assertDefinedUnwrap(document.getElementById("notebookButton")));
    onShowNotebook();
}

// https://github.com/microsoft/TypeScript-DOM-lib-generator/pull/1535
assertDefinedUnwrap(document.getElementById("notebook")).addEventListener("show.bs.collapse", function (): void {
    setCookie(NOTEBOOK_COOKIE_NAME, "true");
    onShowNotebook();
});

assertDefinedUnwrap(document.getElementById("notebook")).addEventListener("hidden.bs.collapse", function (): void {
    setCookie(NOTEBOOK_COOKIE_NAME, "false");
    onHideNotebook();
});

export function onShowNotebook(): void {
    assertDefinedUnwrap(document.getElementById("evapContent")).classList.add("notebook-margin");
    assertDefinedUnwrap(document.getElementById("notebook")).classList.add("notebook-container");
    assertDefinedUnwrap(document.getElementById("notebookButton")).classList.remove("show");
    assertDefinedUnwrap(document.getElementById("notebookButton")).classList.add("hide");
}

export function onHideNotebook(): void {
    assertDefinedUnwrap(document.getElementById("evapContent")).classList.remove("notebook-margin");
    assertDefinedUnwrap(document.getElementById("notebook")).classList.remove("notebook-container");
    assertDefinedUnwrap(document.getElementById("notebookButton")).classList.remove("hide");
    assertDefinedUnwrap(document.getElementById("notebookButton")).classList.add("show");
}
