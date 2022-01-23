// based on: https://docs.djangoproject.com/en/3.1/ref/csrf/#ajax
function getCookie(name: string): string | null {
    if (document.cookie !== "") {
        const cookie = document.cookie
            .split(";")
            .map(cookie => cookie.trim())
            .find(cookie => cookie.substring(0, name.length + 1) === `${name}=`);
        if (cookie) {
            return decodeURIComponent(cookie.substring(name.length + 1));
        }
    }
    return null;
}
const csrftoken = getCookie("csrftoken")!;

function isMethodCsrfSafe(method: string): boolean {
    // these HTTP methods do not require CSRF protection
    return ["GET", "HEAD", "OPTIONS", "TRACE"].includes(method.toUpperCase());
}

function isUrlCrossDomain(url: string): boolean {
    return new URL(document.baseURI).origin !== new URL(url, document.baseURI).origin;
}

// setup ajax sending csrf token
$.ajaxSetup({
    beforeSend: function (xhr: JQuery.jqXHR, settings: JQuery.AjaxSettings) {
        const isMethodSafe = settings.method && isMethodCsrfSafe(settings.method);
        if (!isMethodSafe && !this.crossDomain) {
            xhr.setRequestHeader("X-CSRFToken", csrftoken);
        }
    },
});

function addCsrfToken(this: HTMLFormElement, ev: Event) {
    const inputElement = document.createElement("input");
    inputElement.setAttribute("type", "hidden");
    inputElement.setAttribute("name", "csrfmiddlewaretoken");
    inputElement.setAttribute("value", csrftoken);

    const { submitter } = ev as SubmitEvent;
    const action = (submitter && submitter.getAttribute("formaction")) || this.getAttribute("action");
    const method = (submitter && submitter.getAttribute("formmethod")) || this.getAttribute("method");

    if (method && !isMethodCsrfSafe(method) && action && !isUrlCrossDomain(action)) {
        this.insertAdjacentElement("afterbegin", inputElement.cloneNode() as Element);
    }
}

// Add CSRF token to regular forms on submit.
// This reduces boilerplate code in the templates and makes the form's HTML cacheable.
for (const form of document.forms) {
    form.addEventListener("submit", addCsrfToken);
}

export const testable = {
    getCookie,
    isMethodCsrfSafe,
};
