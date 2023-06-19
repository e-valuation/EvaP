declare const bootstrap: typeof import("bootstrap");
import { getCookie, setCookie, assertDefinedUnwrap } from "./utils.js";
import { CSRF_HEADERS } from "./csrf-utils.js";

const NOTEBOOK_COOKIE_NAME = "evap_notebook_open";

if (getCookie("evap_notebook_open") == "true") {
    new bootstrap.Collapse(assertDefinedUnwrap(document.getElementById("notebook")));
    new bootstrap.Collapse(assertDefinedUnwrap(document.getElementById("notebookButton")));
    onShowNotebook();
}

assertDefinedUnwrap(document.getElementById("notebook-save-button")).addEventListener(
    "click",
    function (event: MouseEvent): void {
        event.preventDefault();
        const form = assertDefinedUnwrap(document.getElementById("notebook-form")) as HTMLFormElement;
        const data = new FormData(form);

        const target = assertDefinedUnwrap(event.target) as HTMLButtonElement;
        const default_label = assertDefinedUnwrap(target.getAttribute("value"));
        const sending_label = assertDefinedUnwrap(target.getAttribute("data-label-sending"));
        const error_label = assertDefinedUnwrap(target.getAttribute("data-label-error"));
        const cooldown_label = assertDefinedUnwrap(target.getAttribute("data-label-cooldown"));
        target.disabled = true;
        target.setAttribute("value", sending_label);
        const cooldown_time = 2000;

        fetch(form.action, {
            body: new URLSearchParams(data as any),
            headers: CSRF_HEADERS,
            method: "POST",
        }).then(response => {
            if (response.ok) {
                target.setAttribute("value", cooldown_label);
                setTimeout(function (): void {
                    target.setAttribute("value", default_label);
                    target.disabled = false;
                }, cooldown_time);
            } else {
                target.disabled = false;
                alert(error_label);
            }
        });
    },
);

// https://github.com/microsoft/TypeScript-DOM-lib-generator/pull/1535
assertDefinedUnwrap(document.getElementById("notebook")).addEventListener("show.bs.collapse", function (): void {
    onShowNotebook();
});

assertDefinedUnwrap(document.getElementById("notebook")).addEventListener("hidden.bs.collapse", function (): void {
    onHideNotebook();
});

export function onShowNotebook(): void {
    setCookie(NOTEBOOK_COOKIE_NAME, "true");
    assertDefinedUnwrap(document.getElementById("evapContent")).classList.add("notebook-margin");
    assertDefinedUnwrap(document.getElementById("notebook")).classList.add("notebook-container");
    assertDefinedUnwrap(document.getElementById("notebookButton")).classList.remove("show");
    assertDefinedUnwrap(document.getElementById("notebookButton")).classList.add("hide");
}

export function onHideNotebook(): void {
    setCookie(NOTEBOOK_COOKIE_NAME, "false");
    assertDefinedUnwrap(document.getElementById("evapContent")).classList.remove("notebook-margin");
    assertDefinedUnwrap(document.getElementById("notebook")).classList.remove("notebook-container");
    assertDefinedUnwrap(document.getElementById("notebookButton")).classList.remove("hide");
    assertDefinedUnwrap(document.getElementById("notebookButton")).classList.add("show");
}
