declare const bootstrap: typeof import("bootstrap");
import { assertDefinedUnwrap } from "./utils.js";
import { CSRF_HEADERS } from "./csrf-utils.js";

const NOTEBOOK_LOCALSTORAGE_KEY = "evap_notebook_open";

if (localStorage.getItem(NOTEBOOK_LOCALSTORAGE_KEY) == "true") {
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
                }, 2000);
            } else {
                target.setAttribute("value", default_label);
                target.disabled = false;
                alert(error_label);
            }
        });
    },
);

assertDefinedUnwrap(document.getElementById("notebook")).addEventListener("show.bs.collapse", function (): void {
    onShowNotebook();
});

assertDefinedUnwrap(document.getElementById("notebook")).addEventListener("hidden.bs.collapse", function (): void {
    onHideNotebook();
});

export function onShowNotebook(): void {
    localStorage.setItem(NOTEBOOK_LOCALSTORAGE_KEY, "true");
    assertDefinedUnwrap(document.getElementById("evapContent")).classList.add("notebook-margin");
    assertDefinedUnwrap(document.getElementById("notebook")).classList.add("notebook-container");
    assertDefinedUnwrap(document.getElementById("notebookButton")).classList.remove("show");
    assertDefinedUnwrap(document.getElementById("notebookButton")).classList.add("hide");
}

export function onHideNotebook(): void {
    localStorage.setItem(NOTEBOOK_LOCALSTORAGE_KEY, "false");
    assertDefinedUnwrap(document.getElementById("evapContent")).classList.remove("notebook-margin");
    assertDefinedUnwrap(document.getElementById("notebook")).classList.remove("notebook-container");
    assertDefinedUnwrap(document.getElementById("notebookButton")).classList.remove("hide");
    assertDefinedUnwrap(document.getElementById("notebookButton")).classList.add("show");
}
