/* eslint-disable  @typescript-eslint/no-non-null-assertion */
declare const bootstrap: typeof import("bootstrap");
import { getCookie, setCookie, assertDefinedUnwrap } from "./utils.js";

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
        const error_label = assertDefinedUnwrap(target.getAttribute("value"));
        target.disabled = true;

        const form_json = JSON.stringify(Object.fromEntries(data.entries()));

        const cooldown_time = 2000;
        const success_code = 204;

        fetch(form.action, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": assertDefinedUnwrap(getCookie("csrftoken")),
            },
            body: form_json,
        }).then(response => {
            if (response.status == success_code) {
                target.setAttribute("value", assertDefinedUnwrap(target.getAttribute("data-label-cooldown")));
                setTimeout(function (): void {
                    target.disabled = false;
                    target.setAttribute("value", default_label);
                }, cooldown_time);
            } else {
                alert(error_label);
            }
        });
    },
);

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
